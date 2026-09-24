"""Decode the delivered video and record artifact hashes for this exact run."""
import hashlib
import argparse
import json
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "outputs"
parser=argparse.ArgumentParser()
parser.add_argument('--video',type=Path,default=root/'butter-spread.mp4')
parser.add_argument('--state',type=Path,default=root/'mpm-state.npz')
parser.add_argument('--surface',type=Path,default=root/'mpm-surface.npz')
args=parser.parse_args()
output=args.video.parent
state = np.load(args.state)
surface = np.load(args.surface)
render_meta=json.loads(args.video.with_suffix('.json').read_text(encoding='utf-8'))
scene_audit=render_meta.get('scene_audit')
reader = imageio_ffmpeg.read_frames(str(args.video), pix_fmt="rgb24")
meta = next(reader)
width, height = meta["size"]
snapshots = []
hashes = set()
count = 0
for i, frame in enumerate(reader):
    count += 1
    hashes.add(hashlib.sha256(frame).hexdigest())
    if i in (0, 36, 72):
        im = Image.frombytes("RGB", (width, height), frame)
        im.thumbnail((640, 360))
        snapshots.append((i, im))
checks = {
    "decoded_frames_match_state": count == len(state["particles"]),
    "fps_matches_state": abs(meta["fps"] - float(state["fps"])) < 0.01,
    "surface_frames_match_state": len(surface["vertex_offsets"]) == count + 1,
    "video_changes_over_time": len(hashes) > count // 2,
    "no_synthetic_contact_film": (scene_audit['no_synthetic_contact_film'] if scene_audit else
                                  "ContactFilm" not in args.video.with_suffix('.usda').read_text()),
}
if scene_audit:
    checks.update({'no_hand_model':scene_audit['no_hand_model'],
                   'volumetric_bread_asset':scene_audit['cdmpm_bread_vertices']>1000000,
                   'flat_blade_present':scene_audit['flat_blade_present']})
artifacts = (args.state,args.surface,args.video,root/'physics-audit.json')
report = {"pass": all(checks.values()), "checks": checks,
          "decoded_frames": count, "size": [width, height], "fps": meta["fps"],
          "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}}
(output / "video-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
sheet = Image.new("RGB", (640, 390 * len(snapshots)), "#202020")
draw = ImageDraw.Draw(sheet)
for row, (i, im) in enumerate(snapshots):
    sheet.paste(im, (0, row * 390))
    draw.text((12, row * 390 + 365), f"Simulation t = {i / meta['fps']:.2f} s", fill="white")
sheet.save(output / "verified-keyframes.jpg")
print(json.dumps(report, indent=2))
if not report["pass"]:
    raise SystemExit(1)
