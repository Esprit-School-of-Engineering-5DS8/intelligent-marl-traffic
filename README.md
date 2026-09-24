# CoTraffic - cooperative multi-agent traffic signal control

Final-year AI & Data Science project, *Intelligent Multi-Agent Traffic Management*.

Every signalised intersection is an autonomous reinforcement-learning agent. Agents
share one policy (PPO with parameter sharing), exchange short messages with their
neighbours, go through a safety shield that makes unsafe signal sequences impossible,
and are trained to reduce person-weighted waiting time while accounting for CO2,
emergency vehicles and pedestrians. They are compared with fixed-time (Webster),
actuated and Max-Pressure control on a synthetic grid and on a real district imported
from OpenStreetMap, under normal, peak, incident and emergency conditions.

Simulation: [SUMO](https://eclipse.dev/sumo/) 1.27 through libsumo. CPU only.

## Install

Python 3.10 or newer. SUMO comes from pip, no system install is needed.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU build, smaller
pip install -r requirements.txt
pip install -e . --no-deps
```

Check the installation (a few seconds):

```bash
python -m cotraffic smoke
python -m pytest -q
```

## Commands

The `Makefile` targets are aliases of the Python CLI, so everything also works on
Windows without `make`.

| make | python -m cotraffic ... | What it does |
|---|---|---|
| `make test` | `python -m pytest -q` | unit and integration tests |
| `make lint` | `python -m ruff check src tests scripts dashboard` | style |
| `make smoke` | `smoke` | quick end-to-end run of every feature |
| `make networks` | `networks --all` | build the SUMO networks from `configs/networks` |
| | `episode --net grid4x4 --demand peak --seconds 3600` | one random-policy episode (sanity check) |

More commands are added with each milestone (training, evaluation, figures); see
`docs/PROGRESS.md`.

## Repository layout

```
configs/        protocol.yaml (timing, episode protocol), networks/, demand/, scenarios/,
                agents/, experiments/, vehicles.yaml
src/cotraffic/  networks/ demand/ scenarios/ envs/ controllers/ training/ evaluation/
                analysis/ forecasting/ explainability/
sumo_files/     generated networks and route bundles (reproducible from configs)
results/        raw/ (one CSV per run), summary/, logs/, training/
figures/        report figures (PNG + SVG)
docs/           Design Thinking, decisions (ADR), FAILURES, EXPERIMENT_JOURNAL, PROGRESS
tests/          pytest suite
```

## Reproducibility

- Every parameter lives in `configs/`; the code has no magic numbers.
- Demand, SUMO and learning are seeded. Test, validation and training seeds are disjoint
  (`src/cotraffic/envs/episodes.py`).
- Each traffic component (cars, buses, emergency vehicles, pedestrians) draws from its
  own random stream, so scenarios run with the same seed share the same car demand.

## Results

Results are produced by the evaluation pipeline and summarised in
`results/summary/REPORT_TABLES.md` once the experiment matrix has run (milestone M7).
