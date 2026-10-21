# PowerShell launcher for 2x2 SUMO Multi-Agent simulation
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

Write-Host "Running 2x2 Simulation..." -ForegroundColor Cyan
Write-Host "Mode: $mode | Steps: $steps | GUI: $(if ($gui) {'Enabled (delay: ' + $delay + 'ms)'} else {'Disabled'})" -ForegroundColor DarkGray

if ($wsl) {
    wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/Hazem/Desktop/SUMO/scenarios/grid_2x2 && ./run.sh $guiFlag --mode '$mode' --steps $steps"
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
