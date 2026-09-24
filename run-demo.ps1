param(
    [ValidateRange(2,73)][int]$Frames = 73,
    [ValidateRange(320,1920)][int]$Width = 1280,
    [ValidateRange(240,1080)][int]$Height = 720,
    [switch]$Gui,
    [switch]$Procedural
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$repo = Split-Path -Parent $root
$genesis = Join-Path $repo 'genesis-garment-demo\.venv\Scripts\python.exe'
$isaac = Join-Path $repo 'lw-runtime\Scripts\python.exe'
$state = Join-Path $root 'outputs\mpm-state.npz'
$surface = Join-Path $root 'outputs\mpm-surface.npz'
$video = if ($Procedural) { Join-Path $root 'outputs\butter-spread.mp4' } else { Join-Path $root 'outputs\butter-spread-matched.mp4' }
if (-not (Test-Path -LiteralPath $genesis)) { throw "Missing Genesis runtime: $genesis" }
if (-not (Test-Path -LiteralPath $isaac)) { throw "Missing Isaac runtime: $isaac" }
& $genesis (Join-Path $root 'scripts\simulate_mpm.py') --frames $Frames --output $state
if ($LASTEXITCODE -ne 0) { throw 'Genesis MPM simulation failed' }
$auditArgs = @((Join-Path $root 'scripts\audit.py'), '--state', $state,
               '--output', (Join-Path $root 'outputs\physics-audit.json'))
if ($Frames -lt 73) { $auditArgs += '--preview' }
& $genesis @auditArgs
if ($LASTEXITCODE -ne 0) { throw 'Genesis MPM physics audit failed' }
& $genesis (Join-Path $root 'scripts\prepare_surface.py') --state $state --output $surface
if ($LASTEXITCODE -ne 0) { throw 'Surface reconstruction failed' }
$renderScript = if ($Procedural) { 'scripts\render_isaac.py' } else { 'scripts\render_matched.py' }
$argsList = @((Join-Path $root $renderScript), '--state', $state,
              '--output', $video, '--width', $Width, '--height', $Height,
              '--frames', $Frames)
if ($Procedural) { $argsList += @('--surface', $surface) }
if ($Gui) { $argsList += '--gui' }
& $isaac @argsList
if ($LASTEXITCODE -ne 0) { throw 'Isaac render failed' }
& $isaac (Join-Path $root 'scripts\verify_video.py')
if ($LASTEXITCODE -ne 0) { throw 'Video validation failed' }
Write-Output "Video: $video"
