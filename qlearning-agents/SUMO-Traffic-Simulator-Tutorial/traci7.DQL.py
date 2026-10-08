import os, sys, random
import numpy as np
import matplotlib.pyplot as plt

# Désactive les logs TensorFlow
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
tf.get_logger().setLevel('ERROR')

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# ====================== CONFIG ======================
# Pour entraîner plus vite : remplace 'sumo-gui' par 'sumo'
traci.start([
    'sumo-gui', '-c', 'Traci.sumocfg',
    '--step-length', '1.0',       # 1.0 = beaucoup plus rapide (au lieu de 0.1)
    '--delay', '20',
    # '--lateral-resolution', '0.1'   <-- SUPPRIMÉ : c'est ça qui rame
])

TLS_ID = "J6"
TOTAL_STEPS = 2500
MIN_GREEN = 25
last_switch = -MIN_GREEN

ALPHA = 0.1
GAMMA = 0.9
EPSILON = 0.15

ACTIONS = [0, 1]
state_size = 3
action_size = 2

TRAIN_EVERY = 50         # entraîne tous les 50 steps (au lieu de 15)
BATCH_SIZE = 32

# ====================== DQN ======================
def build_model():
    model = keras.Sequential([
        layers.Input(shape=(state_size,)),
        layers.Dense(16, activation='relu'),
        layers.Dense(16, activation='relu'),
        layers.Dense(action_size, activation='linear')
    ])
    model.compile(loss='mse', optimizer=keras.optimizers.Adam(learning_rate=0.001))
    return model

dqn = build_model()

def to_array(state):
    return np.array(state, dtype=np.float32).reshape(1, -1)

# ====================== FONCTIONS ======================
def get_queues():
    q_ew = (traci.edge.getLastStepVehicleNumber("E3") +
            traci.edge.getLastStepVehicleNumber("-E4"))
    q_s  = traci.edge.getLastStepVehicleNumber("E5")
    return q_ew, q_s

def get_state():
    q_ew, q_s = get_queues()
    phase = traci.trafficlight.getPhase(TLS_ID)
    phase_group = 0 if phase in [0, 1] else 1
    return (float(q_ew), float(q_s), float(phase_group))

def get_reward(q_ew, q_s, phase):
    total = q_ew + q_s
    if q_ew > q_s and phase in [0, 1]:
        return -total + 1.5
    if q_s > q_ew and phase in [2, 3]:
        return -total + 1.5
    return -total - 0.5

def choose_action(state):
    if random.random() < EPSILON:
        return random.choice(ACTIONS)
    q_values = dqn(to_array(state), training=False).numpy()[0]
    return int(np.argmax(q_values))

def apply_action(action, step, q_ew, q_s):
    global last_switch
    if action == 1 and (step - last_switch) >= MIN_GREEN:
        if q_s >= q_ew:
            traci.trafficlight.setPhase(TLS_ID, 2)   # vert Sud
        else:
            traci.trafficlight.setPhase(TLS_ID, 0)   # vert EW
        last_switch = step
        print(f"  >>> Feu changé → phase {traci.trafficlight.getPhase(TLS_ID)}")

# ====================== AMBULANCE (corrigée) ======================
ambulance_active = False   # évite les prints en boucle

def force_ambulance():
    global ambulance_active
    for veh in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(veh) == "emergency":
            try:
                nxt = traci.vehicle.getNextTLS(veh)
                if nxt and nxt[0][2] < 30:      # 30 m au lieu de 55
                    lane = traci.vehicle.getLaneID(veh)
                    # Choisit la bonne phase selon la direction de l'ambulance
                    if lane.startswith(("E3", "-E4")):
                        target_phase = 0
                    elif lane.startswith("E5"):
                        target_phase = 2
                    else:
                        continue

                    # Ralentit l'ambulance à 50 km/h (~13.9 m/s)
                    traci.vehicle.setMaxSpeed(veh, 13.9)

                    if traci.trafficlight.getPhase(TLS_ID) != target_phase:
                        traci.trafficlight.setPhase(TLS_ID, target_phase)
                        print(f"  *** AMBULANCE → phase {target_phase} (dist={nxt[0][2]:.0f}m)")
                    ambulance_active = True
                    return True
            except Exception:
                pass
    ambulance_active = False
    return False

# ====================== REPLAY BUFFER ======================
replay_buffer = []

def store_transition(s, a, r, s2):
    replay_buffer.append((s, a, r, s2))
    if len(replay_buffer) > 2000:
        replay_buffer.pop(0)

def train_on_batch():
    if len(replay_buffer) < BATCH_SIZE:
        return
    batch = random.sample(replay_buffer, BATCH_SIZE)
    states = np.array([b[0] for b in batch], dtype=np.float32)
    next_states = np.array([b[3] for b in batch], dtype=np.float32)
    q_next = dqn(next_states, training=False).numpy()
    q_curr = dqn(states, training=False).numpy()
    targets = q_curr.copy()
    for i, (s, a, r, s2) in enumerate(batch):
        targets[i][a] = r + GAMMA * np.max(q_next[i])
    dqn.fit(states, targets, verbose=0, epochs=1)

# ====================== BOUCLE ======================
step_history, reward_history, queue_history = [], [], []
cumulative_reward = 0.0

print("\n=== Deep Q-Learning (DQN optimisé) + Priorité Ambulance ===\n")

for step in range(TOTAL_STEPS):
    if traci.simulation.getMinExpectedNumber() <= 0 and step > 200:
        break

    # Priorité ambulance
    if force_ambulance():
        traci.simulationStep()
        continue

    state = get_state()
    q_ew, q_s = get_queues()
    action = choose_action(state)
    apply_action(action, step, q_ew, q_s)

    traci.simulationStep()

    new_state = get_state()
    q_ew2, q_s2 = get_queues()
    phase = traci.trafficlight.getPhase(TLS_ID)
    reward = get_reward(q_ew2, q_s2, phase)
    cumulative_reward += reward

    store_transition(state, action, reward, new_state)

    if step % TRAIN_EVERY == 0:
        train_on_batch()

    if step % 40 == 0:
        print(f"Step {step:4d} | EW:{q_ew2:2d} Sud:{q_s2:2d} | Phase:{phase} | Act:{action} | Rew:{reward:5.1f} | Cumul:{cumulative_reward:7.1f}")
        step_history.append(step)
        reward_history.append(cumulative_reward)
        queue_history.append(q_ew2 + q_s2)

traci.close()
print("\n=== Fin DQN ===")

if step_history:
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(step_history, reward_history)
    plt.title("DQN – Reward cumulé")
    plt.grid(True)
    plt.subplot(1, 2, 2)
    plt.plot(step_history, queue_history, color="orange")
    plt.title("DQN – Queue totale")
    plt.grid(True)
    plt.tight_layout()
    plt.show()
