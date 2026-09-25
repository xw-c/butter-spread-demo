"""Check mixed-resolution MPM mass weights and a uniform gravity response."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'genesis-world'))
import genesis as gs

gs.init(backend=gs.cpu, logging_level='warning')
dt = 5e-5
scene = gs.Scene(sim_options=gs.options.SimOptions(dt=dt, substeps=1),
                 mpm_options=gs.options.MPMOptions(dt=dt, particle_size=0.001, grid_density=256,
                                                 lower_bound=(-.06, -.04, 0), upper_bound=(.06, .04, .1)),
                 show_viewer=False)
entities = []
centers = [-5 / 256, 5 / 256]
for x, spacing in zip(centers, [.001, .0005]):
    entities.append(scene.add_entity(
        morph=gs.morphs.Box(pos=(x, 0, .05), size=(.008, .008, .008)),
        material=gs.materials.MPM.Elastic(E=1000, nu=.2, rho=900,
                                         sampler='regular', particle_size=spacing),
        vis_mode='particle'))
scene.build()
info = scene.sim.mpm_solver.particles_info
mass = info.mass.to_numpy() / scene.sim.mpm_solver._particle_volume_scale
volume = info.reference_volume.to_numpy() / scene.sim.mpm_solver._particle_volume_scale
expected_volume = .008**3
for entity in entities:
    sl = slice(entity._particle_start, entity._particle_start + entity.n_particles)
    assert np.isclose(volume[sl].sum(), expected_volume, rtol=1e-5)
    assert np.isclose(mass[sl].sum(), 900 * expected_volume, rtol=1e-5)
    assert np.allclose(volume[sl], entity.particle_size**3, rtol=1e-6, atol=1e-15)
for _ in range(5):
    scene.step()
expected_vz = -9.81 * dt * 5
for entity in entities:
    velocity = entity.get_particles_vel().detach().cpu().numpy()
    assert np.allclose(velocity[:, :2], 0, atol=2e-6)
    assert np.allclose(velocity[:, 2], expected_vz, atol=2e-6)

qd = gs.qd


@qd.kernel
def compress(particles: qd.template(), f: qd.i32, count: qd.i32, coarse_count: qd.i32):
    for i in range(count):
        center = qd.select(i < coarse_count, -5.0 / 256, 5.0 / 256)
        particles[f, i, 0].pos[0] = center + 0.98 * (particles[f, i, 0].pos[0] - center)
        particles[f, i, 0].F = qd.Matrix([[0.98, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        particles[f, i, 0].vel = qd.Vector.zero(gs.qd_float, 3)
        particles[f, i, 0].C = qd.Matrix.zero(gs.qd_float, 3, 3)


compress(scene.sim.mpm_solver.particles, scene.sim.cur_substep_local,
         sum(e.n_particles for e in entities), entities[0].n_particles)
scene.step()
responses = []
for center, entity in zip(centers, entities):
    velocity = entity.get_particles_vel().detach().cpu().numpy()
    position = entity.get_particles_pos().detach().cpu().numpy()
    assert abs(velocity[:, 0].mean()) < 1e-6
    responses.append(float(np.mean(velocity[:, 0] * np.sign(position[:, 0] - center))))
assert min(responses) > 0
assert abs(responses[1] / responses[0] - 1) < 0.1, responses
print('PASS: equal mass/volume, uniform gravity, zero net internal impulse, matching compression response.', responses)
