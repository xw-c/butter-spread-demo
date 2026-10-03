"""Fetch a public pinned Genesis source archive and apply the bundled patch."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / 'vendor/genesis-lock.json').read_text())
    destination = ROOT / '.vendor/genesis'
    if destination.exists():
        from genesis_runtime import activate
        activate()
        print('Pinned Genesis is already present and verified:', destination)
        return
    archive = ROOT / '.cache/genesis-source.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        urllib.request.urlretrieve(lock['archive_url'], temporary)
        temporary.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['archive_sha256']:
        raise RuntimeError('Genesis archive checksum mismatch: ' + str(archive))
    patch = ROOT / 'vendor/genesis-mpm.patch'
    if hashlib.sha256(patch.read_bytes()).hexdigest() != lock['patch_sha256']:
        raise RuntimeError('Bundled Genesis patch checksum mismatch')
    staging = ROOT / '.vendor/genesis-extract'
    staging.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (staging / name).resolve().is_relative_to(staging.resolve()):
                raise RuntimeError('Invalid archive path')
        z.extractall(staging)
    source = staging / ('Genesis-' + lock['commit'])
    if not source.exists():
        children = list(staging.iterdir())
        if len(children) != 1 or not (children[0] / 'genesis/__init__.py').is_file():
            raise RuntimeError('Unexpected upstream archive structure')
        source = children[0]
    # A local repository makes git-apply independent of the parent's cwd and
    # repository layout, including a GitHub ZIP checkout with no .git folder.
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    subprocess.run(['git', '-C', str(source), 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
    source.rename(destination)
    staging.rmdir()
    (destination / 'butter-demo-source.json').write_text(json.dumps(lock, indent=2))
    from genesis_runtime import activate
    activate()
    print('Installed verified Genesis source:', destination)


if __name__ == '__main__':
    main()
