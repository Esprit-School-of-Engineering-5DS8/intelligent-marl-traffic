# PowerShell root launcher for SUMO Multi-Agent simulation running in WSL Ubuntu
param (
    [switch]$gui,
    [switch]$nogui,
    [string]$mode = "max_pressure",
    [int]$steps = 1000,
    [int]$delay = 100
)

$guiFlag = ""
if ($gui) {
    $guiFlag = "--gui --delay $delay"
}

Write-Host "Running 3x3 Simulation in WSL Ubuntu..." -ForegroundColor Cyan
Write-Host "Mode: $mode | Steps: $steps | GUI: $(if ($gui) {'Enabled (delay: ' + $delay + 'ms)'} else {'Disabled'})" -ForegroundColor DarkGray

wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/Hazem/Desktop/SUMO/scenario_3x3 && ./run.sh $guiFlag --mode '$mode' --steps $steps"
