#!/usr/bin/env bash
# Regenerate every result of the report from the configs.
#   networks -> reward scales -> (training if no selected checkpoint) -> evaluation
#   -> statistics -> figures -> tables
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

if [ "${TRAIN:-0}" = "1" ]; then
  for agent in ind coop coop_eco05 coop_eco coop_full; do
    for seed in 1 2 3; do
      [ -f "results/checkpoints/$agent/grid4x4/seed$seed.zip" ] || $PY -m cotraffic train --agent "$agent" --net grid4x4 --seed "$seed"
    done
  done
  for agent in ind coop coop_full; do
    for seed in 1 2 3; do
      [ -f "results/checkpoints/$agent/real_district/seed$seed.zip" ] || $PY -m cotraffic train --agent "$agent" --net real_district --seed "$seed"
    done
  done
  $PY -m cotraffic select --jobs "$JOBS"
fi

$PY -m cotraffic evaluate --experiment full_matrix --jobs "$JOBS"
$PY -m cotraffic aggregate
$PY -m cotraffic figures
$PY -m cotraffic tables
echo "done: results/summary/REPORT_TABLES.md and figures/"
