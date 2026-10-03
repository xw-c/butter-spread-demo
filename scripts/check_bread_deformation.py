"""Analytic regressions for material-space bread mesh embedding."""
import ast
from pathlib import Path

import numpy as np
from bread_deformation import BreadDeformation

root = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(31)
axes = [np.linspace(-.015, .015, n) for n in (13, 11, 9)]
particles = np.stack(np.meshgrid(*axes, indexing='ij'), axis=-1).reshape(-1, 3).astype(np.float32)
rng.shuffle(particles)
extent = np.array([.015 + .5 * (a[1]-a[0]) for a in axes])
vertices = rng.uniform(-extent, extent, (2000, 3)).astype(np.float32)
normals = rng.normal(size=vertices.shape)
normals = (normals / np.linalg.norm(normals, axis=1, keepdims=True)).astype(np.float32)
binding = BreadDeformation(particles, vertices, normals)
rest, rest_normals, _ = binding.deform(particles)
assert np.array_equal(rest, vertices)
assert np.allclose(rest_normals, normals, atol=1e-7)

angle = .35
rotation = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0],
                     [-np.sin(angle), 0, np.cos(angle)]])
for F in (np.eye(3), rotation, rotation @ np.array([[1, .17, 0], [0, 1, 0], [0, 0, .73]])):
    translation = np.array([.002, -.004, .001])
    moved, changed_normals, determinant = binding.deform(particles @ F.T + translation)
    expected = vertices @ F.T + translation
    expected_normals = normals @ np.linalg.inv(F)
    expected_normals /= np.linalg.norm(expected_normals, axis=1, keepdims=True)
    assert np.allclose(moved, expected, atol=1e-8)
    assert np.allclose(changed_normals, expected_normals, atol=5e-6)
    assert abs(determinant - np.linalg.det(F)) < 5e-6
assert np.array_equal(binding.deform(particles)[0], vertices), 'Frame updates must not accumulate'
try:
    binding.deform(particles * np.array([1, 1, -1]))
except ValueError:
    pass
else:
    raise AssertionError('Inverted deformation must fail')

# Compare demo parameters with the bundled snapshot of the Genesis calibration.
import json
cream = json.loads((root / 'physics/genesis-bread-defaults.json').read_text())
tree = ast.parse((root/'scripts/simulate_mpm.py').read_text())
bread = next(n.value for n in tree.body if isinstance(n, ast.Assign)
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'BREAD')
parameters = {k.arg: ast.literal_eval(k.value) for k in bread.keywords}
for name, value in parameters.items():
    assert value == cream['DEFAULT_BREAD_' + name.upper()], name
print('PASS: rest pose, shuffled particle order, translation, rotation, compression/shear, boundary extrapolation, normal transport, no accumulation, inversion rejection, Genesis bread parameters.')
