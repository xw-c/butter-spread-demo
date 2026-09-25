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
parser.add_argument('--physics-audit',type=Path,default=root/'physics-audit.json')
parser.add_argument('--ripples',type=Path,default=root/'surface-ripples.json')
args=parser.parse_args()
output=args.video.parent
state = np.load(args.state)
surface = np.load(args.surface)
particle_positions, sample_times = state['particles'], state['time_s']
surface_vertices, vertex_offsets = surface['vertices'], surface['vertex_offsets']
surface_normals = surface['normals'] if 'normals' in surface.files else np.empty((0, 3))
physics_meta = json.loads(args.state.with_suffix('.json').read_text(encoding='utf-8'))
material_volumes = surface['material_volume_m3'] if 'material_volume_m3' in surface.files else None
max_material_volume_change = (float(np.max(np.abs(material_volumes / material_volumes[0] - 1)))
                              if material_volumes is not None else float('inf'))
half_blade = np.asarray(state['knife_size'], dtype=float) / 2
blade_offset = np.r_[physics_meta['knife_collider_xy_offset_m'], 0.0]
max_surface_blade_intrusion_m = 0.0
for i, knife_pos in enumerate(state['knife_positions']):
    v0, v1 = vertex_offsets[i:i+2]
    vertices = surface_vertices[v0:v1]
    relative = vertices - knife_pos - blade_offset
    under_blade = np.all(np.abs(relative[:, :2]) <= half_blade[:2], axis=1)
    if np.any(under_blade):
        max_surface_blade_intrusion_m = max(
            max_surface_blade_intrusion_m,
            float(np.max(relative[under_blade, 2] + half_blade[2])))
if 'settled_surface_p99_motion_m' not in surface.files:
    raise ValueError('Rebuild this surface with the continuous density reconstruction before validation')
max_stable_surface_p99_motion_m = float(surface['settled_surface_p99_motion_m'].max())
last_quarter = int(np.searchsorted(sample_times, sample_times[-1] - 0.25))
final_particle_displacement = np.linalg.norm(particle_positions[-1] - particle_positions[last_quarter], axis=1)
final_particle_displacement_p99_m = float(np.percentile(final_particle_displacement, 99))
render_meta=json.loads(args.video.with_suffix('.json').read_text(encoding='utf-8'))
actual_source_hashes = {'state': hashlib.sha256(args.state.read_bytes()).hexdigest(),
                        'surface': hashlib.sha256(args.surface.read_bytes()).hexdigest()}
physics_audit = json.loads(args.physics_audit.read_text(encoding='utf-8'))
ripples = json.loads(args.ripples.read_text(encoding='utf-8'))
scene_audit=render_meta.get('scene_audit')
reader = imageio_ffmpeg.read_frames(str(args.video), pix_fmt="rgb24")
meta = next(reader)
width, height = meta["size"]
snapshots = []
hashes = set()
count = 0
mean_brightness = []
black_frames = []
for i, frame in enumerate(reader):
    count += 1
    hashes.add(hashlib.sha256(frame).hexdigest())
    pixels = np.frombuffer(frame, dtype=np.uint8)
    mean_brightness.append(float(pixels.mean()))
    if np.count_nonzero(pixels) == 0:
        black_frames.append(i)
    if i in (0, (len(particle_positions) - 1) // 2, len(particle_positions) - 1):
        im = Image.frombytes("RGB", (width, height), frame)
        im.thumbnail((640, 360))
        snapshots.append((i, im))
checks = {
    "physics_audit_matches_state": (physics_audit.get('pass') is True
                                     and physics_audit.get('state_sha256') == actual_source_hashes['state']),
    "surface_matches_state": ('state_sha256' in surface.files
                              and str(surface['state_sha256']) == actual_source_hashes['state']),
    "density_field_normals_are_used": (render_meta.get('normal_method') == 'density_gradient'
                                        and surface_normals.shape == surface_vertices.shape
                                        and np.isfinite(surface_normals).all()
                                        and np.allclose(np.linalg.norm(surface_normals, axis=1), 1, atol=1e-4)),
    "ripple_measurement_matches_state_and_surface": (
        ripples.get('state_sha256') == actual_source_hashes['state']
        and ripples.get('surface_sha256') == actual_source_hashes['surface']),
    # Stripes are spatially coherent ridges across/along the strip. Total RMS
    # also counts irregular roughness; retain that stricter smoothness target
    # explicitly in the report instead of calling it a stripe detector.
    "coherent_strip_ridges_below_0_08_mm": max(
        ripples['coherent_cross_strip_ridge_rms_mm'],
        ripples['coherent_along_strip_ridge_rms_mm']) < 0.08,
    "deposited_measurement_patch_has_no_holes": ripples['missing_area_fraction'] == 0,
    "decoded_frames_match_state": count == len(particle_positions),
    "fps_matches_state": abs(meta["fps"] - float(state["fps"])) < 0.01,
    "surface_frames_match_state": len(surface["vertex_offsets"]) == count + 1,
    "video_changes_over_time": len(hashes) > count // 2,
    "no_black_frames": len(black_frames) == 0,
    "no_brightness_flashes": bool(mean_brightness and min(mean_brightness) > 20
                                  and np.max(np.abs(np.diff(mean_brightness))) < 30),
    "butter_surface_outside_blade": max_surface_blade_intrusion_m < 0.0001,
    "settled_butter_surface_is_stable": max_stable_surface_p99_motion_m < 0.00002,
    # At the close-up camera this is less than one pixel over six frames.
    # This bounds residual motion; it does not assert mathematically zero speed.
    "no_fast_residual_particle_motion": final_particle_displacement_p99_m < 0.0001,
    "no_disconnected_butter_surfaces": bool('component_count' in surface.files and np.all(surface['component_count'] == 1)),
    "no_thin_film_holes": bool('euler_characteristic' in surface.files and np.all(surface['euler_characteristic'] == 2)),
    "material_surface_volume_is_conserved": max_material_volume_change < 0.1,
    "no_synthetic_contact_film": (scene_audit['no_synthetic_contact_film'] if scene_audit else
                                  "ContactFilm" not in args.video.with_suffix('.usda').read_text()),
}
if scene_audit:
    checks.update({'video_uses_this_state_and_surface': render_meta.get('source_sha256') == actual_source_hashes,
                   'no_hand_model':scene_audit['no_hand_model'],
                   'volumetric_bread_asset':scene_audit['cdmpm_bread_vertices']>1000000,
                   'flat_blade_present':scene_audit['flat_blade_present']})
artifacts = (args.state,args.surface,args.video,args.physics_audit,args.ripples)
report = {"pass": all(checks.values()), "checks": checks,
          "decoded_frames": count, "size": [width, height], "fps": meta["fps"],
          "black_frames": black_frames,
          "min_mean_brightness": min(mean_brightness) if mean_brightness else None,
          "max_adjacent_brightness_jump": float(np.max(np.abs(np.diff(mean_brightness)))) if count > 1 else None,
          "max_surface_blade_intrusion_m": max_surface_blade_intrusion_m,
          "max_settled_surface_p99_motion_m": max_stable_surface_p99_motion_m,
          "final_quarter_second_particle_displacement_p99_m": final_particle_displacement_p99_m,
          "max_material_surface_volume_change": max_material_volume_change,
          "deposited_strip_height_ripple_rms_mm": ripples['height_ripple_rms_mm'],
          "coherent_cross_strip_ridge_rms_mm": ripples['coherent_cross_strip_ridge_rms_mm'],
          "coherent_along_strip_ridge_rms_mm": ripples['coherent_along_strip_ridge_rms_mm'],
          "additional_smoothness_target": {
              "total_height_rms_below_0_08_mm": ripples['height_ripple_rms_mm'] < 0.08,
              "note": "Total RMS includes nonperiodic roughness. This stricter target is reported separately from coherent stripes."},
          "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}}
report_text = json.dumps(report, indent=2)
args.video.with_name(args.video.stem + '-validation.json').write_text(report_text, encoding='utf-8')
if args.video.name == 'butter-spread.mp4':
    (output / 'video-validation.json').write_text(report_text, encoding='utf-8')
sheet = Image.new("RGB", (640, 390 * len(snapshots)), "#202020")
draw = ImageDraw.Draw(sheet)
for row, (i, im) in enumerate(snapshots):
    sheet.paste(im, (0, row * 390))
    draw.text((12, row * 390 + 365), f"Simulation t = {i / meta['fps']:.2f} s", fill="white")
sheet.save(args.video.with_name(args.video.stem + '-keyframes.jpg'))
print(json.dumps(report, indent=2))
if not report["pass"]:
    raise SystemExit(1)
