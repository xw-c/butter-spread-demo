param(
    [ValidateRange(1,256)][int]$Samples = 64,
    [ValidateRange(320,3840)][int]$Width = 1280,
    [ValidateRange(240,2160)][int]$Height = 720,
    [string]$PhysicsPython = $env:BUTTER_PHYSICS_PYTHON,
    [string]$IsaacPython = $env:BUTTER_ISAAC_PYTHON,
    [string]$Output = (Join-Path $PSScriptRoot 'outputs/butter-spread.mp4')
)
$ErrorActionPreference = 'Stop'
if (-not $PhysicsPython) { $PhysicsPython = Join-Path $PSScriptRoot '.venv-physics/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PhysicsPython)) { throw 'Physics Python missing. Run setup-demo.ps1 or pass -PhysicsPython.' }
$arguments = @((Join-Path $PSScriptRoot 'scripts/run_demo.py'), '--render-only',
    '--samples', $Samples, '--width', $Width, '--height', $Height, '--output', $Output)
if ($IsaacPython) { $arguments += @('--isaac-python', $IsaacPython) }
& $PhysicsPython @arguments
if ($LASTEXITCODE -ne 0) { throw 'Scene render or validation failed.' }
