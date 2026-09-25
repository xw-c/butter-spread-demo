"""Measure particle motion and thickness; never alter the simulation state."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

parser = argparse.ArgumentParser()
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
data = np.load(args.state)
meta = json.loads(args.state.with_suffix('.json').read_text(encoding='utf-8'))
p, bread, times, knife = (data[k] for k in ('particles', 'bread_particles', 'time_s', 'knife_positions'))
velocities = data['particle_velocities'] if 'particle_velocities' in data.files else None
spacing = meta['particle_spacing_m']
bread_spacing = meta.get('bread_particle_spacing_m', spacing)
top_ids = np.flatnonzero(bread[0, :, 2] > bread[0, :, 2].max() - bread_spacing / 2)
age = np.zeros(p.shape[1])
rows = []
for i in range(1, len(p)):
    dt = times[i] - times[i - 1]
    speed = np.linalg.norm(p[i] - p[i - 1], axis=1) / dt
    # Include every particle sufficiently far behind the blade, rather than
    # checking only one fixed rectangle that excludes the end of the spread.
    blade_back = knife[i, 0] + meta['knife_collider_xy_offset_m'][0] - meta['knife_collider_size_m'][0] / 2
    deposited = p[i, :, 0] < blade_back - meta['contact_parameters']['range_m'] - 2 / meta['grid_density']
    age = np.where(deposited, age + dt, 0)
    settled = age >= 0.5
    surface = bread[i, top_ids]
    _, near = cKDTree(surface[:, :2]).query(p[i, :, :2], k=4)
    bread_height = np.mean(surface[near, 2], axis=1) + bread_spacing / 2
    thickness = p[i, :, 2] + spacing / 2 - bread_height
    row = dict(time_s=float(times[i]),
               center_height_above_bread_mm=np.percentile(thickness * 1000, [10, 50, 90]).tolist(),
               all_speed_mm_s=np.percentile(speed * 1000, [50, 95, 99, 100]).tolist(),
               settled_particle_count=int(settled.sum()),
               settled_speed_mm_s=(np.percentile(speed[settled] * 1000, [50, 95, 99, 100]).tolist()
                                   if settled.any() else None))
    if velocities is not None:
        v = np.linalg.norm(velocities[i], axis=1)
        row['instantaneous_speed_mm_s'] = np.percentile(v * 1000, [50, 95, 99, 100]).tolist()
    rows.append(row)
last = np.searchsorted(times, times[-1] - 0.25)
initial_pairs = cKDTree(p[0]).query_pairs(1.05 * spacing, output_type='ndarray')
final_neighbor_distance = np.linalg.norm(p[-1, initial_pairs[:, 0]] - p[-1, initial_pairs[:, 1]], axis=1)
report = dict(state=str(args.state), percentiles=[50, 95, 99, 100],
              final_initial_neighbor_distance_mm=np.percentile(final_neighbor_distance * 1000, [50, 95, 99, 100]).tolist(),
              final_quarter_second_displacement_mm=np.percentile(
                  np.linalg.norm(p[-1] - p[last], axis=1) * 1000, [50, 95, 99, 100]).tolist(),
              final_frame=rows[-1], frames=rows)
args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'frames'}, indent=2))
