# Monaco Real-World Scenario (Phase 3)

This directory contains the **Monaco SUMO Traffic (MoST) Scenario**, the official research-grade microscopic traffic simulation benchmark of the Principality of Monaco.

> **Citation:**  
> L. Codeca, J. Härri, *"Towards Multimodal Mobility Simulation of C-ITS: The Monaco SUMO Traffic Scenario"*, IEEE Vehicular Networking Conference (VNC), 2017.

---

## 🏙️ Network Specifications

| Property | Value |
|---|---|
| **Controlled Intersections** | 12 real-world signalized junctions (`134872`, `cluster_135794_135910`, etc.) |
| **Physical Edges** | Over 1,700 real city streets with 3D elevations and coastlines |
| **Sidewalks & Crossings** | Complete pedestrian sidewalk network and signalized crossings |
| **Multi-Modal Traffic** | Commuter cars, public transit buses, trains, commercial delivery, and emergency/special vehicles |
| **Topology Source** | OpenStreetMap + MoST Scenario |

---

## 🚀 Running the Monaco Scenario

### 1. Quickstart MARL Simulation
```powershell
# Headless run for 100 steps
python examples/marl_quickstart.py --scenario monaco --steps 100

# With SUMO-GUI
python examples/marl_quickstart.py --scenario monaco --steps 100 --gui --delay 150
```

### 2. Benchmark Reference Baselines
```powershell
# Benchmark Fixed-Time, Actuated, and Max-Pressure on real Monaco network
python evaluation/benchmark_baselines.py --scenario monaco --steps 200
```

---

## 🤖 Multi-Agent RL Compatibility

The standardized [`SumoMARLEnv`](../../environment/multi_agent_env.py) dynamically discovers all 12 Monaco junctions and sets up vectorized observation spaces (`spaces.Box`) and action spaces (`spaces.Discrete`) without requiring any manual hardcoding.
