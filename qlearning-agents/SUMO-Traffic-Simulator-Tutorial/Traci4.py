# Step 1: Modules
import os
import sys

# Step 2: SUMO_HOME
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# Step 3: Traci
import traci

# Step 4: Configuration (on utilise ton Traci.sumocfg existant)
Sumo_config = [
    'sumo-gui',
    '-c', 'Traci.sumocfg',
    '--step-length', '0.05',
    '--delay', '200',
    '--lateral-resolution', '0.1'
]

# Step 5: Démarrer
traci.start(Sumo_config)

print("=== Simulation démarrée ===")
print("Cherche les véhicules d'urgence...")

# Step 6 & 7: Boucle principale
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()

    # Cherche les véhicules d'urgence
    for veh_id in traci.vehicle.getIDList():
        veh_type = traci.vehicle.getTypeID(veh_id)

        if veh_type == "emergency":
            # Position et vitesse
            edge = traci.vehicle.getRoadID(veh_id)
            speed = traci.vehicle.getSpeed(veh_id)
            pos = traci.vehicle.getPosition(veh_id)

            print(f"[URGENCE] {veh_id} | Edge: {edge} | Speed: {speed:.1f} m/s | Pos: {pos}")

            # Prochain feu de circulation
            next_tls = traci.vehicle.getNextTLS(veh_id)

            if next_tls:
                tlsID, linkIndex, distance, state = next_tls[0]
                print(f"   → Prochain feu: {tlsID} | Distance: {distance:.1f} m | État actuel: {state}")

                # Si l'ambulance est à moins de 40 mètres du feu → forcer le vert
                if distance < 40:
                    current_phase = traci.trafficlight.getPhase(tlsID)
                    # On force la phase 0 (vert pour la direction E3→E4)
                    if current_phase != 0:
                        traci.trafficlight.setPhase(tlsID, 0)
                        print(f"   >>> FEU {tlsID} FORCÉ AU VERT (phase 0) pour l'ambulance !")

traci.close()
print("=== Simulation terminée ===")
