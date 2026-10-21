@echo off
REM ====================================================================
REM Windows launcher for 2x2 SUMO Multi-Agent Simulation
REM ====================================================================

set ARGS=%*
if "%ARGS%"=="" set ARGS=--mode max_pressure --steps 500

python runner.py %ARGS%
