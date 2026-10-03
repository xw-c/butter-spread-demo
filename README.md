# Butter spreading with Genesis MPM and Isaac Sim

[中文安装与运行说明](README.zh-CN.md)

This repository includes the calibrated butter/bread constitutive models,
contact implementation, and the patches to the pinned public Genesis engine.
No sibling `genesis-world` clone or private source files are required.

Prerequisites: Python 3.11, Git, Blender (tested with 5.2), and a supported
NVIDIA RTX GPU/driver for Isaac Sim 5.1. Software dependencies are installed
separately in project-local physics and rendering environments.

```powershell
git clone https://github.com/xw-c/butter-spread-demo.git
cd butter-spread-demo
.\setup-demo.ps1 -Python python -WithIsaac
# Only after reading and accepting NVIDIA's Omniverse license:
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
.\run-demo.ps1
```

Put Blender on PATH or pass `-Blender` with its executable path. The first run
builds the porous bread mesh from the source VDB ZIP already in this repository.
The full output is `outputs/butter-spread.mp4`. Generated outputs and runtimes
are intentionally not tracked. `-Frames 2` provides a short startup test.

For physics only, omit `-WithIsaac` and run `run-demo.ps1 -PhysicsOnly`.
Existing runtimes can be selected with `-PhysicsPython` and `-IsaacPython`;
see the Chinese guide for dependency installation and Linux commands.

Engine provenance and licenses: [vendor/NOTICE.txt](vendor/NOTICE.txt).
The photomatched rendering option is only a visual reference; the default
3D video renders the simulated butter and deforming bread mesh.
