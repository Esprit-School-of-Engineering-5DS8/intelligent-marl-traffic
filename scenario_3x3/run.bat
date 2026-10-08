@echo off
REM ====================================================================
REM Windows launcher for 3x3 SUMO Multi-Agent Simulation via WSL Ubuntu
REM ====================================================================

set ARGS=%*
if "%ARGS%"=="" set ARGS=--nogui --steps 500

echo Launching SUMO in WSL Ubuntu...
wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/Hazem/Desktop/SUMO/scenario_3x3 && ./run.sh %ARGS%"
