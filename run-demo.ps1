param(
    [ValidateRange(2,97)][int]$Frames = 97,
    [ValidateRange(320,1920)][int]$Width = 1280,
    [ValidateRange(240,1080)][int]$Height = 720,
    [ValidateSet('gpu','cpu')][string]$Backend = 'gpu',
    [string]$PhysicsPython = $env:BUTTER_PHYSICS_PYTHON,
    [string]$IsaacPython = $env:BUTTER_ISAAC_PYTHON,
    [string]$Blender = $env:BLENDER_EXE,
    [switch]$Gui, [switch]$Procedural, [switch]$PhotoMatched,
    [switch]$PhysicsOnly, [switch]$ReusePhysics
)
$ErrorActionPreference = 'Stop'
if (-not $PhysicsPython) { $PhysicsPython = Join-Path $PSScriptRoot '.venv-physics/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PhysicsPython)) { throw 'Physics Python missing. Run setup-demo.ps1 or pass -PhysicsPython.' }
if ($Procedural -and $PhotoMatched) { throw 'Choose either -Procedural or -PhotoMatched' }
$arguments = @((Join-Path $PSScriptRoot 'scripts/run_demo.py'), '--frames', $Frames,
    '--width', $Width, '--height', $Height, '--backend', $Backend)
if ($IsaacPython) { $arguments += @('--isaac-python', $IsaacPython) }
if ($Blender) { $arguments += @('--blender', $Blender) }
if ($Gui) { $arguments += '--gui' }
if ($PhotoMatched) { $arguments += '--photo-matched' }
if ($PhysicsOnly) { $arguments += '--physics-only' }
if ($ReusePhysics) { $arguments += '--reuse-physics' }
& $PhysicsPython @arguments
if ($LASTEXITCODE -ne 0) { throw 'Demo pipeline failed; see the error above.' }
