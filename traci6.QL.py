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

from traci6_pedestrian_agent import PedestrianSignalAgent


# ====================== CONFIG ======================
TLS_ID = "J6"
SUMO_CONFIG = Path(__file__).with_name("Traci.sumocfg")
SUMO_BINARY = os.environ.get("SUMO_BINARY", "sumo-gui")
STEP_LENGTH = 0.1
CONTROL_STEPS = 100             # Re-evaluate queues and emergency vehicles every 10 s.
YELLOW_SECONDS = 3.0
MAX_SIMULATION_STEPS = 12000    # Hard limit: 20 simulated minutes at this step length.
QUEUE_IMBALANCE_OVERRIDE = 3
EMERGENCY_PREEMPTION_DISTANCE = 120.0
Q_TABLE_PATH = Path(os.environ.get(
    "TRACI6_Q_TABLE_PATH",
    Path(__file__).with_name("traci6_qtable_v3.json"),
))

ALPHA = 0.1
GAMMA = 0.9
EPSILON_START = 0.2
EPSILON_MIN = 0.02
EPSILON_DECAY = 0.995

EW_THROUGH_RIGHT, NS_THROUGH_RIGHT, EW_LEFT, NS_LEFT = range(4)
ACTION_NAMES = (
    "E/O tout droit-droite",
    "N/S tout droit-droite",
    "E/O gauche",
    "N/S gauche",
)
ACTION_LANES = {
    EW_THROUGH_RIGHT: (("E3", 1), ("E3", 2), ("-E4", 1), ("-E4", 2)),
    NS_THROUGH_RIGHT: (
        ("E5", 1), ("E5", 2),
        ("-E6", 1), ("-E6", 2),
    ),
    EW_LEFT: (("E3", 3), ("-E4", 3)),
    NS_LEFT: (("E5", 3), ("-E6", 3)),
}
YELLOW_STEPS = round(YELLOW_SECONDS / STEP_LENGTH)
ALL_RED_CLEARANCE_STEPS = round(1.0 / STEP_LENGTH)
ACTION_COUNT = len(ACTION_NAMES)
VEHICLE_SIGNAL_STATES = {
    EW_THROUGH_RIGHT: ("rrrGGrrrrGGr", "rrryyrrrryyr"),
    NS_THROUGH_RIGHT: ("GGrrrrGGrrrr", "yyrrrryyrrrr"),
    EW_LEFT: ("rrrrrGrrrrrG", "rrrrryrrrrry"),
    NS_LEFT: ("rrGrrrrrGrrr", "rryrrrrryrrr"),
}
CROSSING_LANES = (
    ("nord", "E6", ":J6_w1_0", ":J6_c0_0"),
    ("est", "E4", ":J6_w2_0", ":J6_c1_0"),
    ("sud", "-E5", ":J6_w3_0", ":J6_c2_0"),
    ("ouest", "-E3", ":J6_w0_0", ":J6_c3_0"),
)
ACTIVE_SIGNAL_GROUP = EW_THROUGH_RIGHT
SIGNAL_IS_YELLOW = False


def load_model():
    if not Q_TABLE_PATH.exists():
        return {}, EPSILON_START, 0

    model = json.loads(Q_TABLE_PATH.read_text(encoding="utf-8"))
    if not isinstance(model, dict):
        raise ValueError(f"Unsupported Q-learning model format in {Q_TABLE_PATH}")
    if model.get("version") in (1, 2):
        print(
            "Ancien modèle Q-learning détecté : un nouveau modèle est utilisé "
            "pour le réseau avec passage piéton."
        )
        return {}, EPSILON_START, 0
    if model.get("version") != 3:
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
        "version": 3,
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


def set_vehicle_signal(group, stage):
    """Set one vehicle movement green or yellow and keep every crossing red."""
    global ACTIVE_SIGNAL_GROUP, SIGNAL_IS_YELLOW
    if group not in VEHICLE_SIGNAL_STATES or stage not in ("green", "yellow"):
        raise ValueError(f"Unsupported vehicle signal state: {group}, {stage}")

    link_count = len(traci.trafficlight.getControlledLinks(TLS_ID))
    if link_count < 12:
        raise RuntimeError(
            f"Expected at least 12 vehicle links at {TLS_ID}, got {link_count}"
        )
    state_index = 1 if stage == "yellow" else 0
    vehicle_state = VEHICLE_SIGNAL_STATES[group][state_index]
    state = vehicle_state + "r" * (link_count - len(vehicle_state))
    traci.trafficlight.setRedYellowGreenState(TLS_ID, state)
    ACTIVE_SIGNAL_GROUP = group
    SIGNAL_IS_YELLOW = stage == "yellow"


def set_crossing_signals(agents, color):
    """Give requested crossings a signal while all other J6 links stay red."""
    link_count = len(traci.trafficlight.getControlledLinks(TLS_ID))
    state = ["r"] * link_count
    for agent in agents:
        if not 0 <= agent.link_index < link_count:
            raise RuntimeError(
                f"Invalid signal link {agent.link_index} for pedestrian crossing "
                f"{agent.name}"
            )
        state[agent.link_index] = color
    traci.trafficlight.setRedYellowGreenState(TLS_ID, "".join(state))


def set_all_red_signal():
    """Stop every vehicle and pedestrian movement at J6."""
    global SIGNAL_IS_YELLOW
    link_count = len(traci.trafficlight.getControlledLinks(TLS_ID))
    traci.trafficlight.setRedYellowGreenState(TLS_ID, "r" * link_count)
    SIGNAL_IS_YELLOW = False


def create_pedestrian_agents():
    controlled_links = traci.trafficlight.getControlledLinks(TLS_ID)
    agents = []
    for name, approach_edge, waiting_lane, crossing_lane in CROSSING_LANES:
        link_index = None
        for index, connections in enumerate(controlled_links):
            if any(
                from_lane == waiting_lane and to_lane == crossing_lane
                for from_lane, to_lane, _ in connections
            ):
                link_index = index
                break
        if link_index is None:
            raise RuntimeError(
                f"Could not find signal link for pedestrian crossing {name}"
            )
        agents.append(
            PedestrianSignalAgent(
                traci,
                name,
                approach_edge,
                waiting_lane,
                crossing_lane,
                link_index,
                STEP_LENGTH,
            )
        )
    return agents


def get_queues():
    """Return stopped-vehicle counts for each signalized movement group."""
    return tuple(
        sum(
            traci.lane.getLastStepHaltingNumber(f"{edge_id}_{lane_index}")
            for edge_id, lane_index in lanes
        )
        for lanes in (ACTION_LANES[action] for action in range(ACTION_COUNT))
    )


def current_green_group():
    return ACTIVE_SIGNAL_GROUP


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
    queue_buckets = (queue_bucket(queue) for queue in get_queues())
    return ",".join((*map(str, queue_buckets), str(current_green_group())))


def choose_action(state, q_values, epsilon, queues):
    # Do not let a stale/undertrained Q-value keep a clearly longer queue red.
    longest_queue = max(queues)
    if longest_queue - min(queues) >= QUEUE_IMBALANCE_OVERRIDE:
        return random.choice(
            [action for action, queue in enumerate(queues) if queue == longest_queue]
        )

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
    reward_samples.append(-sum(get_queues()))
    return True


def settle_yellow(reward_samples, restore_green=True):
    """Finish a yellow phase before the next Q-learning decision."""
    if not SIGNAL_IS_YELLOW:
        return True
    for _ in range(YELLOW_STEPS):
        if not advance_one_step(reward_samples):
            return False
    if restore_green:
        set_vehicle_signal(current_green_group(), "green")
    else:
        set_all_red_signal()
    return True


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
            set_vehicle_signal(current_group, "yellow")
            if not settle_yellow(reward_samples):
                return None, target_group, emergency_override
            emergency_group = ambulance_priority_group()
            if emergency_group is not None:
                if not emergency_override:
                    print(f"  *** Priorité ambulance : {ACTION_NAMES[emergency_group]}")
                target_group = emergency_group
                emergency_override = True
            if current_green_group() != target_group:
                set_vehicle_signal(target_group, "green")

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
    """Return the signal group needed by an emergency vehicle near either light."""
    for vehicle_id in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(vehicle_id) != "emergency":
            continue
        next_tls = traci.vehicle.getNextTLS(vehicle_id)
        if (not next_tls or next_tls[0][0] != TLS_ID
                or next_tls[0][2] >= EMERGENCY_PREEMPTION_DISTANCE):
            continue

        road_id = traci.vehicle.getRoadID(vehicle_id)
        lane_index = traci.vehicle.getLaneIndex(vehicle_id)
        if road_id in ("E5", "-E5"):
            return NS_LEFT if lane_index == 3 else NS_THROUGH_RIGHT
        if next_tls[0][0] != TLS_ID:
            continue
        if road_id in ("E3", "-E4"):
            return EW_LEFT if lane_index == 3 else EW_THROUGH_RIGHT
        if road_id == "-E6":
            return NS_LEFT if lane_index == 3 else NS_THROUGH_RIGHT
    return None


def service_pedestrian_requests(pedestrian_agents):
    """Serve ready crossings together, sharing a single vehicle-red interval."""
    requested_agents = [
        agent for agent in pedestrian_agents if agent.has_request()
    ]
    if not requested_agents:
        return False

    resume_group = current_green_group()
    set_vehicle_signal(resume_group, "yellow")
    if not settle_yellow([], restore_green=False):
        return False

    for _ in range(ALL_RED_CLEARANCE_STEPS):
        if not simulation_has_work():
            return False
        traci.simulationStep()

    emergency_group = ambulance_priority_group()
    if emergency_group is not None:
        set_vehicle_signal(emergency_group, "green")
        return False

    requested_agents = [
        agent for agent in requested_agents if agent.has_request()
    ]
    if not requested_agents:
        set_vehicle_signal(resume_group, "green")
        return False

    set_crossing_signals(requested_agents, "G")

    def advance_clearance_step():
        if not simulation_has_work():
            return False
        traci.simulationStep()
        return True

    minimum_green_steps = max(
        agent.minimum_green_steps for agent in requested_agents
    )
    maximum_green_steps = max(
        agent.maximum_green_steps for agent in requested_agents
    )
    for step in range(maximum_green_steps):
        if (
            step >= minimum_green_steps
            and not any(
                agent.has_pedestrians_to_clear()
                for agent in requested_agents
            )
        ):
            break
        if not advance_clearance_step():
            return False
    else:
        waiting_names = ", ".join(
            agent.name
            for agent in requested_agents
            if agent.has_pedestrians_to_clear()
        )
        raise RuntimeError(
            f"Pedestrian crossings did not clear within "
            f"{maximum_green_steps * STEP_LENGTH:g} seconds: {waiting_names}"
        )

    set_all_red_signal()
    for _ in range(max(agent.clearance_steps for agent in requested_agents)):
        if not advance_clearance_step():
            return False

    emergency_group = ambulance_priority_group()
    set_vehicle_signal(
        emergency_group if emergency_group is not None else resume_group,
        "green",
    )
    return True


def main():
    q_values, epsilon, updates = load_model()
    traci.start([
        SUMO_BINARY,
        "-c", str(SUMO_CONFIG),
        "--step-length", str(STEP_LENGTH),
        "--delay", "50",
        "--lateral-resolution", "0.1",
    ])
    pedestrian_agents = create_pedestrian_agents()
    set_vehicle_signal(EW_THROUGH_RIGHT, "green")

    cumulative_reward = 0.0
    decision = 0
    print("\n=== Q-learning tabulaire pour le feu J6 ===")
    print("=== Agents piétons indépendants actifs sur les quatre passages ===")
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

            emergency_group = ambulance_priority_group()
            requested_agents = [
                agent for agent in pedestrian_agents if agent.has_request()
            ]
            if requested_agents and emergency_group is None:
                if service_pedestrian_requests(pedestrian_agents):
                    crossing_names = ", ".join(
                        agent.name for agent in requested_agents
                    )
                    print(
                        f"Agents piétons {crossing_names} : groupes servis "
                        "ensemble, "
                        "mouvements véhicules sécurisés au rouge."
                    )
                continue

            state = get_state()
            queues = get_queues()
            forced = emergency_group is not None
            action = emergency_group if forced else choose_action(
                state, q_values, epsilon, queues
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

            queues = get_queues()
            decision += 1
            label = (
                "PRIORITÉ URGENCE" if forced
                else f"action={ACTION_NAMES[served_action]}"
            )
            queue_summary = " ".join(
                f"{name}={queue}" for name, queue in zip(ACTION_NAMES, queues)
            )
            print(
                f"Décision {decision:3d} | {label:18s} | "
                f"files: {queue_summary} | "
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
