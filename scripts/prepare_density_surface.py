"""Continuous, mass-weighted B-spline surface reconstruction for diagnosis.

No position quantization, per-frame normalization, temporal filtering, component
deletion or prescribed connectivity. Each particle contributes its actual rest
volume to a fixed kernel. Under-resolved samples, disconnected components and
holes are reported, not removed from the surface.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from numba import njit
from scipy.ndimage import map_coordinates
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from skimage.measure import marching_cubes


@njit(cache=True)
def b2(x):
    x = abs(x)
    if x < 0.5:
        return 0.75 - x * x
    if x < 1.5:
        return 0.5 * (1.5 - x) ** 2
    return 0.0


@njit(cache=True)
def splat(points, origin, shape, voxel, kernel_width, volume):
    density = np.zeros(shape, dtype=np.float32)
    support = 1.5 * kernel_width
    amplitude = volume / kernel_width**3
    for p in points:
        low = np.maximum(np.ceil((p - support - origin) / voxel).astype(np.int32), 0)
        high = np.minimum(np.floor((p + support - origin) / voxel).astype(np.int32) + 1, np.array(shape))
        for i in range(low[0], high[0]):
            wx = b2((origin[0] + i * voxel - p[0]) / kernel_width)
            for j in range(low[1], high[1]):
                wxy = wx * b2((origin[1] + j * voxel - p[1]) / kernel_width)
                for k in range(low[2], high[2]):
                    density[i, j, k] += amplitude * wxy * b2((origin[2] + k * voxel - p[2]) / kernel_width)
    return density


def field_normals(density, vertices, origin, voxel):
    """Outward normals of the same level set used to generate the mesh."""
    coordinates = ((vertices - origin) / voxel).T
    normal = -np.stack([map_coordinates(g, coordinates, order=1, mode='constant')
                        for g in np.gradient(density, voxel)], axis=1)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    return normal.astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--state', type=Path, default=root / 'outputs' / 'mpm-state.npz')
    parser.add_argument('--output', type=Path, default=root / 'outputs' / 'mpm-surface.npz')
    parser.add_argument('--kernel-width', type=float, default=None)
    args = parser.parse_args()
    data = np.load(args.state)
    particles, times, knives = data['particles'], data['time_s'], data['knife_positions']
    meta = json.loads(args.state.with_suffix('.json').read_text(encoding='utf-8'))
    spacing = meta['particle_spacing_m']
    kernel_width = args.kernel_width or meta.get('reconstruction_kernel_width_m', max(spacing, 0.5 / meta['grid_density']))
    voxel = kernel_width / 3
    origin = np.floor((particles.min(axis=(0, 1)) - 2 * kernel_width) / voxel) * voxel
    shape = tuple((np.ceil((particles.max(axis=(0, 1)) + 2 * kernel_width - origin) / voxel).astype(int) + 1).tolist())
    vertices, faces, volumes, missed, normals = [], [], [], [], []
    components, euler = [], []
    surface_motion = []
    previous_density = None
    vo, fo = [0], [0]
    for i, xyz in enumerate(particles):
        density = splat(xyz.astype(np.float64), origin.astype(np.float64), shape, voxel, kernel_width, spacing**3)
        particle_density = map_coordinates(density, ((xyz - origin) / voxel).T, order=1, mode='constant')
        missed.append(int(np.count_nonzero(particle_density < 0.5)))
        v, f, _, _ = marching_cubes(density, 0.5, spacing=(voxel,) * 3,
                                  gradient_direction='ascent', allow_degenerate=False)
        v = (v + origin).astype(np.float32)
        # The level-set normal belongs to the density field, not to the
        # changing marching-cubes triangulation. No geometry is smoothed.
        normals.append(field_normals(density, v, origin, voxel))
        p99_motion = 0.0
        if previous_density is not None and times[i] > 0.5:
            old_i = max(0, int(np.searchsorted(times, times[i] - 0.5)) - 1)
            blade_back = (knives[old_i, 0] + meta['knife_collider_xy_offset_m'][0]
                          - meta['knife_collider_size_m'][0] / 2
                          - meta['contact_parameters']['range_m'] - 2 / meta['grid_density'])
            settled = v[v[:, 0] < blade_back]
            if len(settled):
                coordinates = ((settled - origin) / voxel).T
                old_value = map_coordinates(previous_density, coordinates, order=1, mode='constant')
                gradient = np.stack([map_coordinates(g, coordinates, order=1, mode='constant')
                                     for g in np.gradient(previous_density, voxel)], axis=1)
                # Normal displacement of the same continuous level set; mesh
                # vertices can slide along grid edges without surface motion.
                normal_motion = np.abs(old_value - 0.5) / np.maximum(np.linalg.norm(gradient, axis=1), 1.0)
                p99_motion = float(np.percentile(normal_motion, 99))
        surface_motion.append(p99_motion)
        previous_density = density
        a, b, c = (v[f[:, j]].astype(np.float64) for j in range(3))
        volume = float(np.einsum('ij,ij->', a, np.cross(b, c)) / 6)
        if volume < 0:
            f = f[:, ::-1].copy()
            volume = -volume
        vertices.append(v); faces.append(f.astype(np.int32)); volumes.append(volume)
        edges = np.unique(np.sort(np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]])), axis=1), axis=0)
        graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(v), len(v)))
        components.append(int(connected_components(graph, directed=False, return_labels=False)))
        euler.append(int(len(v) - len(edges) + len(f)))
        vo.append(vo[-1] + len(v)); fo.append(fo[-1] + len(f))
        if i % 24 == 0:
            print(f'frame={i} below half density={missed[-1]} components={components[-1]} Euler={euler[-1]} volume={volume:.6g}', flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, vertices=np.concatenate(vertices), faces=np.concatenate(faces),
                        normals=np.concatenate(normals), normal_method='density_gradient',
                        vertex_offsets=np.asarray(vo, np.int32), face_offsets=np.asarray(fo, np.int32),
                        material_volume_m3=np.asarray(volumes), particles_below_isovalue=np.asarray(missed),
                        component_count=np.asarray(components), euler_characteristic=np.asarray(euler),
                        settled_surface_p99_motion_m=np.asarray(surface_motion),
                        reconstruction_method='continuous_mass_density', voxel_size_m=voxel,
                        state_sha256=hashlib.sha256(args.state.read_bytes()).hexdigest(),
                        kernel_width_m=kernel_width)
    report = dict(normal_method='density_gradient', initial_particles_below_isovalue=missed[0], max_particles_below_isovalue=max(missed), final_particles_below_isovalue=missed[-1],
                  max_components=max(components), minimum_euler=min(euler),
                  final_volume_ratio=volumes[-1] / (len(particles[0]) * spacing**3))
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
