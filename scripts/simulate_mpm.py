"""Run a level-blade press and spread with the calibrated Genesis MPM materials."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
GENESIS = WORKSPACE / "genesis-world"
CREAM = GENESIS / "examples" / "cream"
if not CREAM.is_dir():
    raise RuntimeError(f"Missing calibrated material sources: {CREAM}")
sys.path.insert(0, str(GENESIS))
sys.path.insert(0, str(CREAM))

import genesis as gs
from knife_motion import knife_pose, PRESS_END_S, ACCEL_END_S, SPREAD_END_S, LIFT_END_S

FPS = 24
BREAD_TOP = 0.026
BREAD_SIZE = (0.14, 0.114, 0.016)
BREAD_CENTER = (0.0, 0.0, BREAD_TOP - BREAD_SIZE[2] / 2)
PLATE_HEIGHT = 0.010
# The visual plate is shallow, but the collision support needs a volume below
# its top. A 2 mm rigid slab gives the MPM grid a poorly resolved signed
# distance field and lets the entire bread sheet travel with the knife.
SUPPORT_DEPTH = 0.020
BUTTER_SIZE = (0.040, 0.030, 0.018)
BUTTER_CENTER = (-0.040, 0.0, 0.035)
# Approximate the visible 20 x 95 mm blade, including its asymmetric outline.
KNIFE_SIZE = (0.020, 0.095, 0.005)
KNIFE_CENTER_XY = (0.0021, 0.0035)

HB = dict(shear_modulus=20000.0, bulk_modulus=150000.0,
          yield_stress=80.0, consistency=25.0, flow_exponent=0.5, rho=900.0)
BREAD = dict(E=16000.0, nu=0.15, rho=280.0,
             compaction_yield_pressure=650.0, compaction_hardening=5200.0,
             densification_strain=0.32, densification_hardening=45000.0,
             min_plastic_volume_ratio=0.35, shear_yield_stress=700.0,
             shear_hardening=7000.0)
CONTACT = dict(bread_stress=450.0, blade_stress=100.0,
               bread_shear_stress=650.0, blade_shear_stress=150.0,
               bread_slip_time=0.008, blade_slip_time=0.008)
CONTACT_RANGE_M = 0.002916666666666667
BREAD_CONTACT_RANGE_M = 0.0015
BLADE_NORMAL_RELAXATION_TIME_S = 0.005
BLADE_MAX_SEPARATION_SPEED = 0.35
BLADE_CONTACT_MARGIN_M = 0.001875


def particle_positions(entity):
    return entity.get_particles_pos().detach().cpu().numpy().astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=round(LIFT_END_S * FPS) + 1)
    parser.add_argument("--backend", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument("--dt", type=float, default=3.5e-5)
    parser.add_argument("--grid-density", type=int, default=512)
    parser.add_argument("--particle-size", type=float, default=0.001)
    parser.add_argument("--butter-particle-size", type=float, default=0.0005)
    parser.add_argument("--butter-sampling", choices=('regular', 'stratified'), default='stratified')
    parser.add_argument("--cpic", action=argparse.BooleanOptionalAction, default=True,
                        help="enable the optional rigid-interface CPIC transfer for comparison")
    parser.add_argument("--knife-thickness", type=float, default=KNIFE_SIZE[2])
    parser.add_argument("--blade-stress", type=float, default=CONTACT["blade_stress"])
    parser.add_argument("--blade-shear-stress", type=float, default=CONTACT["blade_shear_stress"])
    parser.add_argument("--blade-normal-relaxation-time", type=float, default=BLADE_NORMAL_RELAXATION_TIME_S)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
    args = parser.parse_args()
    if not 2 <= args.frames <= round(LIFT_END_S * FPS) + 1:
        parser.error(f"--frames must be in [2, {round(LIFT_END_S * FPS) + 1}]")
    if not 0 < args.dt <= 5e-5 or args.grid_density < 128 or not 0 < args.particle_size <= 0.002:
        parser.error("dt must be in (0, 5e-5], grid density >= 128, particle size in (0, 2 mm]")
    if args.dt > 0.02 / args.grid_density:
        parser.error('dt exceeds the Genesis recommended step for this grid density')
    if not 0 < args.butter_particle_size <= args.particle_size:
        parser.error("butter particle size must be positive and no larger than bread particle size")
    if not 0 < args.knife_thickness <= 0.012 or args.blade_stress < 0 or args.blade_shear_stress < 0:
        parser.error("knife thickness must be in (0, 12 mm], blade stresses must be nonnegative")
    if args.blade_normal_relaxation_time < args.dt:
        parser.error("blade normal relaxation time must be at least one time step")
    knife_size = (KNIFE_SIZE[0], KNIFE_SIZE[1], args.knife_thickness)
    contact_parameters = {**CONTACT, "blade_stress": args.blade_stress,
                          "blade_shear_stress": args.blade_shear_stress}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GS_CACHE_FILE_PATH", str(WORKSPACE / ".cache" / "genesis"))
    started = time.perf_counter()

    gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu,
            logging_level="warning", theme="dumb")
    from cream_contact import ButterContact
    from cream_materials import HerschelBulkleyButter, PorousBread
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=args.dt, substeps=1, gravity=(0, 0, -9.81)),
        mpm_options=gs.options.MPMOptions(
            dt=args.dt, gravity=(0, 0, -9.81),
            lower_bound=(-0.12, -0.08, -0.02), upper_bound=(0.12, 0.08, 0.11),
            particle_size=args.particle_size, grid_density=args.grid_density,
            enable_CPIC=args.cpic),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_mpm=True),
        show_viewer=False)
    # The visual plate is unchanged. This fixed physical support carries the
    # newly deformable bread where the old rigid bread collider stood.
    scene.add_entity(
        morph=gs.morphs.Box(lower=(-0.09, -0.07, PLATE_HEIGHT - SUPPORT_DEPTH),
                             upper=(0.09, 0.07, PLATE_HEIGHT), fixed=True),
        material=gs.materials.Rigid(
            rho=700, friction=0.9, coup_friction=1.0, coup_restitution=0,
            coup_softness=0.001, needs_coup=True, sdf_cell_size=0.0015,
            sdf_min_res=32, sdf_max_res=128))
    bread = scene.add_entity(
        morph=gs.morphs.Box(pos=BREAD_CENTER, size=BREAD_SIZE),
        material=PorousBread(**BREAD, sampler="regular"),
        surface=gs.surfaces.Plastic(color=(0.72, 0.55, 0.35), roughness=0.9),
        vis_mode="particle")
    initial = knife_pose(0)
    knife = scene.add_entity(
        morph=gs.morphs.Box(
            pos=(float(initial[0] + KNIFE_CENTER_XY[0]), KNIFE_CENTER_XY[1], float(initial[2])),
            size=knife_size),
        material=gs.materials.Rigid(
            rho=7800, friction=0.65, coup_friction=0.12,
            coup_restitution=0, coup_softness=0.001, needs_coup=True,
            sdf_cell_size=0.001, sdf_min_res=32, sdf_max_res=128))
    butter = scene.add_entity(
        morph=gs.morphs.Box(pos=BUTTER_CENTER, size=BUTTER_SIZE),
        material=HerschelBulkleyButter(**HB, dt=args.dt, sampler="regular", particle_size=args.butter_particle_size),
        surface=gs.surfaces.Plastic(color=(0.97, 0.78, 0.30), roughness=0.3),
        vis_mode="particle")
    scene.build()

    # One-time placement of regularly sampled particles. Contact and MPM
    # determine all subsequent motion; there are no spring anchors.
    bread_pos = bread.get_particles_pos()
    bread_pos[:, 2] += PLATE_HEIGHT + args.particle_size / 2 - bread_pos[:, 2].min()
    bread.set_particles_pos(bread_pos)
    bread.set_particles_vel(gs.zeros_like(bread_pos))
    bread_top_initial = float(bread.get_particles_pos()[:, 2].max().item())
    butter_pos = butter.get_particles_pos()
    # Two material cell centers must be one full spacing apart at contact.
    # Half a spacing made the initial butter overlap the top bread cells.
    butter_pos[:, 2] += bread_top_initial + 0.5 * (args.particle_size + args.butter_particle_size) - butter_pos[:, 2].min()
    if args.butter_sampling == 'stratified':
        # One integration point per material cell, with the same cell volume.
        # Break coherent lattice planes in the *initial quadrature*, not by
        # moving, filtering or jittering particles during the simulation.
        rng = np.random.default_rng(17)
        offsets = rng.uniform(-0.45, 0.45, size=tuple(butter_pos.shape)) * args.butter_particle_size
        butter_pos += gs.tensor(offsets.astype(np.float32))
    butter.set_particles_pos(butter_pos)
    butter.set_particles_vel(gs.zeros_like(butter_pos))

    range_multiplier = CONTACT_RANGE_M / args.butter_particle_size
    contact = ButterContact(
        bread, butter, args.butter_particle_size, args.dt, knife_size,
        contact_parameters["bread_stress"], contact_parameters["blade_stress"],
        BREAD_CONTACT_RANGE_M / args.butter_particle_size, contact_parameters["bread_slip_time"], contact_parameters["bread_shear_stress"],
        range_multiplier, contact_parameters["blade_slip_time"], contact_parameters["blade_shear_stress"],
        # A fixed physical relaxation time keeps the contact response invariant
        # under time-step refinement. A constant per-step fraction did not.
        blade_normal_relaxation=args.dt / args.blade_normal_relaxation_time,
        blade_max_separation_speed=BLADE_MAX_SEPARATION_SPEED,
        blade_contact_margin_multiplier=BLADE_CONTACT_MARGIN_M / args.butter_particle_size,
        equilibrium_adhesion=True)
    frames = [particle_positions(butter)]
    velocity_frames = [butter.get_particles_vel().detach().cpu().numpy().astype(np.float32)]
    bread_frames = [particle_positions(bread)]
    poses = [knife_pose(0)]
    sample_times = [0.0]
    frame_steps = [round(i / FPS / args.dt) for i in range(args.frames)]
    print(f"Genesis MPM: {frame_steps[-1]} steps, {butter.n_particles} butter "
          f"and {bread.n_particles} bread particles", flush=True)
    for step in range(frame_steps[-1]):
        t = step * args.dt
        pose, next_pose = knife_pose(t), knife_pose(t + args.dt)
        center = pose + np.array([*KNIFE_CENTER_XY, 0], dtype=np.float32)
        velocity = (next_pose - pose) / args.dt
        knife.set_pos(gs.tensor(center[None, :]), zero_velocity=False,
                      relative=False, skip_forward=True)
        knife.set_dofs_velocity(
            gs.tensor(np.r_[velocity, np.zeros(3, np.float32)][None, :]))
        contact.apply(scene.sim.cur_substep_local,
                      tuple(float(v) for v in center),
                      tuple(float(v) for v in velocity), 0.0, 0.0, 0.0)
        scene.step()
        if step + 1 == frame_steps[len(frames)]:
            frames.append(particle_positions(butter))
            velocity_frames.append(butter.get_particles_vel().detach().cpu().numpy().astype(np.float32))
            bread_frames.append(particle_positions(bread))
            poses.append(knife_pose((step + 1) * args.dt))
            sample_times.append((step + 1) * args.dt)
            if len(frames) == 2 or len(frames) % 12 == 1 or len(frames) == args.frames:
                p = frames[-1]
                print(f"frame={len(frames)-1}/{args.frames-1} "
                      f"t={sample_times[-1]:.3f}s "
                      f"x=[{p[:,0].min():.4f},{p[:,0].max():.4f}]", flush=True)

    butter_frames, bread_frames = np.stack(frames), np.stack(bread_frames)
    if not np.isfinite(butter_frames).all() or not np.isfinite(bread_frames).all():
        raise RuntimeError("Non-finite Genesis MPM particle state")
    np.savez_compressed(
        args.output, particles=butter_frames, particle_velocities=np.stack(velocity_frames), bread_particles=bread_frames,
        knife_positions=np.stack(poses), time_s=np.asarray(sample_times), fps=FPS,
        bread_center=np.asarray(BREAD_CENTER), bread_size=np.asarray(BREAD_SIZE),
        knife_size=np.asarray(knife_size))
    report = dict(
        solver="Genesis MPM", butter_material="HerschelBulkleyButter / Yue et al. TOG 2015",
        bread_material="PorousBread",
        contact_model="equilibrium cohesive zone and bounded wall slip",
        particle_constraints=False, material_point_deletion=False,
        backend=args.backend, fps=FPS, frames=len(frames), dt_s=args.dt,
        grid_density=args.grid_density, particle_spacing_m=args.butter_particle_size,
        bread_particle_spacing_m=args.particle_size,
        butter_sampling=args.butter_sampling,
        reconstruction_kernel_width_m=1.0 / 768,
        enable_CPIC=args.cpic,
        total_steps=frame_steps[-1], butter_particle_count=butter.n_particles,
        butter_mass_kg=float(butter.get_mass().item()),
        butter_reference_volume_m3=butter.n_particles * args.butter_particle_size**3,
        bread_particle_count=bread.n_particles, butter_parameters=HB,
        bread_parameters=BREAD,
        contact_parameters={**contact_parameters, "range_m": CONTACT_RANGE_M,
                            "bread_range_m": BREAD_CONTACT_RANGE_M, "equilibrium_adhesion": True},
        blade_normal_relaxation=args.dt / args.blade_normal_relaxation_time,
        blade_normal_relaxation_time_s=args.blade_normal_relaxation_time,
        blade_max_separation_speed_m_s=BLADE_MAX_SEPARATION_SPEED,
        blade_contact_margin_m=BLADE_CONTACT_MARGIN_M,
        knife_collider_size_m=knife_size,
        knife_collider_xy_offset_m=KNIFE_CENTER_XY,
        bread_support_height_m=PLATE_HEIGHT,
        bread_support_depth_m=SUPPORT_DEPTH,
        knife_motion="level blade: smooth press, continuous spread, end lift",
        motion_phases_s=dict(press_end=PRESS_END_S, accel_end=ACCEL_END_S,
                             spread_end=SPREAD_END_S, lift_end=LIFT_END_S),
        butter_initial_size_m=BUTTER_SIZE,
        initial_bread_top_m=bread_top_initial,
        elapsed_wall_s=round(time.perf_counter() - started, 2))
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
