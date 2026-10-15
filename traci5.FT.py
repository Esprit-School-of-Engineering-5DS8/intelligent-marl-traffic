# Step 1: Modules
import os
import sys
import matplotlib.pyplot as plt

# Step 2: SUMO_HOME
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# Step 3: Traci
import traci

# Step 4: Configuration (ton Sample)
Sumo_config = [
    'sumo-gui',
    '-c', 'Traci.sumocfg',
    '--step-length', '0.1',
    '--delay', '50',
    '--lateral-resolution', '0.1'
]

# Step 5: Démarrer
traci.start(Sumo_config)

# -------------------------
# Step 6: Variables
# -------------------------
TOTAL_STEPS = 500          # Nombre de pas (assez court pour le Sample)
TLS_ID = "J6"              # Feu de ton réseau Sample

step_history = []
reward_history = []
queue_history = []
cumulative_reward = 0.0

# -------------------------
# Step 7: Fonctions
# -------------------------
def get_queue_length():
    """Compte le nombre de véhicules sur les edges entrants du feu J6"""
    edges = ["E3", "-E4", "E5"]   # edges qui arrivent sur J6
    total = 0
    for e in edges:
        try:
            total += traci.edge.getLastStepVehicleNumber(e)
        except:
            pass
    return total

def get_reward(queue):
    """Récompense = -longueur de file (plus la file est petite, mieux c'est)"""
    return -float(queue)

# -------------------------
# Step 8: Boucle Fixed Timing
# -------------------------
print("\n=== Fixed Timing (Baseline) ===")
print("Le feu J6 tourne en mode normal (temps fixe). On mesure juste les files.\n")

for step in range(TOTAL_STEPS):
    traci.simulationStep()

    # Si plus de véhicules, on arrête plus tôt
    if traci.simulation.getMinExpectedNumber() <= 0:
        print(f"Plus de véhicules à l'étape {step}")
        break

    queue = get_queue_length()
    reward = get_reward(queue)
    cumulative_reward += reward

    # Enregistrer toutes les 20 étapes
    if step % 20 == 0:
        phase = traci.trafficlight.getPhase(TLS_ID)
        print(f"Step {step:4d} | Queue: {queue} | Phase: {phase} | Reward: {reward:.1f} | Cumul: {cumulative_reward:.1f}")
        step_history.append(step)
        reward_history.append(cumulative_reward)
        queue_history.append(queue)

traci.close()
print("\n=== Simulation terminée ===")

# -------------------------
# Step 9: Graphiques
# -------------------------
if step_history:
    plt.figure(figsize=(10, 4))

    plt.subplot(1, 2, 1)
    plt.plot(step_history, reward_history, marker='o')
    plt.xlabel("Step")
    plt.ylabel("Cumulative Reward")
    plt.title("Fixed Timing – Reward")
    plt.grid(True)

    plt.subplot(1, 2, 2)
    plt.plot(step_history, queue_history, marker='o', color='orange')
    plt.xlabel("Step")
    plt.ylabel("Queue Length")
    plt.title("Fixed Timing – Queue")
    plt.grid(True)

    plt.tight_layout()
    plt.show()
else:
    print("Pas assez de données pour afficher les graphiques.")
