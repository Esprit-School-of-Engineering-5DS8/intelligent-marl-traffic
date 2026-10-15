import json
import math
import os
import random
import sys
from pathlib import Path

if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci


# ====================== CONFIG ======================
TLS_ID = "J6"
SUMO_CONFIG = Path(__file__).with_name("Traci.sumocfg")
SUMO_BINARY = os.environ.get("SUMO_BINARY", "sumo-gui")
STEP_LENGTH = 0.1
CONTROL_STEPS = 50              # Re-evaluate queues and emergency vehicles every 5 s.
YELLOW_SECONDS = 3.0
MAX_SIMULATION_STEPS = 12000    # Hard limit: 20 simulated minutes at this step length.
QUEUE_IMBALANCE_OVERRIDE = 3
EMERGENCY_PREEMPTION_DISTANCE = 120.0
Q_TABLE_PATH = Path(os.environ.get(
    "TRACI6_Q_TABLE_PATH",
    Path(__file__).with_name("traci6_qtable.json"),
))

ALPHA = 0.1
GAMMA = 0.9
EPSILON_START = 0.2
EPSILON_MIN = 0.02
EPSILON_DECAY = 0.995

EW, SOUTH = 0, 1
ACTION_NAMES = ("EW", "Sud")
GREEN_PHASES = {EW: 0, SOUTH: 2}
YELLOW_PHASES = {EW: 1, SOUTH: 3}
YELLOW_STEPS = round(YELLOW_SECONDS / STEP_LENGTH)
ACTION_COUNT = len(ACTION_NAMES)


def load_model():
    if not Q_TABLE_PATH.exists():
        return {}, EPSILON_START, 0

    model = json.loads(Q_TABLE_PATH.read_text(encoding="utf-8"))
    if not isinstance(model, dict) or model.get("version") != 1:
        raise ValueError(f"Unsupported Q-learning model format in {Q_TABLE_PATH}")

    q_values = model.get("q_values")
    epsilon = model.get("epsilon")
    updates = model.get("updates")
    if not isinstance(q_values, dict):
        raise ValueError(f"Invalid Q-values in {Q_TABLE_PATH}")
    if not isinstance(epsilon, (int, float)) or not EPSILON_MIN <= epsilon <= 1:
        raise ValueError(f"Invalid exploration rate in {Q_TABLE_PATH}")
    if not isinstance(updates, int) or updates < 0:
        raise ValueError(f"Invalid update count in {Q_TABLE_PATH}")

    for state, values in q_values.items():
        if (not isinstance(state, str) or not isinstance(values, list)
                or len(values) != ACTION_COUNT):
            raise ValueError(f"Invalid state entry in {Q_TABLE_PATH}: {state!r}")
        if any(not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in values):
            raise ValueError(f"Invalid Q-value for state {state!r} in {Q_TABLE_PATH}")
        q_values[state] = [float(value) for value in values]

    return q_values, float(epsilon), updates


def save_model(q_values, epsilon, updates):
    model = {
        "version": 1,
        "epsilon": epsilon,
        "updates": updates,
        "q_values": q_values,
    }
    temporary_path = Q_TABLE_PATH.with_suffix(Q_TABLE_PATH.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(model, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(Q_TABLE_PATH)


def get_queues():
    """Return stopped-vehicle counts on the two approaches to J6."""
    q_ew = (
        traci.edge.getLastStepHaltingNumber("E3")
        + traci.edge.getLastStepHaltingNumber("-E4")
    )
    q_south = traci.edge.getLastStepHaltingNumber("E5")
    return q_ew, q_south


def current_green_group():
    phase = traci.trafficlight.getPhase(TLS_ID)
    if phase in (0, 1):
        return EW
    if phase in (2, 3):
        return SOUTH
    raise RuntimeError(f"Unexpected traffic-light phase {phase} for {TLS_ID}")


def queue_bucket(queue):
    if queue == 0:
        return 0
    if queue <= 2:
        return 1
    if queue <= 5:
        return 2
    if queue <= 9:
        return 3
    return 4


def get_state():
    q_ew, q_south = get_queues()
    return f"{queue_bucket(q_ew)},{queue_bucket(q_south)},{current_green_group()}"


def choose_action(state, q_values, epsilon, q_ew, q_south):
    # Do not let a stale/undertrained Q-value keep a clearly longer queue red.
    imbalance = q_ew - q_south
    if imbalance >= QUEUE_IMBALANCE_OVERRIDE:
        return EW
    if imbalance <= -QUEUE_IMBALANCE_OVERRIDE:
        return SOUTH

    values = q_values.setdefault(state, [0.0] * ACTION_COUNT)
    if random.random() < epsilon:
        return random.randrange(ACTION_COUNT)
    best_value = max(values)
    best_actions = [action for action, value in enumerate(values) if value == best_value]
    return random.choice(best_actions)


def simulation_has_work():
    return (
        traci.simulation.getTime() < MAX_SIMULATION_STEPS * STEP_LENGTH
        and traci.simulation.getMinExpectedNumber() > 0
    )


def advance_one_step(reward_samples):
    if not simulation_has_work():
        return False
    traci.simulationStep()
    q_ew, q_south = get_queues()
    reward_samples.append(-(q_ew + q_south))
    return True


def settle_yellow(reward_samples):
    """Finish a yellow phase before the next Q-learning decision."""
    for _ in range(YELLOW_STEPS + 2):
        phase = traci.trafficlight.getPhase(TLS_ID)
        if phase in GREEN_PHASES.values():
            return True
        if phase not in YELLOW_PHASES.values():
            raise RuntimeError(f"Unexpected traffic-light phase {phase} for {TLS_ID}")
        if not advance_one_step(reward_samples):
            return False
    raise RuntimeError(f"Traffic light {TLS_ID} did not finish its yellow phase")


def run_action(target_group):
    """Serve the selected approach and return its average queue reward."""
    reward_samples = []
    if not settle_yellow(reward_samples):
        return None, target_group, False

    emergency_override = False
    for _ in range(CONTROL_STEPS):
        emergency_group = ambulance_priority_group()
        if emergency_group is not None:
            if not emergency_override:
                print(f"  *** Priorité ambulance : {ACTION_NAMES[emergency_group]}")
            target_group = emergency_group
            emergency_override = True

        current_group = current_green_group()
        if target_group != current_group:
            cleared_group = current_group
            traci.trafficlight.setPhase(TLS_ID, YELLOW_PHASES[current_group])
            if not settle_yellow(reward_samples):
                return None, target_group, emergency_override
            emergency_group = ambulance_priority_group()
            if emergency_group is not None:
                if not emergency_override:
                    print(f"  *** Priorité ambulance : {ACTION_NAMES[emergency_group]}")
                target_group = emergency_group
                emergency_override = True
            if current_green_group() != target_group:
                if target_group == cleared_group:
                    # The yellow has cleared the old green; resume that same
                    # approach if an emergency vehicle arrived during clearance.
                    traci.trafficlight.setPhase(TLS_ID, GREEN_PHASES[target_group])
                else:
                    raise RuntimeError(
                        f"Yellow phase did not lead to the requested green for {TLS_ID}"
                    )

        # Keep the selected green active throughout this control interval.
        traci.trafficlight.setPhaseDuration(
            TLS_ID, CONTROL_STEPS * STEP_LENGTH + STEP_LENGTH
        )
        if not advance_one_step(reward_samples):
            break

    if not reward_samples:
        return None, target_group, emergency_override
    return sum(reward_samples) / len(reward_samples), target_group, emergency_override


def update_q_value(q_values, state, action, reward, next_state, discount):
    current_values = q_values.setdefault(state, [0.0] * ACTION_COUNT)
    next_values = q_values.setdefault(next_state, [0.0] * ACTION_COUNT)
    target = reward + discount * max(next_values)
    current_values[action] += ALPHA * (target - current_values[action])


def ambulance_priority_group():
    """Return the approach an emergency vehicle needs, if it is near J6."""
    for vehicle_id in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(vehicle_id) != "emergency":
            continue
        next_tls = traci.vehicle.getNextTLS(vehicle_id)
        if (not next_tls or next_tls[0][0] != TLS_ID
                or next_tls[0][2] >= EMERGENCY_PREEMPTION_DISTANCE):
            continue

        road_id = traci.vehicle.getRoadID(vehicle_id)
        if road_id in ("E3", "-E4"):
            return EW
        if road_id == "E5":
            return SOUTH
    return None


def main():
    q_values, epsilon, updates = load_model()
    traci.start([
        SUMO_BINARY,
        "-c", str(SUMO_CONFIG),
        "--step-length", str(STEP_LENGTH),
        "--delay", "50",
        "--lateral-resolution", "0.1",
    ])

    cumulative_reward = 0.0
    decision = 0
    print("\n=== Q-learning tabulaire pour le feu J6 ===")
    print(
        f"États appris: {len(q_values)} | mises à jour précédentes: {updates} "
        f"| exploration epsilon: {epsilon:.3f}\n"
    )

    try:
        while simulation_has_work():
            # Decisions are made only on green; a yellow phase already in
            # progress is completed before observing the state.
            if not settle_yellow([]):
                break

            state = get_state()
            q_ew, q_south = get_queues()
            emergency_group = ambulance_priority_group()
            forced = emergency_group is not None
            action = emergency_group if forced else choose_action(
                state, q_values, epsilon, q_ew, q_south
            )
            switching = current_green_group() != action

            reward, served_action, emergency_override = run_action(action)
            if reward is None:
                break
            cumulative_reward += reward
            forced = forced or emergency_override

            terminal = not simulation_has_work()
            next_state = get_state()
            if not forced:
                simulated_seconds = CONTROL_STEPS * STEP_LENGTH
                if switching:
                    simulated_seconds += YELLOW_SECONDS
                discount = 0.0 if terminal else GAMMA ** (
                    simulated_seconds / (CONTROL_STEPS * STEP_LENGTH)
                )
                update_q_value(
                    q_values, state, served_action, reward, next_state, discount
                )
                updates += 1
                epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)
                save_model(q_values, epsilon, updates)

            q_ew, q_south = get_queues()
            decision += 1
            label = (
                "PRIORITÉ URGENCE" if forced
                else f"action={ACTION_NAMES[served_action]}"
            )
            print(
                f"Décision {decision:3d} | {label:18s} | "
                f"EW arrêté={q_ew:2d} Sud arrêté={q_south:2d} | "
                f"récompense={reward:6.2f} cumul={cumulative_reward:8.2f} "
                f"| epsilon={epsilon:.3f}"
            )
    finally:
        try:
            save_model(q_values, epsilon, updates)
        finally:
            traci.close()

    print(f"\n=== Terminé : {updates} mises à jour Q sauvegardées dans {Q_TABLE_PATH.name} ===")


if __name__ == "__main__":
    main()
