# PowerShell launcher for SUMO Multi-Agent simulation running in WSL Ubuntu
param (
    [switch]$gui,
    [switch]$nogui,
    [string]$mode = "max_pressure",
    [int]$steps = 1000,
    [int]$delay = 100,
    [switch]$wsl
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$guiFlag = ""
if ($gui) {
    $guiFlag = "--gui --delay $delay"
}

Write-Host "Running 3x3 Simulation..." -ForegroundColor Cyan
Write-Host "Mode: $mode | Steps: $steps | GUI: $(if ($gui) {'Enabled (delay: ' + $delay + 'ms)'} else {'Disabled'})" -ForegroundColor DarkGray

if ($wsl) {
    wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/Hazem/Desktop/SUMO/scenarios/grid_3x3 && ./run.sh $guiFlag --mode '$mode' --steps $steps"
} else {
    Push-Location $scriptDir
    try {
        if ($gui) {
            python runner.py --gui --delay $delay --mode $mode --steps $steps
        } else {
            python runner.py --mode $mode --steps $steps
        }
    } finally {
        Pop-Location
    }
}

