# 3x3 Grid Multi-Agent Urban Traffic Management Scenario

Starter simulation scenario built for **Eclipse SUMO** inside **WSL Ubuntu**, specifically designed for testing and implementing multi-agent traffic signal control algorithms.

---

## 1. Network Topology (3x3 Grid)

- **Intersections**: 9 signalized intersections in a 3x3 layout:
  ```
  [A2] --- [B2] --- [C2]
    |        |        |
  [A1] --- [B1] --- [C1]
    |        |        |
  [A0] --- [B0] --- [C0]
  ```
- **Geometry**:
  - Distance between junctions: `200 meters`
  - Attached feeder boundary roads: `100 meters` (providing incoming and outgoing entry points on all 4 borders)
  - Lanes: `2 lanes` in each direction (`50 km/h` / `13.89 m/s` speed limit)
- **Signal Control**:
  - Every intersection (`A0` through `C2`) has a 4-phase traffic light logic:
    - Phase 0: North-South Green (`GGGggrrrrrGGGggrrrrr`)
    - Phase 1: North-South Yellow (`yyyyyrrrrryyyyyrrrrr`)
    - Phase 2: East-West Green (`rrrrrGGGggrrrrrGGGgg`)
    - Phase 3: East-West Yellow (`rrrrryyyyyrrrrryyyyy`)

---

## 2. Directory Structure

```
scenarios/grid_3x3/
├── grid3x3.net.xml           # Road network generated via netgenerate
├── grid3x3.rou.xml           # Vehicle demand & routes
├── grid3x3.sumocfg           # SUMO simulation configuration file
├── build_network.py          # Script to regenerate / customize the network
├── generate_routes.py        # Script to generate realistic traffic demand
├── runner.py                 # TraCI Python controller with Multi-Agent interface
├── simulation_metrics.csv    # Automatically logged step-by-step performance metrics
├── run.sh                    # One-click launcher for WSL Ubuntu
├── run.bat                   # Windows launcher shortcut
└── README.md                 # This guide
```

---

## 3. How to Run the Simulation

### Option A: From inside WSL Ubuntu Terminal
```bash
cd /mnt/c/Users/Hazem/Desktop/SUMO/scenarios/grid_3x3

# Run with SUMO GUI (opens graphical window via WSLg/X11)
./run.sh --gui

# Run fast headless simulation (ideal for training / batch runs)
./run.sh --nogui --steps 1000

# Compare different controllers:
./run.sh --mode sumo_default   # SUMO pre-timed baseline
./run.sh --mode fixed          # Fixed-time cycle baseline
./run.sh --mode max_pressure   # Decentralized adaptive queue-pressure agent
./run.sh --mode custom         # Custom policy hook (for your RL algorithms)
```

### Option B: From Windows PowerShell
```powershell
# In PowerShell:
cd scenarios\grid_3x3
python runner.py --mode max_pressure --steps 1000
```

---

## 4. Multi-Agent Architecture (`runner.py`)

The script [runner.py](runner.py) establishes an extensible multi-agent framework:

### 1. Agent State / Observation Space
For each intersection $i \in \{A0, \dots, C2\}$:
- **`lane_queues`**: Halting vehicle count ($speed < 0.1\text{ m/s}$) on all incoming approaches.
- **`total_queue`**: Sum of halting vehicles at the junction.
- **`lane_waiting`**: Accumulated waiting time on each lane.
- **`lane_counts`**: Total active vehicles on incoming lanes.
- **`current_phase`**: Active phase index (0 or 2).
- **`time_in_phase`**: Duration the current phase has been green.

### 2. Action Space & Safety Guardrails
- **Action 0**: Allocate green to North-South corridor.
- **Action 1**: Allocate green to East-West corridor.
- **Safety Enforcement**:
  - `min_green`: Minimum green duration (default: 10s) to prevent rapid signal flickering.
  - `yellow_time`: 3-second yellow clearance phase automatically triggered before switching traffic directions.

### 3. Step Reward Formulation
Standard multi-agent reward minimizing congestion and emissions:
$$R_i(t) = - \left(0.1 \times \text{total\_waiting\_time} + 1.0 \times \text{total\_queue}\right)$$

### 4. Metrics Logging
Step-by-step logs exported to `simulation_metrics.csv`:
- `active_vehicles`: Vehicles in transit.
- `arrived_vehicles`: Vehicles reaching their destinations (throughput).
- `avg_speed_m_s`: Mean vehicle speed across network.
- `total_waiting_time_s`: Total vehicle delay.
- `co2_mg_s`: Instantaneous carbon dioxide emissions.
- `fuel_ml_s`: Fuel consumption rate.

---

## 5. Next Steps for MARL Implementation

To train Reinforcement Learning agents (e.g. Independent Q-Learning, MAPPO, or Centralized Training Decentralized Execution - CTDE):
1. In `runner.py`, implement your policy inside `select_action_custom_rl(tls_id, state)`.
2. Connect an experience replay buffer or policy gradient loss using PyTorch.
3. Compare learning curves against the included `fixed` and `max_pressure` baselines.
