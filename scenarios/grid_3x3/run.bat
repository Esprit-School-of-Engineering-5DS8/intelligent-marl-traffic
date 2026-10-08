@echo off
REM ====================================================================
REM Windows launcher for 3x3 SUMO Multi-Agent Simulation via WSL Ubuntu
REM ====================================================================

set ARGS=%*
if "%ARGS%"=="" set ARGS=--mode max_pressure --steps 500

python runner.py %ARGS%
