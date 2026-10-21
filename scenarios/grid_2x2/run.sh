#!/usr/bin/env bash
# ====================================================================
# Run script for 2x2 SUMO Multi-Agent Scenario
# ====================================================================

export SUMO_HOME=${SUMO_HOME:-/usr/share/sumo}
export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Default settings
GUI_FLAG=""
MODE="max_pressure"
STEPS=1000
DELAY=100

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --gui)
      GUI_FLAG="--gui"
      shift
      ;;
    --nogui)
      GUI_FLAG=""
      shift
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --steps)
      STEPS="$2"
      shift 2
      ;;
    --delay)
      DELAY="$2"
      shift 2
      ;;
    --rebuild)
      echo "[run.sh] Rebuilding network and routes..."
      python3 build_network.py
      python3 generate_routes.py
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: ./run.sh [--gui] [--nogui] [--mode fixed|max_pressure|custom|sumo_default] [--steps N] [--delay ms]"
      exit 1
      ;;
  esac
done

echo "=================================================="
echo " Starting 2x2 Grid Multi-Agent Simulation"
echo " Controller Mode : $MODE"
echo " Steps           : $STEPS"
echo " GUI Enabled     : $([ -n "$GUI_FLAG" ] && echo "Yes (delay: ${DELAY}ms)" || echo 'No (Headless)')"
echo "=================================================="

if [ -n "$GUI_FLAG" ]; then
  python3 runner.py --gui --mode "$MODE" --steps "$STEPS" --delay "$DELAY"
else
  python3 runner.py --mode "$MODE" --steps "$STEPS" --delay 0
fi
