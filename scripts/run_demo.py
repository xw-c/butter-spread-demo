"""Portable physics -> surface -> Isaac scene pipeline, independent of cwd."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames', type=int, default=97)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--samples', type=int, default=64)
    parser.add_argument('--backend', choices=['gpu', 'cpu'], default='gpu')
    parser.add_argument('--physics-only', action='store_true')
    parser.add_argument('--reuse-physics', action='store_true')
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--photo-matched', action='store_true')
    parser.add_argument('--isaac-python', default=os.environ.get('BUTTER_ISAAC_PYTHON',
        str(ROOT / '.venv-isaac' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))))
    parser.add_argument('--blender', default=os.environ.get('BLENDER_EXE'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 2 <= args.frames <= 97:
        parser.error('frames must be between 2 and 97')
    def run(script, *arguments, python=sys.executable):
        subprocess.run([python, str(ROOT/'scripts'/script), *map(str, arguments)], cwd=ROOT, check=True)
    out = ROOT/'outputs'
    out.mkdir(exist_ok=True)
    state, surface = out/'mpm-state.npz', out/'mpm-surface.npz'
    if not args.physics_only:
        if not Path(args.isaac_python).is_file():
            parser.error('Isaac Python not found. Run setup_demo.py --with-isaac, or pass --isaac-python /path/to/python.')
        if not args.photo_matched:
            run('prepare_assets.py', *(['--blender', args.blender] if args.blender else []))
    if not args.reuse_physics and not args.render_only:
        run('simulate_mpm.py', '--frames', args.frames, '--backend', args.backend, '--output', state)
    if not state.is_file():
        parser.error('No simulated state; run without --reuse-physics / --render-only first')
    if not args.render_only:
        run('audit.py', '--state', state, '--output', out/'physics-audit.json',
            *(['--preview'] if args.frames < 97 else []))
        run('prepare_surface.py', '--state', state, '--output', surface)
        if args.frames == 97:
            run('measure_surface_ripples.py', '--state', state, '--surface', surface,
                '--output', out/'surface-ripples.json')
    if args.physics_only:
        print('Physics and surface:', state, surface)
        return
    video = args.output or out/('butter-spread-matched.mp4' if args.photo_matched else 'butter-spread.mp4')
    script = 'render_matched.py' if args.photo_matched else 'render_isaac.py'
    options = ['--state', state, '--output', video, '--width', args.width, '--height', args.height,
               '--frames', args.frames]
    if not args.photo_matched:
        options += ['--surface', surface, '--samples', args.samples]
    if args.gui:
        options += ['--gui']
    run(script, *options, python=args.isaac_python)
    if args.frames == 97 and not args.photo_matched:
        run('verify_video.py', '--video', video, '--state', state, '--surface', surface)
    else:
        print('Preview/reference output; full physical-video validation requires the 97-frame 3D scene.')
    print('Video:', video)


if __name__ == '__main__':
    main()
