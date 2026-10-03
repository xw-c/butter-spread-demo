"""Rebuild the ignored bread mesh solely from the committed source VDB ZIP."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import os

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', default=os.environ.get('BLENDER_EXE'))
    args = parser.parse_args()
    ready = ROOT / 'assets/cdmpm-bread-hero-ready.npz'
    if ready.is_file():
        print('Bread mesh already exists:', ready)
        return
    raw = ROOT / 'assets/cdmpm-bread-raw.npz'
    if not raw.is_file():
        blender = args.blender or shutil.which('blender')
        if not blender and os.name == 'nt':
            candidates = sorted((Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
                                 / 'Blender Foundation').glob('Blender */blender.exe'))
            blender = str(candidates[-1]) if candidates else None
        if not blender or not (Path(blender).is_file() or shutil.which(blender)):
            raise SystemExit('Install Blender and pass --blender /path/to/blender (or set BLENDER_EXE). '
                             'The source breadxxx.vdb.zip is included; no private mesh download is needed.')
        source = ROOT / 'assets/reference/cdmpm/breadxxx.vdb'
        if not source.is_file():
            with zipfile.ZipFile(source.with_suffix('.vdb.zip')) as z, z.open('breadxxx.vdb') as inp, source.open('wb') as out:
                shutil.copyfileobj(inp, out)
        subprocess.run([blender, '--background', '--threads', '4', '--python-exit-code', '1',
                        '--python', str(ROOT / 'scripts/inspect_bread_vdb.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_cdmpm_mesh.py')], check=True)
    if not ready.is_file():
        raise RuntimeError('Bread preparation did not create ' + str(ready))


if __name__ == '__main__':
    main()
