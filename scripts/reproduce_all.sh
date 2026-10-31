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
for net in grid3x3 tunis; do
  [ -f "configs/reward_norm/$net.yaml" ] || $PY -m cotraffic calibrate --net "$net"
done
# inflow forecasting (Tier 2) and the Ridge model used by the forecast agent (Tier 3)
[ -f results/forecasting/ridge_grid3x3.json ] || $PY -m cotraffic forecast --net grid3x3

if [ "${TRAIN:-0}" = "1" ]; then
  # Learned models are trained as recipes now (the rl template and rl_<hash> profiles
  # frozen by the dashboard's training editor); legacy coop/ind presets are gone.
  for seed in 1 2 3; do
    [ -f "results/checkpoints/rl/grid3x3/seed$seed.zip" ] || $PY -m cotraffic train --agent rl --net grid3x3 --seed "$seed"
    [ -f "results/checkpoints/rl/tunis/seed$seed.zip" ] || $PY -m cotraffic train --agent rl --net tunis --seed "$seed"
  done
  $PY -m cotraffic select --jobs "$JOBS"
fi

$PY -m cotraffic evaluate --experiment full_matrix --jobs "$JOBS"
$PY -m cotraffic evaluate --experiment sensitivity --jobs "$JOBS"
$PY -m cotraffic aggregate
# feature importance (figure 12): training run t1 of the primal model, test seeds 0-4
[ -f results/summary/importance_rl_grid3x3.csv ] || $PY -m cotraffic explain --agent rl --net grid3x3 --demand peak --scenarios normal
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

