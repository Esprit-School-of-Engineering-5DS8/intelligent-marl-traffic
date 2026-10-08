# PowerShell root launcher for SUMO Multi-Agent simulation
param (
    [string]$scenario = "grid_2x2",
    [switch]$gui,
    [switch]$nogui,
    [string]$mode = "max_pressure",
    [int]$steps = 1000,
    [int]$delay = 100,
    [switch]$wsl
)

$targetDir = Join-Path $PSScriptRoot "scenarios\$scenario"
if (-not (Test-Path $targetDir)) {
    Write-Error "Scenario '$scenario' not found at $targetDir. Available: grid_2x2, grid_3x3"
    exit 1
}

$guiFlag = ""
if ($gui) {
    $guiFlag = "--gui --delay $delay"
}

Write-Host "Running $scenario Simulation..." -ForegroundColor Cyan
Write-Host "Mode: $mode | Steps: $steps | GUI: $(if ($gui) {'Enabled (delay: ' + $delay + 'ms)'} else {'Disabled'})" -ForegroundColor DarkGray

if ($wsl) {
    wsl -d Ubuntu -e bash -lc "cd /mnt/c/Users/Hazem/Desktop/SUMO/scenarios/$scenario && ./run.sh $guiFlag --mode '$mode' --steps $steps"
} else {
    Push-Location $targetDir
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
