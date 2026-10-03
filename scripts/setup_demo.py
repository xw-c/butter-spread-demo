"""Create project-local Python environments with pinned public dependencies."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv
import os

ROOT = Path(__file__).resolve().parents[1]


def environment(name):
    directory = ROOT / name
    python = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(directory)
    return str(python)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-isaac', action='store_true')
    parser.add_argument('--cpu', action='store_true', help='CPU PyTorch for physics-only machines')
    parser.add_argument('--blender', help='also prepare the mesh using this Blender executable')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.error('Use Python 3.11 for the tested Genesis / Isaac Sim 5.1 environments')
    subprocess.run([sys.executable, str(ROOT/'scripts/bootstrap_genesis.py')], check=True)
    python = environment('.venv-physics')
    def pip(executable, *arguments):
        subprocess.run([executable, '-m', 'pip', 'install', *arguments], check=True)
    pip(python, '--upgrade', 'pip')
    pip(python, 'torch==2.11.0', '--index-url',
        'https://download.pytorch.org/whl/' + ('cpu' if args.cpu else 'cu128'))
    pip(python, '-r', str(ROOT/'requirements-physics.txt'), '-e', str(ROOT/'.vendor/genesis'))
    if args.with_isaac:
        render = environment('.venv-isaac')
        pip(render, '--upgrade', 'pip')
        pip(render, 'isaacsim[all,extscache]==5.1.0.0', '--extra-index-url', 'https://pypi.nvidia.com',
            '-r', str(ROOT/'requirements-render.txt'))
    if args.blender:
        subprocess.run([python, str(ROOT/'scripts/prepare_assets.py'), '--blender', args.blender], check=True)
    print('Physics environment:', python)
    print('Next: run-demo.ps1 (Windows), or .venv-physics/bin/python scripts/run_demo.py (Linux).')


if __name__ == '__main__':
    main()
