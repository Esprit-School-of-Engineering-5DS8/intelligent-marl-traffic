#!/usr/bin/env bash
# Regenerate every result of the report from the configs.
#   networks -> reward scales -> forecast model -> (training if no selected checkpoint)
#   -> evaluation (full matrix + sensitivity) -> statistics -> feature importance
#   -> figures -> tables -> A/B (llm_ab) -> dashboard export
# Set TRAIN=1 to retrain missing policies (hours on a laptop); by default the selected
# checkpoints shipped in results/checkpoints are used.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
JOBS=${JOBS:-2}
export LIBSUMO_AS_TRACI=1

$PY -m cotraffic networks --all
for net in grid4x4 real_district; do
  [ -f "configs/reward_norm/$net.yaml" ] || $PY -m cotraffic calibrate --net "$net"
done
# inflow forecasting (Tier 2) and the Ridge model used by the forecast agent (Tier 3)
[ -f results/forecasting/ridge_grid4x4.json ] || $PY -m cotraffic forecast --net grid4x4

if [ "${TRAIN:-0}" = "1" ]; then
  for agent in ind coop coop_eco05 coop_eco coop_full coop_forecast; do
    for seed in 1 2 3; do
      [ -f "results/checkpoints/$agent/grid4x4/seed$seed.zip" ] || $PY -m cotraffic train --agent "$agent" --net grid4x4 --seed "$seed"
    done
  done
  for agent in coop_full_ev1 coop_full_ev4; do  # sensitivity: one training run each
    [ -f "results/checkpoints/$agent/grid4x4/seed1.zip" ] || $PY -m cotraffic train --agent "$agent" --net grid4x4 --seed 1
  done
  for agent in ind coop coop_full; do
    for seed in 1 2 3; do
      [ -f "results/checkpoints/$agent/real_district/seed$seed.zip" ] || $PY -m cotraffic train --agent "$agent" --net real_district --seed "$seed"
    done
  done
  $PY -m cotraffic select --jobs "$JOBS"
fi

$PY -m cotraffic evaluate --experiment full_matrix --jobs "$JOBS"
$PY -m cotraffic evaluate --experiment sensitivity --jobs "$JOBS"
$PY -m cotraffic aggregate
# feature importance (figure 12): training run t1 of each variant, test seeds 0-4
[ -f results/summary/importance_coop_full_grid4x4.csv ] || $PY -m cotraffic explain --agent coop_full --net grid4x4 --demand peak --scenarios emergency
[ -f results/summary/importance_coop_grid4x4.csv ] || $PY -m cotraffic explain --agent coop --net grid4x4 --demand peak --scenarios normal
$PY -m cotraffic figures
$PY -m cotraffic tables

# A/B: LLM vs PPO vs Max-Pressure (configs/experiments/llm_ab.yaml).
# AB=0 skips it. Keep AB_JOBS=1 for the LLM cells: two workers share one API key and hit
# the provider's rate limits (see docs/ARCHITECTURE.md §6).
if [ "${AB:-1}" = "1" ]; then
  $PY -m cotraffic evaluate --experiment llm_ab --jobs "${AB_JOBS:-1}"
  $PY -m cotraffic aggregate
  $PY -m cotraffic tables
fi

# The files the dashboard serves (frontend/public/data) come from the results above.
$PY scripts/export_dashboard_data.py

echo "done: results/summary/REPORT_TABLES.md, figures/, frontend/public/data"
echo "live policy defaults: configs/dashboard_policy.yaml (GET/PUT /api/policy)"

