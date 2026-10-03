param(
    [string]$Python = 'python',
    [switch]$WithIsaac,
    [switch]$Cpu,
    [string]$Blender = $env:BLENDER_EXE
)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'scripts/setup_demo.py'))
if ($WithIsaac) { $arguments += '--with-isaac' }
if ($Cpu) { $arguments += '--cpu' }
if ($Blender) { $arguments += @('--blender', $Blender) }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Demo setup failed; Python 3.11 is required.' }
