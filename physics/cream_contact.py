"""Finite-range, dissipative butter contact for the cream demo.

Adds cohesive traction and bounded tangential drag before MPM's normal collision
solve. It never assigns particle positions or attaches particles to a target.
Bread contact uses a height field of its moving surface particles, with the
opposite impulse distributed back to those particles. The blade is prescribed
kinematically, so its reaction is supplied by the external trajectory controller.
This is a tunable visual-demo contact law, not a measured food-material model.
"""

import math

import numpy as np

import genesis as gs

qd = gs.qd


@qd.data_oriented
class ButterContact:
    def __init__(
        self,
        bread,
        butter,
        spacing,
        dt,
        blade_size,
        bread_stress,
        blade_stress,
        bread_range_multiplier=1.5,
        bread_slip_time=0.008,
        bread_shear_stress=650.0,
        blade_range_multiplier=1.5,
        blade_slip_time=0.006,
        blade_shear_stress=600.0,
        blade_normal_relaxation=0.0,
        blade_max_separation_speed=0.35,
        blade_contact_margin_multiplier=0.5,
        equilibrium_adhesion=False,
    ):
        self.solver = butter.solver
        self.particles = self.solver.particles
        self.info = self.solver.particles_info
        self.dt = float(dt)
        self.spacing = float(spacing)
        self.bread_spacing = float(bread.particle_size)
        self.grid_spacing = self.bread_spacing
        self.bread_contact_range = float(bread_range_multiplier) * spacing
        self.blade_contact_range = float(blade_range_multiplier) * spacing
        self.rho = float(butter.material.rho)
        self.bread_stress = float(bread_stress)
        self.blade_stress = float(blade_stress)
        self.bread_slip_time = float(bread_slip_time)
        self.blade_slip_time = float(blade_slip_time)
        self.bread_shear_stress = float(bread_shear_stress)
        self.blade_shear_stress = float(blade_shear_stress)
        self.blade_normal_relaxation = float(blade_normal_relaxation)
        self.blade_max_separation_speed = float(blade_max_separation_speed)
        self.blade_contact_margin = float(blade_contact_margin_multiplier) * spacing
        self.equilibrium_adhesion = bool(equilibrium_adhesion)
        self.half_blade = qd.Vector([v / 2 for v in blade_size])
        self.butter_start = butter._particle_start
        self.butter_end = self.butter_start + butter.n_particles
        self.origin = qd.Vector([-0.25, -0.28])
        self.res = (math.ceil(0.50 / self.grid_spacing) + 2, math.ceil(0.56 / self.grid_spacing) + 2)

        pos = bread.get_particles_pos().detach().cpu().numpy()
        self.surface_local_indices = np.flatnonzero(pos[:, 2] > pos[:, 2].max() - self.bread_spacing * 0.55)
        self.surface_ids = qd.field(qd.i32, shape=len(self.surface_local_indices))
        self.surface_ids.from_numpy((self.surface_local_indices + bread._particle_start).astype(np.int32))
        self.mass = qd.field(gs.qd_float, shape=self.res)
        self.height_mass = qd.field(gs.qd_float, shape=self.res)
        self.momentum = qd.Vector.field(3, gs.qd_float, shape=self.res)
        self.reaction = qd.Vector.field(3, gs.qd_float, shape=self.res)
        self.contacts = qd.field(qd.i32, shape=2)

    @qd.func
    def _cell(self, pos):
        uv = (qd.Vector([pos[0], pos[1]]) - self.origin) / self.grid_spacing
        base = qd.cast(qd.floor(uv), qd.i32)
        return base, uv - base

    @qd.func
    def _weight(self, frac, a, b):
        return (frac[0] if a == 1 else 1 - frac[0]) * (frac[1] if b == 1 else 1 - frac[1])

    @qd.func
    def _valid(self, node):
        return 0 <= node[0] < self.res[0] and 0 <= node[1] < self.res[1]

    @qd.func
    def _impulse_velocity(self, relative_velocity, normal, gap, stress, contact_range, slip_time, shear_stress):
        # A finite separation distance permits peel-off; there are no permanent bonds.
        weight = qd.max(0.0, 1.0 - qd.max(gap, 0.0) / contact_range) ** 2
        normal_weight = weight
        normal_depth = self.spacing
        tangent_depth = self.spacing
        if qd.static(self.equilibrium_adhesion):
            # A cohesive zone pulls separated surfaces together, but supplies
            # no inward traction once the material is already in contact.
            # Constant attraction at negative gaps otherwise acts like an
            # artificial compressive load inside the shared MPM grid.
            separation = qd.min(1.0, qd.max(0.0, gap / contact_range))
            normal_weight = 4.0 * separation * (1.0 - separation)
            # Integrals of 4*s*(1-s) and (1-s)^2 over the physical contact
            # layer. Refining quadrature must not increase total traction.
            normal_depth = 2.0 * contact_range / 3.0
            tangent_depth = contact_range / 3.0 + 0.5 * self.spacing
        dv_normal = -normal * stress * self.dt / (self.rho * normal_depth) * normal_weight
        tangent = relative_velocity - relative_velocity.dot(normal) * normal
        speed = tangent.norm(1.0e-12)
        drag = qd.min(
            speed * (1.0 - qd.exp(-self.dt / slip_time)),
            shear_stress * self.dt / (self.rho * tangent_depth),
        )
        return dv_normal - tangent / speed * drag * weight

    @qd.kernel
    def apply(
        self,
        f: qd.i32,
        center: gs.qd_vec3,
        velocity: gs.qd_vec3,
        pitch: qd.f32,
        yaw: qd.f32,
        omega: qd.f32,
    ):
        for node in qd.grouped(self.mass):
            self.mass[node] = 0.0
            self.height_mass[node] = 0.0
            self.momentum[node] = qd.Vector.zero(gs.qd_float, 3)
            self.reaction[node] = qd.Vector.zero(gs.qd_float, 3)
        for j in range(2):
            self.contacts[j] = 0

        # Conservative bilinear scatter of the deforming bread surface.
        for a in self.surface_ids:
            i = self.surface_ids[a]
            pos = self.particles[f, i, 0].pos
            mass = self.info[i].mass
            base, frac = self._cell(pos)
            for u, v in qd.static(qd.ndrange(2, 2)):
                node = base + qd.Vector([u, v])
                if self._valid(node):
                    wm = self._weight(frac, u, v) * mass
                    self.mass[node] += wm
                    self.height_mass[node] += wm * pos[2]
                    self.momentum[node] += wm * self.particles[f, i, 0].vel

        for i in range(self.butter_start, self.butter_end):
            pos = self.particles[f, i, 0].pos
            vel = self.particles[f, i, 0].vel
            base, frac = self._cell(pos)
            height = 0.0
            surface_velocity = qd.Vector.zero(gs.qd_float, 3)
            weight_sum = 0.0
            for u, v in qd.static(qd.ndrange(2, 2)):
                node = base + qd.Vector([u, v])
                if self._valid(node) and self.mass[node] > 1.0e-12:
                    weight = self._weight(frac, u, v)
                    height += weight * self.height_mass[node] / self.mass[node]
                    surface_velocity += weight * self.momentum[node] / self.mass[node]
                    weight_sum += weight
            if weight_sum > 0.5 and self.bread_stress > 0.0:
                height /= weight_sum
                surface_velocity /= weight_sum
                gap = pos[2] - height - 0.5 * (self.spacing + self.bread_spacing)
                if -self.spacing < gap < self.bread_contact_range:
                    dv = self._impulse_velocity(
                        vel - surface_velocity,
                        qd.Vector([0.0, 0.0, 1.0]),
                        gap,
                        self.bread_stress,
                        self.bread_contact_range,
                        self.bread_slip_time,
                        self.bread_shear_stress,
                    )
                    vel += dv
                    self.contacts[0] += 1
                    impulse = self.info[i].mass * dv
                    for u, v in qd.static(qd.ndrange(2, 2)):
                        node = base + qd.Vector([u, v])
                        if self._valid(node) and self.mass[node] > 1.0e-12:
                            self.reaction[node] -= self._weight(frac, u, v) / weight_sum * impulse

            # Exact closest point on the oriented rectangular blade; only butter
            # receives this wet-contact law, not the bread or wooden board.
            c, s = qd.cos(pitch), qd.sin(pitch)
            cy, sy = qd.cos(yaw), qd.sin(yaw)
            offset = pos - center
            yaw_x = cy * offset[0] + sy * offset[1]
            yaw_y = -sy * offset[0] + cy * offset[1]
            local = qd.Vector([c * yaw_x - s * offset[2], yaw_y, s * yaw_x + c * offset[2]])
            closest = qd.min(qd.max(local, -self.half_blade), self.half_blade)
            delta = local - closest
            distance = delta.norm(1.0e-12)
            blade_gap = distance - 0.5 * self.spacing
            if distance > 1.0e-6 and blade_gap < self.blade_contact_range and self.blade_stress > 0.0:
                n = delta / distance
                pitch_nx = c * n[0] + s * n[2]
                normal = qd.Vector([
                    cy * pitch_nx - sy * n[1],
                    sy * pitch_nx + cy * n[1],
                    -s * n[0] + c * n[2],
                ])
                blade_velocity = velocity + qd.Vector([
                    cy * omega * offset[2],
                    sy * omega * offset[2],
                    omega * (-sy * offset[1] - cy * offset[0]),
                ])
                vel += self._impulse_velocity(
                    vel - blade_velocity,
                    normal,
                    blade_gap,
                    self.blade_stress,
                    self.blade_contact_range,
                    self.blade_slip_time,
                    self.blade_shear_stress,
                )
                self.contacts[1] += 1
            # The MPM grid contact can admit particle centers into a thin,
            # moving rigid box. Enforce a one-sided normal velocity at the
            # blade surface, including for centers already inside the box.
            # This is a contact response, not a particle position edit.
            if self.blade_normal_relaxation > 0.0:
                signed_distance = distance
                contact_normal_local = delta / qd.max(distance, 1.0e-12)
                if distance <= 1.0e-6:
                    face_distance = self.half_blade - qd.abs(local)
                    signed_distance = -qd.min(qd.min(face_distance[0], face_distance[1]), face_distance[2])
                    if face_distance[2] <= face_distance[0] and face_distance[2] <= face_distance[1]:
                        contact_normal_local = qd.Vector([0.0, 0.0, qd.select(local[2] >= 0.0, 1.0, -1.0)])
                    elif face_distance[0] <= face_distance[1]:
                        contact_normal_local = qd.Vector([qd.select(local[0] >= 0.0, 1.0, -1.0), 0.0, 0.0])
                    else:
                        contact_normal_local = qd.Vector([0.0, qd.select(local[1] >= 0.0, 1.0, -1.0), 0.0])
                center_gap = signed_distance - self.blade_contact_margin
                if center_gap < 0.0:
                    nx = c * contact_normal_local[0] + s * contact_normal_local[2]
                    contact_normal = qd.Vector([
                        cy * nx - sy * contact_normal_local[1],
                        sy * nx + cy * contact_normal_local[1],
                        -s * contact_normal_local[0] + c * contact_normal_local[2],
                    ])
                    target_speed = qd.min(
                        -center_gap * self.blade_normal_relaxation / self.dt,
                        self.blade_max_separation_speed,
                    )
                    normal_speed = (vel - velocity).dot(contact_normal)
                    if normal_speed < target_speed:
                        vel += (target_speed - normal_speed) * contact_normal
            self.particles[f, i, 0].vel = vel

        # The opposite bread impulse uses the same weights and masses as the
        # scatter, preserving the pair's total linear momentum.
        for a in self.surface_ids:
            i = self.surface_ids[a]
            base, frac = self._cell(self.particles[f, i, 0].pos)
            dv = qd.Vector.zero(gs.qd_float, 3)
            for u, v in qd.static(qd.ndrange(2, 2)):
                node = base + qd.Vector([u, v])
                if self._valid(node) and self.mass[node] > 1.0e-12:
                    dv += self._weight(frac, u, v) * self.reaction[node] / self.mass[node]
            self.particles[f, i, 0].vel += dv

    def surface_gaps(self, butter_positions):
        """Diagnostic distances from butter centers to the current bread surface."""
        mass = self.mass.to_numpy()
        height_mass = self.height_mass.to_numpy()
        uv = (butter_positions[:, :2] - np.array([-0.25, -0.28])) / self.grid_spacing
        base = np.floor(uv).astype(int)
        frac = uv - base
        height = np.zeros(len(base))
        weights = np.zeros(len(base))
        for u in range(2):
            for v in range(2):
                node = base + np.array([u, v])
                inside = ((node >= 0) & (node < np.array(self.res))).all(axis=1)
                node = np.clip(node, 0, np.array(self.res) - 1)
                valid = inside & (mass[node[:, 0], node[:, 1]] > 1e-12)
                w = (frac[:, 0] if u else 1 - frac[:, 0]) * (frac[:, 1] if v else 1 - frac[:, 1])
                w = np.where(valid, w, 0.0)
                h = height_mass[node[:, 0], node[:, 1]] / np.maximum(mass[node[:, 0], node[:, 1]], 1e-12)
                height += w * h
                weights += w
        valid = weights > 0.5
        gaps = butter_positions[:, 2] - height / np.maximum(weights, 1e-12)
        return gaps, valid
