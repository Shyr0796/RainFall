"""Minimal rectangular, masked, steady-boundary adapter for RainFall's local-inertial core.

This deliberately mirrors the flux update in ``src/rainfall_ca/engine.py`` while adding
the capabilities required by the Li et al. flume: explicit buildings, three specified
inflow discharges, and three fixed downstream stages. It is experiment-local and does
not modify the production simulator.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Boundary:
    name: str
    cells: tuple[np.ndarray, np.ndarray]
    value: float  # m3/s for inflow; m for stage


class UrbanLocalInertialAdapter:
    gravity = 9.81
    dry_depth_m = 1e-5

    def __init__(self, fluid_mask: np.ndarray, dx: float, manning_n: float,
                 inflows: list[Boundary], stages: list[Boundary], initial_depth_m: float):
        self.mask = np.asarray(fluid_mask, dtype=bool)
        self.dx = float(dx)
        self.n = float(manning_n)
        self.inflows = inflows
        self.stages = stages
        self.h = np.where(self.mask, initial_depth_m, 0.0).astype(float)
        self.qx = np.zeros((self.mask.shape[0] - 1, self.mask.shape[1]), dtype=float)
        self.qy = np.zeros((self.mask.shape[0], self.mask.shape[1] - 1), dtype=float)
        self.face_x = self.mask[:-1, :] & self.mask[1:, :]
        self.face_y = self.mask[:, :-1] & self.mask[:, 1:]
        self.time_s = 0.0
        self.inflow_volume_m3 = 0.0
        self.stage_outflow_volume_m3 = 0.0
        self.stage_inflow_volume_m3 = 0.0
        self.stage_outflow_by_name_m3 = {boundary.name: 0.0 for boundary in stages}
        self.stage_inflow_by_name_m3 = {boundary.name: 0.0 for boundary in stages}
        self.initial_storage_m3 = float(self.h.sum() * self.dx**2)
        for boundary in stages:
            self.h[boundary.cells] = boundary.value

    def velocity(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        qx_cell = np.zeros_like(self.h)
        qy_cell = np.zeros_like(self.h)
        qx_cell[1:-1, :] = 0.5 * (self.qx[:-1, :] + self.qx[1:, :])
        qx_cell[0, :] = self.qx[0, :]
        qx_cell[-1, :] = self.qx[-1, :]
        qy_cell[:, 1:-1] = 0.5 * (self.qy[:, :-1] + self.qy[:, 1:])
        qy_cell[:, 0] = self.qy[:, 0]
        qy_cell[:, -1] = self.qy[:, -1]
        wet = np.maximum(self.h, self.dry_depth_m)
        u = np.where(self.mask & (self.h > self.dry_depth_m), qx_cell / wet, 0.0)
        v = np.where(self.mask & (self.h > self.dry_depth_m), qy_cell / wet, 0.0)
        return u, v, np.hypot(u, v)

    def adaptive_dt(self, cfl: float = 0.25, max_dt_s: float = 0.02) -> float:
        u, v, _ = self.velocity()
        wave = np.hypot(u, v) + np.sqrt(self.gravity * self.h)
        return min(max_dt_s, max(2e-4, cfl * self.dx / max(float(wave.max()), 1e-6)))

    def step(self, dt: float | None = None) -> float:
        dt = self.adaptive_dt() if dt is None else float(dt)
        dx = self.dx
        area = dx * dx
        # Specified steady discharge distributed uniformly across each inlet opening.
        for boundary in self.inflows:
            count = max(1, len(boundary.cells[0]))
            self.h[boundary.cells] += boundary.value * dt / (count * area)
            self.inflow_volume_m3 += boundary.value * dt

        surface = self.h  # horizontal flume bottom
        n2 = self.n * self.n
        eps = 1e-12
        flow_x = np.maximum(surface[:-1, :], surface[1:, :])
        slope_x = (surface[1:, :] - surface[:-1, :]) / dx
        denom_x = 1 + self.gravity * dt * n2 * np.abs(self.qx) / (flow_x ** (7 / 3) + eps)
        new_qx = (self.qx - self.gravity * flow_x * dt * slope_x) / denom_x
        new_qx = np.where(self.face_x & (flow_x > self.dry_depth_m), new_qx, 0.0)

        flow_y = np.maximum(surface[:, :-1], surface[:, 1:])
        slope_y = (surface[:, 1:] - surface[:, :-1]) / dx
        denom_y = 1 + self.gravity * dt * n2 * np.abs(self.qy) / (flow_y ** (7 / 3) + eps)
        new_qy = (self.qy - self.gravity * flow_y * dt * slope_y) / denom_y
        new_qy = np.where(self.face_y & (flow_y > self.dry_depth_m), new_qy, 0.0)

        outgoing = np.zeros_like(self.h)
        outgoing[:-1, :] += np.maximum(new_qx, 0)
        outgoing[1:, :] += np.maximum(-new_qx, 0)
        outgoing[:, :-1] += np.maximum(new_qy, 0)
        outgoing[:, 1:] += np.maximum(-new_qy, 0)
        limiter = np.minimum(1, self.h * dx / (dt * outgoing + eps))
        new_qx *= np.where(new_qx >= 0, limiter[:-1, :], limiter[1:, :])
        new_qy *= np.where(new_qy >= 0, limiter[:, :-1], limiter[:, 1:])

        next_h = self.h.copy()
        tx = dt / dx * new_qx
        ty = dt / dx * new_qy
        next_h[:-1, :] -= tx
        next_h[1:, :] += tx
        next_h[:, :-1] -= ty
        next_h[:, 1:] += ty
        next_h[~self.mask] = 0

        # Dirichlet downstream-stage reservoirs; account for both signs of exchange.
        for boundary in self.stages:
            before = next_h[boundary.cells].copy()
            exchange = float(np.sum(before - boundary.value) * area)
            if exchange >= 0:
                self.stage_outflow_volume_m3 += exchange
                self.stage_outflow_by_name_m3[boundary.name] += exchange
            else:
                self.stage_inflow_volume_m3 -= exchange
                self.stage_inflow_by_name_m3[boundary.name] -= exchange
            next_h[boundary.cells] = boundary.value

        self.h = np.maximum(next_h, 0)
        self.qx = new_qx
        self.qy = new_qy
        self.time_s += dt
        return dt

    def mass_error_m3(self) -> float:
        storage_change = float(self.h.sum() * self.dx**2) - self.initial_storage_m3
        expected = self.inflow_volume_m3 + self.stage_inflow_volume_m3 - self.stage_outflow_volume_m3
        return storage_change - expected
