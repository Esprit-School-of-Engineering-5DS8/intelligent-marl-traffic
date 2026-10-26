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
├── src/cotraffic/       # Backend domain: env, controllers, training, evaluation, CLI
├── api/                 # FastAPI layer: data, runs, assistant, policy, live simulation
├── configs/             # protocol, networks, agents, scenarios, experiments (all parameters)
├── tests/               # pytest: API contract + domain checks
├── scripts/             # export/replay/reproduce entry points, explore/ research helpers
├── frontend/            # Single frontend (Vite)
│   ├── index.html       #   entry -> src/shell/app.js (control-room shell)
│   ├── styles.css       #   KEMETRA green/white tokens and layout
│   └── src/
│       ├── app/         #   React shell: router, nav, providers, theme
│       ├── features/    #   one folder per page (overview, live-map, agents, ...)
│       ├── shared/      #   api client, schemas, ui, charts, i18n, theme tokens
│       └── shell/       #   vanilla shell, Mapbox/3D env, benchmark island mount
├── docs/                # ARCHITECTURE, DESIGN_TOKENS, FRONTEND_ROADMAP, plans/
├── scenarios/monaco/    # source for the Monaco map JSON (extract_monaco_network.py)
├── sumo_files/          # generated SUMO networks (gitignored)
└── results/             # generated runs, summary, checkpoints (gitignored)
```

One backend (`src/cotraffic` + `api/`), one frontend (`frontend/`). The retired stacks
(`environment/`, `baselines/`, `evaluation/`, `agents/`, the Streamlit dashboard, the grid
scenario runners) are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §8.

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
pip install -r requirements.txt       # runtime
pip install -r requirements-dev.txt   # tests and linting (optional)
cd frontend && npm install
```

### Run a scenario (cotraffic CLI)
```bash
python -m cotraffic networks --net grid2x2           # build the SUMO network
python -m cotraffic episode --net grid2x2 --demand medium --seconds 600
python -m cotraffic evaluate --experiment llm_ab_quick --jobs 1
python -m cotraffic aggregate && python -m cotraffic tables
```

### Dashboard (live simulation + results)
```bash
uvicorn api.main:app --port 8000                     # backend
cd frontend && npm install && npm run dev            # Vite on :5173
python scripts/export_dashboard_data.py              # refresh served result files
```

### Controller methods
| `method` | Description |
|------|-------------|
| `ft` | Fixed-time Webster plan (baseline) |
| `act` | Actuated gap-out / max-out |
| `mp` | Max-Pressure adaptive heuristic |
| `ev_rule`, `ev_rule_mp` | Emergency pre-emption |
| `ped_rule_mp` | Pedestrian-aware MP |
| `ind`, `coop`, `coop_full`, `coop_eco*` | PPO learned variants (checkpoint required) |
| `dqn` | DQN comparison agent |
| `llm` | Batched language-model controller, MP fallback |

Full architecture, controller catalog and A/B protocol: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

