<<<<<<< HEAD
## Welcome to SUMO Traffic Simulator Tutorial

## Introduction
This is a wide range of tutorial codes for SUMO traci applications ranging from. You can find the video tutorials in our website [Link to Videos in Our Website](https://roadwayvr.com/)

## 1. Vehicle Value Retrieval (for example, extracting trajectory of all cars)
   
<img src="https://github.com/user-attachments/assets/e5b251e0-e5d1-4f4f-94d8-dedb2bd80eb6" width="600" alt="Thumbnail">

## 2. Change a vehicle's state (For example, move Ego Car)

<img src="https://github.com/user-attachments/assets/b85ce87f-c5ca-4699-9e0f-4d80b73d59ab" width="600" alt="Thumbnail">
   
## 3. Get road network stats before running simulation (SUMO Lib)

<img src="https://github.com/user-attachments/assets/9d56c33b-5d64-4d70-b348-cf6593196945" width="600" alt="Thumbnail">
   
## 4. SUMO Traffic Light: Signal Preemption/Priority for Emergency Vehicles 

<img src="https://github.com/user-attachments/assets/000826b8-2a15-4a08-9abb-dcf43d275be1" width="600" alt="Thumbnail">

## 5. SUMO Vehicle Type - Car Following Model and Lane Changing Model

<img src="https://github.com/user-attachments/assets/0271d52b-8539-4486-a4d4-5f6c107d97b7" width="600" alt="Thumbnail">

## 6 - 8.  Developing Two Reinforcement Learning Algorithms (Q-Learning and Deep Q-Learning)

<img src="https://github.com/user-attachments/assets/c9610bf3-b286-44e2-8c2b-5a8db64ae0b7" width="600" alt="Thumbnail">

## 9.  Developing Mixed Traffic Environment for Autonomous Vehicles and Normal Cars

<img src="https://github.com/user-attachments/assets/23601524-d49e-496a-af1e-e7c554bd6008" width="600" alt="Thumbnail">

## 10.  To Be Continued
=======
# Intelligent Multi-Agent Urban Traffic Management

> **Course:** Advanced Data Science Project - Esprit School of Engineering (5DS8)  
> **Supervisor:** Islem Maiti  
> **Team:** Hazem Mrad, Bilel Brini, Lina Haddad, Amen Allah Ben Aissa, Rami Ben Slimen

---

## 🎯 Project Overview

This project explores how **intelligent autonomous agents** and **data science** can be combined to build a smarter, more adaptive urban traffic management system.

We use [Eclipse SUMO](https://sumo.dlr.de) as the microscopic traffic simulator and implement a **Multi-Agent Reinforcement Learning (MARL)** framework where each intersection is controlled by an independent agent that learns to minimize congestion, support pedestrian safety, and coordinate emergency vehicle priority.

**Challenge Question:**  
> *"How might we use data and intelligent agents to make urban traffic more efficient, adaptive, and sustainable?"*

---

## 🗺️ Roadmap

| Phase | Scenario | Status |
|-------|----------|--------|
| Phase 1 | 2x2 Grid - toy validation | 🟡 In Progress |
| Phase 2 | 3x3 Grid - main benchmark | 🟠 In Progress |
| Phase 3 | Monaco - real-world use case | 🔴 Planned |

---

## 📁 Repository Structure

```
intelligent-marl-traffic/
├── scenarios/
│   ├── grid_2x2/        # Phase 1 - 4-intersection toy grid
│   ├── grid_3x3/        # Phase 2 - 9-intersection benchmark
│   └── monaco/          # Phase 3 - Real OSM network (TBD)
├── agents/              # Traffic light controller policies
│   └── rl/              # Deep RL agents (DQN, PPO)
├── environment/         # Core multi-agent SUMO environment
├── baselines/           # Fixed-time & actuated reference controllers
├── forecasting/         # Travel time, pedestrian & EV prediction models
├── evaluation/          # Batch experiments, KPI comparison, plots
├── notebooks/           # Analysis and reporting notebooks
├── docs/                # Design Thinking documentation
└── results/             # Auto-generated (gitignored)
```

---

## 🚀 Quick Start

### Prerequisites
- [Eclipse SUMO](https://sumo.dlr.de/docs/Installing/index.html) ≥ 1.20
- Python ≥ 3.10
- WSL Ubuntu (optional, for Linux-native SUMO)

### Setup
```bash
git clone https://github.com/Esprit-School-of-Engineering-5DS8/intelligent-marl-traffic.git
cd intelligent-marl-traffic
pip install -r requirements.txt
```

### Run the 2x2 scenario (Phase 1 Validation)
```powershell
cd scenarios/grid_2x2
python runner.py --mode max_pressure --steps 1000

# Or with GUI
python runner.py --gui --mode max_pressure --steps 1000
```

### Run the 3x3 scenario (Phase 2 Grid)
```powershell
cd scenarios/grid_3x3
python runner.py --mode max_pressure --steps 1000

# Or with GUI
python runner.py --gui --mode sumo_default --steps 1000
```

### Available controller modes
| Mode | Description |
|------|-------------|
| `sumo_default` | SUMO built-in pre-timed logic (baseline) |
| `fixed` | Fixed-time cycle coordination |
| `max_pressure` | Adaptive queue-pressure heuristic |
| `custom` | Hook for your RL / custom policy |

---

## 👥 Team & Responsibilities

| Member | Role | Objectives |
|--------|------|------------|
| Hazem Mrad | Simulation & Environment Lead | F1, F2 - SUMO scenarios, data pipeline, baselines |
| Bilel Brini | RL Agent Developer | F3, M1, M3 - DQN/PPO, multi-agent, emissions |
| Lina Haddad | Pedestrian & Safety Module | S1, S2, S3 - pedestrian-adaptive signals, safety |
| Amen Allah Ben Aissa | Emergency Priority | E1, E2 - green corridor, EV detection & ETA |
| Rami Ben Slimen | Evaluation & Forecasting | F4, F5, M2 - experiments, visualization, reporting |

---

## 📊 Key Metrics Tracked

- `avg_speed_m_s` - Network mean vehicle speed
- `total_waiting_time_s` - Total vehicle delay per step
- `arrived_vehicles` - Throughput (vehicles reaching destination)
- `co2_mg_s` - CO2 emissions
- `fuel_ml_s` - Fuel consumption

---

## 🎨 Design Thinking Process

This project follows the **Design Thinking** methodology:

| Phase | Status | Deliverable |
|-------|--------|-------------|
| Empathize | ✅ Done | Personas: Mehdi (driver), Sarra (pedestrian), Sonia (EV responder), Karim (operator) |
| Define | ✅ Done | Problem statement, POV statements, HMW questions, success criteria |
| Ideate | 🟡 In Progress | Approach shortlist, chosen direction |
| Prototype | 🟡 In Progress | Working SUMO + MARL prototype |
| Test | 🔴 Planned | Experiment results, data-driven evidence vs baseline |

---

## 📜 License

MIT License - see [LICENSE](LICENSE)
>>>>>>> 0530456505d88b1e35a0baa94c9f302cba81d1ab

