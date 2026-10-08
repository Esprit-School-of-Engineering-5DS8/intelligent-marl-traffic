#!/usr/bin/env bash
# ====================================================================
# Run script for 3x3 SUMO Multi-Agent Scenario in WSL Ubuntu
# ====================================================================

# Keep a system-wide/WSL SUMO install working when present (no-op with pip-installed SUMO).
if [ -z "${SUMO_HOME:-}" ] && [ -d /usr/share/sumo ]; then
  export SUMO_HOME=/usr/share/sumo
fi
if [ -n "${SUMO_HOME:-}" ] && [ -d "$SUMO_HOME/tools" ]; then
  export PYTHONPATH="$SUMO_HOME/tools:${PYTHONPATH:-}"
fi

# Pick a Python interpreter that has SUMO/traci installed:
#   1. an activated virtualenv, 2. ~/.venvs/sumo (Amen's machine), 3. PATH.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
    PY="$VIRTUAL_ENV/bin/python"
  elif [ -x "$HOME/.venvs/sumo/bin/python" ]; then
    PY="$HOME/.venvs/sumo/bin/python"
  else
    PY="python3"
  fi
fi

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
      "$PY" build_network.py
      "$PY" generate_routes.py
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
echo " Starting 3x3 Grid Multi-Agent Simulation"
echo " Controller Mode : $MODE"
echo " Steps           : $STEPS"
echo " GUI Enabled     : $([ -n "$GUI_FLAG" ] && echo "Yes (delay: ${DELAY}ms)" || echo 'No (Headless)')"
echo "=================================================="

if [ -n "$GUI_FLAG" ]; then
  "$PY" runner.py --gui --mode "$MODE" --steps "$STEPS" --delay "$DELAY"
else
  "$PY" runner.py --mode "$MODE" --steps "$STEPS" --delay 0
fi
