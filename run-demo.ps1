param(
    [ValidateRange(2,97)][int]$Frames = 97,
    [ValidateRange(320,1920)][int]$Width = 1280,
    [ValidateRange(240,1080)][int]$Height = 720,
    [switch]$Gui,
    [switch]$Procedural,
    [switch]$PhotoMatched,
    [switch]$PhysicsOnly,
    [switch]$ReusePhysics
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$repo = Split-Path -Parent $root
$isaac = Join-Path $repo 'lw-runtime\python.exe'
$state = Join-Path $root 'outputs\mpm-state.npz'
$surface = Join-Path $root 'outputs\mpm-surface.npz'
if ($Procedural -and $PhotoMatched) { throw 'Choose either -Procedural or -PhotoMatched' }
# The physical 3D scene is the default. The photograph projection is only an
# explicitly requested visual reference; it is not a simulation result.
$video = if ($PhotoMatched) { Join-Path $root 'outputs\butter-spread-matched.mp4' } else { Join-Path $root 'outputs\butter-spread.mp4' }
if (-not $ReusePhysics) {
    & conda run --no-capture-output -n genesis-world python -u (Join-Path $root 'scripts\simulate_mpm.py') --frames $Frames --output $state
    if ($LASTEXITCODE -ne 0) { throw 'Genesis MPM simulation failed' }
}
if (-not (Test-Path -LiteralPath $state)) { throw "Missing simulated state: $state" }
$auditArgs = @((Join-Path $root 'scripts\audit.py'), '--state', $state,
               '--output', (Join-Path $root 'outputs\physics-audit.json'))
if ($Frames -lt 97) { $auditArgs += '--preview' }
& conda run --no-capture-output -n genesis-world python @auditArgs
if ($LASTEXITCODE -ne 0) { throw 'Genesis MPM physics audit failed' }
& conda run --no-capture-output -n genesis-world python (Join-Path $root 'scripts\prepare_surface.py') --state $state --output $surface
if ($LASTEXITCODE -ne 0) { throw 'Surface reconstruction failed' }
if ($Frames -eq 97) {
    & conda run --no-capture-output -n genesis-world python (Join-Path $root 'scripts\measure_surface_ripples.py') --state $state --surface $surface --output (Join-Path $root 'outputs\surface-ripples.json')
    if ($LASTEXITCODE -ne 0) { throw 'Surface ripple measurement failed' }
}
if ($PhysicsOnly) {
    Write-Output "Physics state: $state"
    Write-Output "Reconstructed surface: $surface"
    return
}
if (-not (Test-Path -LiteralPath $isaac)) {
    throw "Isaac Sim runtime is missing at $isaac. Physics outputs are complete; use -PhysicsOnly to generate them without rendering."
}
$renderScript = if ($PhotoMatched) { 'scripts\render_matched.py' } else { 'scripts\render_isaac.py' }
$argsList = @((Join-Path $root $renderScript), '--state', $state,
              '--output', $video, '--width', $Width, '--height', $Height,
              '--frames', $Frames)
if (-not $PhotoMatched) { $argsList += @('--surface', $surface) }
if ($Gui) { $argsList += '--gui' }
& $isaac @argsList
if ($LASTEXITCODE -ne 0) { throw 'Isaac render failed' }
if ($Frames -eq 97) {
    & $isaac (Join-Path $root 'scripts\verify_video.py') --video $video --state $state --surface $surface
    if ($LASTEXITCODE -ne 0) { throw 'Video validation failed' }
} else {
    Write-Output 'Partial preview: end-of-spread surface and video validation require all 97 frames.'
}
Write-Output "Video: $video"
