"""Select and verify this checkout's pinned, patched Genesis engine."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def activate():
    engine = ROOT / '.vendor' / 'genesis'
    lock = json.loads((ROOT / 'vendor/genesis-lock.json').read_text())
    for relative, expected in lock['patched_files'].items():
        path = engine / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise RuntimeError('Missing or incompatible Genesis engine. Run python scripts/bootstrap_genesis.py, '
                               'then install .vendor/genesis in the physics environment. File: ' + str(path))
    sys.path.insert(0, str(engine))
    sys.path.insert(0, str(ROOT))
    if 'genesis' in sys.modules and not Path(sys.modules['genesis'].__file__).resolve().is_relative_to(engine):
        raise RuntimeError('A different Genesis engine was imported before the demo runtime')
    return engine
