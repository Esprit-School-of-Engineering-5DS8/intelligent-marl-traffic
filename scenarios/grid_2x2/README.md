# 2x2 Grid Multi-Agent Urban Traffic Management Scenario

Phase 1 validation scenario built for **Eclipse SUMO** (compatible with native Windows and WSL Ubuntu), specifically designed for rapid testing, prototyping, and debugging of multi-agent reinforcement learning (MARL) and heuristic traffic signal control algorithms.

---

## 1. Network Topology (2x2 Grid)

- **Intersections**: 4 signalized intersections in a 2x2 layout:
  ```
  [A1] --- [B1]
    |        |
  [A0] --- [B0]
  ```
- **Geometry**:
  - Distance between junctions: `200 meters`
  - Attached feeder boundary roads: `100 meters` (providing incoming and outgoing entry points on all 4 borders)
  - Lanes: `2 lanes` in each direction (`50 km/h` / `13.89 m/s` speed limit)
- **Signal Control**:
  - Every intersection (`A0`, `A1`, `B0`, `B1`) has a 4-phase traffic light logic:
    - Phase 0: North-South Green (`GGGggrrrrrGGGggrrrrr`)
    - Phase 1: North-South Yellow (`yyyyyrrrrryyyyyrrrrr`)
    - Phase 2: East-West Green (`rrrrrGGGggrrrrrGGGgg`)
    - Phase 3: East-West Yellow (`rrrrryyyyyrrrrryyyyy`)

---

## 2. Directory Structure

```
scenarios/grid_2x2/
├── grid2x2.net.xml           # Road network generated via netgenerate
├── grid2x2.rou.xml           # Vehicle demand & synthetic routes
├── grid2x2.sumocfg           # SUMO simulation configuration file
├── viewsettings.xml          # GUI camera position & display settings
├── build_network.py          # Script to regenerate / customize the network
├── generate_routes.py        # Script to generate traffic demand
├── runner.py                 # TraCI Python controller with Multi-Agent interface
├── simulation_metrics.csv    # Automatically logged step-by-step performance metrics
├── run.ps1                   # PowerShell launcher (Windows native or WSL)
├── run.bat                   # Windows batch launcher shortcut
├── run.sh                    # Bash launcher for Linux / WSL
└── README.md                 # This documentation
```

---

## 3. How to Run the Simulation

### Option A: Direct Windows PowerShell (Recommended for GUI)
```powershell
cd scenarios\grid_2x2

# Run headless with Max-Pressure (fast)
python runner.py --mode max_pressure --steps 500

# Run with SUMO-GUI
python runner.py --gui --mode max_pressure --steps 1000

# Using PowerShell script launcher
.\run.ps1 -gui -mode max_pressure -steps 1000
```

### Option B: From WSL Ubuntu Terminal
```bash
cd /mnt/c/Users/Hazem/Desktop/SUMO/scenarios/grid_2x2

# Headless simulation
./run.sh --nogui --steps 1000

# Rebuild network & routes from scratch
./run.sh --rebuild
```

---

## 4. Supported Control Modes

| Mode | Description |
|---|---|
| `sumo_default` | Uses SUMO's native pre-timed traffic light cycle |
| `fixed` | Rule-based synchronous 60s cycle (30s NS green, 30s EW green) |
| `max_pressure` | Decentralized adaptive agent selecting green for the direction with greatest halting queue |
| `custom` | Multi-agent extension hook ready for RL agents (Q-learning, PPO, MADDPG) |

---

## 5. Logged Metrics

Simulation output is saved to `simulation_metrics.csv`:
- `step`: Current simulation second
- `active_vehicles`: Vehicles presently in the network
- `arrived_vehicles`: Vehicles completing their trip in this step
- `avg_speed_m_s`: Network-wide average vehicle velocity (m/s)
- `total_waiting_time_s`: Cumulative waiting time of all halted vehicles
- `co2_mg_s`: Total CO2 emissions (mg/s)
- `fuel_ml_s`: Fuel consumption rate (ml/s)
