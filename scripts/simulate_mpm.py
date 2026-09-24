"""Three-second butter spreading experiment using the pinned Genesis MPM solver.

All positions are metres. The bread is a fixed rigid boundary, the butter is
MPM.ElastoPlastic, and the knife blade is a prescribed rigid collider. The
output is solver particle state, not a painted-on animation.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SOURCE = REPO / "coffee-milk-demo" / "reference" / "genesis-world-mopping-simplified"
os.environ.setdefault("GS_CACHE_FILE_PATH", str(REPO / "coffee-milk-demo" / "reference" / "genesis-cache"))
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
sys.path.insert(0, str(SOURCE))
import genesis as gs
import genesis.utils.geom as genesis_geom
from scipy.spatial.transform import Rotation
import quadrants.lang._fast_caching.src_hasher as qd_src_hasher

# Same Windows runtime workarounds already used by coffee-milk-demo.
genesis_geom.euler_to_R = lambda xyz: Rotation.from_euler("xyz", xyz, degrees=True).as_matrix()
qd_src_hasher.store = lambda *args, **kwargs: None

FPS = 24
DT = 1 / FPS
PHYSICS_HZ = 240
BREAD_TOP = 0.026
BREAD_SIZE = (0.14, 0.10, 0.024)
BREAD_CENTER = (0.0, 0.0, BREAD_TOP - BREAD_SIZE[2] / 2)
KNIFE_SIZE = (0.012, 0.070, 0.012)


def knife_pose(t):
    """Blade descends, sweeps in +X, then lifts clear of the spread."""
    if t < 0.30:
        x, z = -0.068, 0.050 - 0.0175 * t / 0.30
    elif t < 2.55:
        u = (t - 0.30) / 2.25
        x, z = -0.068 + 0.136 * u, 0.0325
    else:
        x, z = 0.068, 0.0325 + 0.025 * (t - 2.55) / 0.45
    return np.array([x, 0.0, z], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=73)
    parser.add_argument("--backend", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--adhesion", type=float, default=8.0)
    parser.add_argument("--anchor-stride", type=int, default=8,
                        help="retain one bread adhesion anchor per N bottom particles")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
    args = parser.parse_args()
    if not 2 <= args.frames <= 73:
        parser.error("--frames must be in [2, 73]")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu,
            precision="32", logging_level="warning")
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=1 / PHYSICS_HZ, substeps=32),
        mpm_options=gs.options.MPMOptions(
            lower_bound=(-0.12, -0.08, 0.0),
            upper_bound=(0.12, 0.08, 0.11),
            particle_size=0.0025, grid_density=128),
        show_viewer=False,
    )
    bread = scene.add_entity(
        morph=gs.morphs.Box(pos=BREAD_CENTER, size=BREAD_SIZE, fixed=True),
        material=gs.materials.Rigid(needs_coup=True, coup_friction=5.0,
                                    coup_softness=0.0005,
                                    is_coup_reaction_enabled=False),
    )
    knife = scene.add_entity(
        morph=gs.morphs.Box(pos=knife_pose(0).tolist(), size=KNIFE_SIZE),
        material=gs.materials.Rigid(needs_coup=True, coup_friction=5.0,
                                    coup_softness=0.0002,
                                    gravity_compensation=1.0,
                                    is_coup_reaction_enabled=False),
    )
    butter = scene.add_entity(
        morph=gs.morphs.Box(pos=(-0.044, 0.0, 0.031),
                            size=(0.028, 0.025, 0.009)),
        material=gs.materials.MPM.ElastoPlastic(
            E=1.0e3, nu=0.35, rho=910,
            use_von_mises=True, von_mises_yield_stress=15.0,
            sampler="regular"),
        surface=gs.surfaces.Default(color=(0.97, 0.78, 0.30),
                                    vis_mode="particle"),
    )
    scene.build()
    # The first layer grips the porous bread. Genesis spring constraints are
    # used for this adhesion boundary; the unpinned upper layers remain MPM.
    adhered = butter.get_particles_in_bbox(
        (-0.070, -0.030, BREAD_TOP), (0.0, 0.030, BREAD_TOP + 0.003))
    if args.anchor_stride < 1:
        parser.error("--anchor-stride must be positive")
    original_mask = adhered.detach().cpu().numpy()
    anchor_ids = np.flatnonzero(original_mask)[::args.anchor_stride]
    sparse_mask = np.zeros_like(original_mask, dtype=bool)
    sparse_mask.flat[anchor_ids] = True
    adhered = torch.as_tensor(sparse_mask, device=adhered.device)
    adhered_count = int(adhered.sum().item())
    butter.set_particle_constraints(adhered, bread.links[0].idx,
                                    stiffness=args.adhesion)
    print(f"Adhered bottom-layer particles: {adhered_count}", flush=True)
    frames, poses, statistics = [], [], []
    for i in range(args.frames):
        t = i * DT
        if i:
            for j in range(PHYSICS_HZ // FPS):
                current_t = t - DT + (j + 1) / PHYSICS_HZ
                target = knife_pose(current_t)
                previous = knife_pose(current_t - 1 / PHYSICS_HZ)
                knife.set_pos(previous)
                knife.set_dofs_velocity(np.r_[(target - previous) * PHYSICS_HZ,
                                              np.zeros(3, dtype=np.float32)])
                scene.step()
        pose = knife_pose(t)
        positions = butter.get_particles_pos().detach().cpu().numpy().astype(np.float32)
        if not np.isfinite(positions).all():
            raise RuntimeError(f"Non-finite MPM particles at frame {i}")
        if ((positions[:, 2] > 0.07).any() or
                (np.abs(positions[:, 0]) > 0.11).any() or
                (np.abs(positions[:, 1]) > 0.07).any()):
            raise RuntimeError(f"MPM particles escaped bread region at frame {i}")
        frames.append(positions)
        poses.append(pose)
        near_bread = positions[positions[:, 2] < BREAD_TOP + 0.012]
        span = np.ptp(near_bread[:, :2], axis=0) if len(near_bread) else np.zeros(2)
        statistics.append({"frame": i, "time_s": round(t, 5),
                           "particle_count": len(positions),
                           "spread_x_m": float(span[0]),
                           "spread_y_m": float(span[1]),
                           "min_z_m": float(positions[:, 2].min()),
                           "max_z_m": float(positions[:, 2].max())})
        if i % 12 == 0:
            print(json.dumps(statistics[-1]), flush=True)
    np.savez_compressed(args.output, particles=np.stack(frames),
                        knife_positions=np.stack(poses), fps=FPS,
                        bread_center=np.asarray(BREAD_CENTER),
                        bread_size=np.asarray(BREAD_SIZE),
                        knife_size=np.asarray(KNIFE_SIZE))
    report = {"solver": "Genesis MPM.ElastoPlastic", "frames": args.frames,
              "fps": FPS, "backend": args.backend,
              "adhered_particle_count": adhered_count,
              "initial_spread_x_m": statistics[0]["spread_x_m"],
              "final_spread_x_m": statistics[-1]["spread_x_m"],
              "statistics": statistics}
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
