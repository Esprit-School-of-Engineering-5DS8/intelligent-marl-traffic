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
Windows without `make`. `python -m cotraffic <command> --help` lists the options.

| make | python -m cotraffic ... | What it does |
|---|---|---|
| `make test` | (`python -m pytest -q`) | unit and integration tests |
| `make lint` | (`python -m ruff check src tests scripts dashboard`) | style |
| `make smoke` | `smoke` | quick end-to-end run of every feature (a few minutes) |
| `make networks` | `networks --all` | build the SUMO networks from `configs/networks` |
| | `calibrate-demand --net grid4x4 --scales ...` | demand calibration sweep (tuning seeds) |
| `make calibrate` | `calibrate --net grid4x4` | reward normalisation constants from baseline runs |
| `make train` | `train --agent coop --net grid4x4 --seed 1` | train one variant (resumes from its last checkpoint) |
| `make select` | `select` | choose the checkpoint of each run on validation seeds |
| | `validate --agents ind coop --baselines mp` | compare variants on validation seeds (design choices) |
| `make evaluate` | `evaluate --experiment full_matrix --jobs 2` | run an experiment matrix (skips runs already done) |
| `make aggregate` | `aggregate` | means, bootstrap CIs, Mann-Whitney U + Holm, Cliff's delta |
| `make figures` | `figures` | the report figures, PNG + SVG, in `figures/` |
| `make tables` | `tables` | `results/summary/REPORT_TABLES.md` |
| `make forecast` | `forecast --net grid4x4` | inflow forecasting dataset, models and scores |
| `make explain` | `explain --agent coop_full --net grid4x4` | decision log and feature-group importance |
| `make dashboard` | (`streamlit run dashboard/app.py`) | interactive results (no SUMO needed) |
| `make demo` | (`python scripts/demo_side_by_side.py`) | two sumo-gui windows: baseline vs COOP-FULL |
| `make reproduce` | (`bash scripts/reproduce_all.sh`) | everything, from networks to tables |

`docs/RUN_PLAN.md` explains how to split training and evaluation between machines,
Kaggle (`notebooks/kaggle_train.ipynb`) and Colab (`notebooks/colab_train.ipynb`).

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
