import os, sys, random, numpy as np, matplotlib.pyplot as plt

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

traci.start([
    'sumo-gui', '-c', 'Traci.sumocfg',
    '--step-length', '0.1', '--delay', '50', '--lateral-resolution', '0.1'
])

TLS_ID = "J6"
MIN_GREEN = 30          # temps minimum avant de re-changer (en steps)
last_switch = -MIN_GREEN
TOTAL_STEPS = 3000

step_history, reward_history, queue_history = [], [], []
cumulative_reward = 0.0

def get_queues():
    q_ew = (traci.edge.getLastStepVehicleNumber("E3") +
            traci.edge.getLastStepVehicleNumber("-E4"))
    q_s  = traci.edge.getLastStepVehicleNumber("E5")
    return q_ew, q_s

def force_ambulance():
    for veh in traci.vehicle.getIDList():
        if traci.vehicle.getTypeID(veh) == "emergency":
            try:
                nxt = traci.vehicle.getNextTLS(veh)
                if nxt and nxt[0][2] < 55:
                    traci.trafficlight.setPhase(TLS_ID, 0)
                    print(f"  *** AMBULANCE → VERT forcé (dist={nxt[0][2]:.0f}m)")
                    return True
            except: pass
    return False

print("\n=== Contrôle intelligent des feux (équitable) ===\n")

for step in range(TOTAL_STEPS):
    if traci.simulation.getMinExpectedNumber() <= 0 and step > 200:
        break

    # 1. Priorité ambulance
    if force_ambulance():
        traci.simulationStep()
        continue

    q_ew, q_s = get_queues()
    phase = traci.trafficlight.getPhase(TLS_ID)

    # 2. Décision équitable
    #    - Si Sud a autant ou plus de voitures → vert Sud (phase 2)
    #    - Sinon → vert EW (phase 0)
    if (step - last_switch) >= MIN_GREEN:
        if q_s >= q_ew and q_s > 0 and phase not in [2, 3]:
            traci.trafficlight.setPhase(TLS_ID, 2)
            last_switch = step
            print(f"  >>> VERT pour le SUD  (Sud={q_s} vs EW={q_ew})")
        elif q_ew > q_s and phase not in [0, 1]:
            traci.trafficlight.setPhase(TLS_ID, 0)
            last_switch = step
            print(f"  >>> VERT pour EW     (EW={q_ew} vs Sud={q_s})")

    traci.simulationStep()

    q_ew2, q_s2 = get_queues()
    reward = -(q_ew2 + q_s2)
    cumulative_reward += reward

    if step % 40 == 0:
        print(f"Step {step:4d} | EW:{q_ew2:2d}  Sud:{q_s2:2d} | Phase:{traci.trafficlight.getPhase(TLS_ID)} | Cumul:{cumulative_reward:7.1f}")
        step_history.append(step)
        reward_history.append(cumulative_reward)
        queue_history.append(q_ew2 + q_s2)

traci.close()
print("\n=== Terminé ===")
