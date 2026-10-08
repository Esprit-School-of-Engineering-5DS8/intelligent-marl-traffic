#!/usr/bin/env bash
# =====================================================================
# Root launcher (Linux/macOS) — mirrors run.ps1 for the Windows team.
# Automatically uses the Python interpreter that has SUMO/traci.
#
# Usage:
#   ./run.sh [--scenario grid_2x2|grid_3x3] [--mode MODE] [--steps N] [--gui] [--delay MS]
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCENARIO="grid_2x2"
MODE="max_pressure"
STEPS=1000
DELAY=100
GUI=0

usage() {
  echo "Usage: ./run.sh [--scenario grid_2x2|grid_3x3] [--mode sumo_default|fixed|max_pressure|custom] [--steps N] [--gui] [--delay MS]"
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --scenario|-s) SCENARIO="$2"; shift 2 ;;
    --mode|-m)     MODE="$2"; shift 2 ;;
    --steps|-n)    STEPS="$2"; shift 2 ;;
    --delay)       DELAY="$2"; shift 2 ;;
    --gui)         GUI=1; shift ;;
    --nogui)       GUI=0; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

TARGET_DIR="$SCRIPT_DIR/scenarios/$SCENARIO"
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: scenario '$SCENARIO' not found. Available:"
  ls "$SCRIPT_DIR/scenarios"
  exit 1
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

echo "Running $SCENARIO | mode: $MODE | steps: $STEPS | gui: $([ "$GUI" -eq 1 ] && echo yes || echo no)"
echo "Python: $PY"

cd "$TARGET_DIR"
if [ "$GUI" -eq 1 ]; then
  exec "$PY" runner.py --gui --delay "$DELAY" --mode "$MODE" --steps "$STEPS"
else
  exec "$PY" runner.py --mode "$MODE" --steps "$STEPS"
fi
