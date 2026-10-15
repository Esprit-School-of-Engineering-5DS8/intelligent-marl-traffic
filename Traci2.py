# Step 1: Add modules to provide access to specific libraries and functions
import os # Module provides functions to handle file paths, directories, environment variables
import sys # Module provides access to Python-specific system parameters and functions

# Step 2: Establish path to SUMO (SUMO_HOME)
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

# Step 3: Add Traci module to provide access to specific libraries and functions
import traci # Module for controlling SUMO simulations via TraCI

# Step 4: Define SUMO configuration
Sumo_config = [
    'sumo-gui',
    '-c', 'Traci.sumocfg',
    '--step-length', '0.05',
    '--delay', '1000',
    '--lateral-resolution', '0.1'
]

# Step 5: Open connection between SUMO and Traci
traci.start(Sumo_config)

# Step 6: Define Variables
moved = False   # drapeau pour ne déplacer qu'une seule fois

# Step 7: Define Functions
def process_vehicles():
    global moved
    if 't_0' in traci.vehicle.getIDList():
        if not moved:
            # On déplace t_0 UNE SEULE FOIS
            traci.vehicle.moveToXY('t_0', 'E3', '0', -30, -17.7, angle=90, keepRoute=2)
            moved = True
            print(">>> Véhicule t_0 téléporté une seule fois")
        
        # Ensuite on lit juste la position et l'angle
        position = traci.vehicle.getPosition('t_0')
        angle = traci.vehicle.getAngle('t_0')
        speed = traci.vehicle.getSpeed('t_0')
        print(f"t_0 → Pos: {position}, Angle: {angle:.1f}°, Speed: {speed:.2f} m/s")
# Step 8: Take simulation steps until there are no more vehicles in the network
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep() # Move simulation forward 1 step
    # Here you can decide what to do with simulation data at each step
    process_vehicles()
    
# Step 9: Close connection between SUMO and Traci
traci.close()

