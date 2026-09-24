"""Reconstruct a smooth display mesh from Genesis MPM particle positions."""
import argparse
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "mpm-surface.npz")
parser.add_argument("--density-level", type=float, default=0.20,
                    help="fraction of peak particle density used for the visible butter surface")
args = parser.parse_args()
if not 0.05 <= args.density_level <= 0.5:
    parser.error("--density-level must be in [0.05, 0.5]")
data = np.load(args.state)
origin = np.array([-0.085, -0.060, 0.022], dtype=np.float32)
voxel = 0.0017
shape = (104, 72, 28)
vertices = []
faces = []
vertex_offsets = [0]
face_offsets = [0]
for xyz in data["particles"]:
    ids = np.floor((xyz - origin) / voxel).astype(int)
    ok = np.all((ids >= 0) & (ids < np.array(shape)), axis=1)
    field = np.zeros(shape, dtype=np.float32)
    np.add.at(field, tuple(ids[ok].T), 1.0)
    field = gaussian_filter(field, sigma=1.65)
    level = max(float(field.max()) * args.density_level, 1e-5)
    if field.max() > level:
        v, f, _, _ = marching_cubes(field, level)
        vertices.append((origin + v * voxel).astype(np.float32))
        faces.append(f.astype(np.int32))
    else:
        vertices.append(np.empty((0, 3), dtype=np.float32))
        faces.append(np.empty((0, 3), dtype=np.int32))
    vertex_offsets.append(vertex_offsets[-1] + len(vertices[-1]))
    face_offsets.append(face_offsets[-1] + len(faces[-1]))
args.output.parent.mkdir(parents=True, exist_ok=True)
np.savez_compressed(args.output,
                    vertices=np.concatenate(vertices),
                    faces=np.concatenate(faces),
                    vertex_offsets=np.array(vertex_offsets, dtype=np.int32),
                    face_offsets=np.array(face_offsets, dtype=np.int32))
print(f"Saved {args.output} ({len(vertices)} frames)")
