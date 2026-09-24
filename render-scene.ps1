param(
    [ValidateRange(1,256)][int]$Samples = 32,
    [ValidateRange(320,3840)][int]$Width = 1280,
    [ValidateRange(240,2160)][int]$Height = 720,
    [string]$Output = (Join-Path $PSScriptRoot 'outputs\scene-v3\butter-spread.mp4')
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$repo = Split-Path -Parent $root
$python = Join-Path $repo 'lw-runtime\Scripts\python.exe'
& $python (Join-Path $root 'scripts\render_isaac.py') --samples $Samples --width $Width --height $Height --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Reference-scene render failed' }
& $python (Join-Path $root 'scripts\verify_video.py') --video $Output
if ($LASTEXITCODE -ne 0) { throw 'Video validation failed' }
Write-Output $Output
