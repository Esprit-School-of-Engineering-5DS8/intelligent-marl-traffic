# Emergency Vehicle Priority — Showcase

Part of the Intelligent Multi-Agent Urban Traffic Management project.
Owner: Amen Allah Ben Aissa. Branch: `amen/ev-priority`.

Goal: ambulances cross the signalized grid with minimum delay (E1), with an
arrival-time model that predicts when they reach each light (E2), and an RL
layer that decides when to pre-empt (M4).

## Live demo (SUMO-GUI)

Priority policy — watch the red ambulance and the lights clearing for it:

```bash
/home/logmoon/.venvs/sumo/bin/python experiments/run_ev_priority.py \
    --scenario 3x3 --mode priority --gui --delay 100 --steps 1200 --no-summary
```

Fixed-time baseline — same scene, no priority:

```bash
/home/logmoon/.venvs/sumo/bin/python experiments/run_ev_priority.py \
    --scenario 3x3 --mode fixed --gui --delay 100 --steps 1200 --no-summary
```

Talking points while it runs:
- one ambulance every ~4 minutes, six fixed routes (both axes and turns)
- the rule reacts only within 150 m; yellow and minimum green always apply
- the stats block at the end is the same measurement used for the tables below

## Results (3x3 grid, one simulated hour, seed 42)

| Controller | EV time (s) | EV wait (s) | Red stops | Green arrivals (%) | Civilian wait (s/veh) | Throughput |
|---|---|---|---|---|---|---|
| Fixed-time | 55.7 | 17.8 | 15 | 72.9 | 3.35 | 1196 |
| Max-pressure | 55.5 | 15.2 | 23 | 56.2 | 2.03 | 1196 |
| **Priority (rule)** | **37.2** | **2.4** | **6** | **87.5** | **1.37** | 1196 |
| RL (safe margin) | 40.6 | 5.1 | 7 | 81.2 | 1.41 | 1197 |

![EV travel time](figures/fig1_ev_time.png)
![Civilian cost and service](figures/fig2_impact.png)

## Models

Both models share one feature extractor (12 inputs) used identically at
training and at run time: distance, speed, acceleration, leader gap, vehicles
on lane, signal state, time-to-switch, time-in-phase, turn flag, plus the
same signal/distance features of the first upcoming light (so second-light
predictions know about the first stop).

### ETA regression (`forecasting/ev_arrival_predictor.py`)

- input: 12 features for one (ambulance, upcoming light) pair
- output: seconds until the ambulance passes that light
- held-out error (runs never seen in training):

| | next light | second light |
|---|---|---|
| physics formula | 8.6 s | 33.7 s |
| **model** | **5.6 s** | **9.5 s** |

### Red-arrival classifier (same file)

- input: same 12 features
- output: probability the ambulance reaches that light on a non-green signal
- held-out AUC: 0.965 next light, 0.752 next light beyond 150 m, 0.715 second light
- status: trained and saved (`ev_red.joblib`) but **not wired into control** —
  it remains an evaluated signal for the report and future gating

![Model accuracy](figures/fig3_models.png)

### RL policy (`agents/emergency_rl.py`)

- one decision per (ambulance, light): pick one of six strategies — do
  nothing, pre-empt at 100/150/250 m, ETA-trigger at 8/15 s
- reward: −(ambulance waiting seconds + 0.25 × civilian wait-seconds)
- trained by fitted Q-iteration on 1,440 decision episodes (random + guided
  exploration), evaluated online with a safety margin over the best fixed
  strategy

Honest outcome: on this grid, held-out data justified no deviation from the
best fixed strategy (`dist_150`), so the safe policy converges to the
rule-based one. The pipeline works and is ready for harder scenarios (longer
corridors, heavier traffic); the negative result is supported by margin
sweeps and per-context reward tables.

## Limitations

- baselines measured on seed 42 only; priority has 3-seed support
- RL mode has a small residual mechanics gap vs priority mode (40.6 s vs
  37.2 s on seed 42) under investigation
- ETA-triggered early greens were neutral on this grid; kept behind an
  environment flag, default off

## Reproduce

```bash
# figures and results table
/home/logmoon/.venvs/sumo/bin/python experiments/make_report_figures.py

# rule-based priority (headless)
/home/logmoon/.venvs/sumo/bin/python experiments/run_ev_priority.py \
    --scenario 3x3 --mode priority --steps 3600 --seed 42

# ETA model training
/home/logmoon/.venvs/sumo/bin/python forecasting/ev_arrival_predictor.py \
    --data "results/ev/3x3_*_eta.csv"

# RL data collection, training, evaluation
/home/logmoon/.venvs/sumo/bin/python experiments/run_ev_priority.py \
    --scenario 3x3 --mode rl --steps 3600 --seed 100 --rl-epsilon 1.0 \
    --collect-rl --no-summary
/home/logmoon/.venvs/sumo/bin/python experiments/train_ev_rl.py \
    --data "results/ev/3x3_rl*_episodes.csv"
/home/logmoon/.venvs/sumo/bin/python experiments/run_ev_priority.py \
    --scenario 3x3 --mode rl --steps 3600 --seed 42 --rl-epsilon 0 \
    --rl-policy forecasting/artifacts/ev_rl_policy.joblib
```

## Where things live

| Piece | Path |
|---|---|
| Priority rule + shared classifier | `agents/emergency_priority.py` |
| RL controller + policy | `agents/emergency_rl.py` |
| ETA regression + classifier + features | `forecasting/ev_arrival_predictor.py` |
| Experiment driver (all modes, GUI, data collection) | `experiments/run_ev_priority.py` |
| RL training | `experiments/train_ev_rl.py` |
| Figures generator | `experiments/make_report_figures.py` |
| EV demand generator (2x2 + 3x3) | `scenarios/generate_ev_routes.py` |
| All raw results | `results/ev/summary.csv` + per-run CSVs |
