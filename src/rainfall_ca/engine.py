from __future__ import annotations

import base64
import heapq
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

try:
    import cupy as cp
except (ImportError, OSError):  # pragma: no cover - CPU-only installations
    cp = None


@dataclass(slots=True)
class SimulationConfig:
    grid_size: int = 192
    cell_size_m: float = 10.0
    seed: int = 42
    relief_m: float = 180.0
    north_south_drop_m: float = 110.0
    rainfall_mm_h: float = 95.0
    rain_duration_min: float = 60.0
    rain_center_x: float = 0.50
    rain_center_y: float = 0.22
    rain_width: float = 0.48
    rain_height: float = 0.30
    infiltration_mm_h: float = 8.0
    manning_n: float = 0.055
    max_dt_s: float = 1.5
    cfl: float = 0.35
    open_outlet: bool = True

    def validated(self) -> SimulationConfig:
        self.grid_size = int(min(384, max(48, self.grid_size)))
        self.cell_size_m = float(min(100.0, max(0.01, self.cell_size_m)))
        self.seed = int(min(2_147_483_647, max(0, self.seed)))
        self.relief_m = float(min(800.0, max(20.0, self.relief_m)))
        self.north_south_drop_m = float(
            min(self.relief_m * 1.5, max(0.0, self.north_south_drop_m))
        )
        self.rainfall_mm_h = float(min(500.0, max(0.0, self.rainfall_mm_h)))
        self.rain_duration_min = float(min(360.0, max(1.0, self.rain_duration_min)))
        self.rain_center_x = float(min(1.0, max(0.0, self.rain_center_x)))
        self.rain_center_y = float(min(1.0, max(0.0, self.rain_center_y)))
        self.rain_width = float(min(1.0, max(0.05, self.rain_width)))
        self.rain_height = float(min(1.0, max(0.05, self.rain_height)))
        self.infiltration_mm_h = float(min(200.0, max(0.0, self.infiltration_mm_h)))
        self.manning_n = float(min(0.2, max(0.01, self.manning_n)))
        self.max_dt_s = float(min(10.0, max(0.02, self.max_dt_s)))
        self.cfl = float(min(0.8, max(0.05, self.cfl)))
        return self


@dataclass(slots=True)
class SpecifiedFluxBoundary:
    """A nonnegative discharge distributed over selected fluid cells."""

    name: str
    cells: np.ndarray
    discharge_m3_s: float


@dataclass(slots=True)
class FixedStageBoundary:
    """A fixed water-surface elevation (or depth) on selected fluid cells."""

    name: str
    cells: np.ndarray
    stage_m: float
    value_type: str = "wse"


@dataclass(slots=True)
class DrainageSink:
    """A capacity-limited one-way sink representing unresolved urban drainage."""

    name: str
    cells: np.ndarray
    capacity_m3_s: float


def _select_array_module() -> tuple[Any, str, str]:
    force_cpu = os.getenv("RAINFALL_FORCE_CPU", "0") == "1"
    if not force_cpu and cp is not None:
        try:
            if cp.cuda.runtime.getDeviceCount() > 0:
                # Probe NVRTC as well as the driver; a mismatched CUDA runtime may
                # enumerate a GPU successfully but fail on the first array kernel.
                cp.arange(1, dtype=cp.float32).sum().get()
                name = cp.cuda.runtime.getDeviceProperties(0)["name"]
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                return cp, "cuda", str(name)
        except (OSError, RuntimeError):
            return np, "cpu", "NumPy CPU fallback"
    return np, "cpu", "NumPy CPU fallback"


def generate_mountain_dem(config: SimulationConfig) -> np.ndarray:
    """Create a deterministic multi-scale mountain basin with a carved trunk valley."""

    n = config.grid_size
    rng = np.random.default_rng(config.seed)
    yy, xx = np.mgrid[0 : 1 : complex(n), 0 : 1 : complex(n)]

    terrain = np.zeros((n, n), dtype=np.float64)
    scales = ((n / 3.5, 0.58), (n / 10.0, 0.25), (n / 28.0, 0.12), (1.2, 0.05))
    for sigma, weight in scales:
        noise = gaussian_filter(
            rng.normal(size=(n, n)), sigma=max(0.8, sigma), mode="reflect"
        )
        noise -= noise.mean()
        std = max(float(noise.std()), 1e-9)
        terrain += weight * noise / std

    # Long ridges and asymmetric uplift make the surface look geological rather than random.
    ridge_a = np.exp(-(((xx - (0.08 + 0.20 * yy)) / 0.14) ** 2))
    ridge_b = np.exp(-(((xx - (0.94 - 0.23 * yy)) / 0.16) ** 2))
    foothills = 0.25 * np.sin(3.0 * np.pi * xx + 1.4 * np.sin(2 * np.pi * yy))
    terrain += 0.72 * ridge_a + 0.63 * ridge_b + foothills

    # A meandering main valley widens toward the southern outlet.
    channel_x = (
        0.50 + 0.10 * np.sin(2.4 * np.pi * yy + 0.4) + 0.035 * np.sin(8 * np.pi * yy)
    )
    channel_width = 0.018 + 0.055 * yy
    trunk = np.exp(-(((xx - channel_x) / channel_width) ** 2))
    terrain -= (0.62 + 0.38 * yy) * trunk

    # Two tributaries merge into the main valley near the middle of the domain.
    left_line = 0.08 + 0.78 * yy
    left_gate = np.exp(-(((yy - 0.34) / 0.25) ** 2))
    right_line = 0.92 - 0.72 * yy
    right_gate = np.exp(-(((yy - 0.40) / 0.27) ** 2))
    terrain -= 0.34 * left_gate * np.exp(-(((xx - left_line) / 0.035) ** 2))
    terrain -= 0.31 * right_gate * np.exp(-(((xx - right_line) / 0.038) ** 2))

    terrain -= terrain.min()
    terrain /= max(float(terrain.max()), 1e-9)
    terrain *= config.relief_m
    terrain += (1.0 - yy) * config.north_south_drop_m

    # Lower a broad notch at the downstream edge, which becomes the optional open outlet.
    outlet = np.exp(-(((xx - channel_x[-1:, :]) / 0.09) ** 2)) * np.exp(
        -(((yy - 1.0) / 0.06) ** 2)
    )
    terrain -= outlet * (0.10 * config.relief_m)
    terrain -= terrain.min()
    outlet_col = int(np.argmin(terrain[-1, :]))
    terrain = _priority_flood_to_outlet(
        terrain, outlet_col, minimum_rise_m=max(1e-3, config.cell_size_m * 0.002)
    )
    terrain -= terrain.min()
    return terrain.astype(np.float32)


def _priority_flood_to_outlet(
    dem: np.ndarray, outlet_col: int, minimum_rise_m: float = 1e-3
) -> np.ndarray:
    """Fill internal sinks while preserving a four-neighbour path to the south outlet."""

    rows, cols = dem.shape
    conditioned = np.asarray(dem, dtype=np.float64).copy()
    visited = np.zeros((rows, cols), dtype=bool)
    heap: list[tuple[float, int, int]] = []
    half_width = max(2, cols // 24)
    for col in range(
        max(0, outlet_col - half_width), min(cols, outlet_col + half_width + 1)
    ):
        visited[rows - 1, col] = True
        heapq.heappush(heap, (float(conditioned[rows - 1, col]), rows - 1, col))

    neighbours = ((-1, 0), (1, 0), (0, -1), (0, 1))
    while heap:
        elevation, row, col = heapq.heappop(heap)
        for dr, dc in neighbours:
            nr, nc = row + dr, col + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols or visited[nr, nc]:
                continue
            visited[nr, nc] = True
            conditioned[nr, nc] = max(conditioned[nr, nc], elevation + minimum_rise_m)
            heapq.heappush(heap, (float(conditioned[nr, nc]), nr, nc))
    return conditioned


class MountainFloodCA:
    """Mass-conservative local-inertial cellular flood solver on CPU or CUDA."""

    gravity = 9.81
    dry_depth_m = 1e-5

    def __init__(self, config: SimulationConfig | None = None):
        self.config = (config or SimulationConfig()).validated()
        self.xp, self.backend, self.device_name = _select_array_module()
        self.reset(self.config)

    def reset(self, config: SimulationConfig | None = None) -> None:
        if config is not None:
            self.config = config.validated()
        xp = self.xp
        dem_cpu = generate_mountain_dem(self.config)
        n = self.config.grid_size
        self._initialize_domain(
            dem_cpu,
            active_mask=np.ones((n, n), dtype=bool),
            building_mask=np.zeros((n, n), dtype=bool),
            grid_metadata=None,
        )
        self.outlet_center_x = float(np.argmin(dem_cpu[-1, :])) / max(n - 1, 1)
        outlet_cols = xp.linspace(0.0, 1.0, n)
        self._outlet_weight = xp.exp(
            -(((outlet_cols - self.outlet_center_x) / 0.10) ** 4)
        )
        self._reset_state()
        self._rain_mask = self._make_rain_mask()

    def _initialize_domain(
        self,
        dem_m: np.ndarray,
        *,
        display_dem_m: np.ndarray | None = None,
        active_mask: np.ndarray,
        building_mask: np.ndarray,
        grid_metadata: dict[str, Any] | None,
    ) -> None:
        dem_cpu = np.asarray(dem_m, dtype=np.float32)
        if dem_cpu.ndim != 2 or min(dem_cpu.shape) < 2:
            raise ValueError("DEM must be a two-dimensional grid of at least 2 x 2 cells")
        active = np.asarray(active_mask, dtype=bool)
        buildings = np.asarray(building_mask, dtype=bool)
        if active.shape != dem_cpu.shape or buildings.shape != dem_cpu.shape:
            raise ValueError("DEM, active mask and building mask must have identical shapes")
        active &= np.isfinite(dem_cpu)
        buildings &= active
        if not np.any(active & ~buildings):
            raise ValueError("Domain contains no fluid cells")
        fill_elevation = float(np.nanmax(dem_cpu[active]))
        solver_dem = np.where(active, dem_cpu, fill_elevation).astype(np.float32)
        display_cpu = (
            solver_dem
            if display_dem_m is None
            else np.asarray(display_dem_m, dtype=np.float32)
        )
        if display_cpu.shape != dem_cpu.shape:
            raise ValueError("Display DEM must have the same shape as terrain DEM")
        display_cpu = np.where(active, display_cpu, fill_elevation).astype(np.float32)
        xp = self.xp
        self.dem = xp.asarray(solver_dem, dtype=xp.float32)
        self.display_dem = xp.asarray(display_cpu, dtype=xp.float32)
        self.active_mask = xp.asarray(active)
        self.building_mask = xp.asarray(buildings)
        self.fluid_mask = self.active_mask & ~self.building_mask
        self._face_x_open = self.fluid_mask[:, :-1] & self.fluid_mask[:, 1:]
        self._face_y_open = self.fluid_mask[:-1, :] & self.fluid_mask[1:, :]
        self.shape = dem_cpu.shape
        self.grid_metadata = grid_metadata

    def _reset_state(self) -> None:
        xp = self.xp
        rows, cols = self.shape
        self.h = xp.zeros((rows, cols), dtype=xp.float32)
        self.qx = xp.zeros((rows, cols - 1), dtype=xp.float32)
        self.qy = xp.zeros((rows - 1, cols), dtype=xp.float32)
        self.time_s = 0.0
        self.steps = 0
        self.initial_storage_m3 = 0.0
        self.cumulative_rain_m3 = 0.0
        self.cumulative_infiltration_m3 = 0.0
        self.cumulative_outflow_m3 = 0.0
        self.cumulative_boundary_inflow_m3 = 0.0
        self.cumulative_boundary_outflow_m3 = 0.0
        self.cumulative_drainage_m3 = 0.0
        self.boundary_inflow_by_name: dict[str, float] = {}
        self.boundary_outflow_by_name: dict[str, float] = {}
        self.inflow_boundaries: list[SpecifiedFluxBoundary] = []
        self.stage_boundaries: list[FixedStageBoundary] = []
        self.drainage_sinks: list[DrainageSink] = []
        self.drainage_by_name: dict[str, float] = {}
        self.spatial_rainfall_mm_h = None
        self.spatial_infiltration_mm_h = None
        self.spatial_manning_n = None
        self.last_dt_s = self.config.max_dt_s
        self.last_compute_ms = 0.0
        self.last_steps_per_second = 0.0

    def configure_domain(
        self,
        dem_m: np.ndarray,
        *,
        cell_size_m: float,
        surface_dem_m: np.ndarray | None = None,
        active_mask: np.ndarray | None = None,
        building_mask: np.ndarray | None = None,
        grid_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Replace the synthetic terrain with a georeferenced rectangular domain."""

        dem = np.asarray(dem_m, dtype=np.float32)
        active = np.isfinite(dem) if active_mask is None else np.asarray(active_mask)
        buildings = (
            np.zeros(dem.shape, dtype=bool)
            if building_mask is None
            else np.asarray(building_mask)
        )
        self.config.cell_size_m = float(cell_size_m)
        self.config.validated()
        if not np.isclose(self.config.cell_size_m, cell_size_m):
            raise ValueError("cell_size_m must be between 0.01 and 100 metres")
        self.config.open_outlet = False
        self._initialize_domain(
            dem,
            display_dem_m=surface_dem_m,
            active_mask=active,
            building_mask=buildings,
            grid_metadata=grid_metadata,
        )
        rows, cols = self.shape
        self.outlet_center_x = 0.5
        self._outlet_weight = self.xp.zeros(cols, dtype=self.xp.float32)
        self._reset_state()
        self._rain_mask = self._make_rain_mask()

    def configure_boundaries(
        self,
        *,
        inflows: list[SpecifiedFluxBoundary] | None = None,
        stages: list[FixedStageBoundary] | None = None,
        drainage: list[DrainageSink] | None = None,
    ) -> None:
        """Attach auditable source and fixed-stage boundaries to fluid cells."""

        seen_names: set[str] = set()
        checked_inflows: list[SpecifiedFluxBoundary] = []
        checked_stages: list[FixedStageBoundary] = []
        for boundary in inflows or []:
            cells = self._validated_boundary_cells(boundary.name, boundary.cells)
            if boundary.discharge_m3_s < 0:
                raise ValueError("Specified inflow discharge must be nonnegative")
            if boundary.name in seen_names:
                raise ValueError(f"Duplicate boundary name: {boundary.name}")
            seen_names.add(boundary.name)
            checked_inflows.append(
                SpecifiedFluxBoundary(boundary.name, cells, float(boundary.discharge_m3_s))
            )
        occupied_stage_cells: set[tuple[int, int]] = set()
        for boundary in stages or []:
            cells = self._validated_boundary_cells(boundary.name, boundary.cells)
            if boundary.value_type not in {"wse", "depth"}:
                raise ValueError("Fixed-stage value_type must be 'wse' or 'depth'")
            if boundary.name in seen_names:
                raise ValueError(f"Duplicate boundary name: {boundary.name}")
            cell_set = {tuple(cell) for cell in cells.tolist()}
            if occupied_stage_cells & cell_set:
                raise ValueError("Fixed-stage boundaries may not overlap")
            occupied_stage_cells |= cell_set
            seen_names.add(boundary.name)
            checked_stages.append(
                FixedStageBoundary(
                    boundary.name, cells, float(boundary.stage_m), boundary.value_type
                )
            )
        checked_drainage: list[DrainageSink] = []
        for sink in drainage or []:
            cells = self._validated_boundary_cells(sink.name, sink.cells)
            if sink.capacity_m3_s < 0:
                raise ValueError("Drainage capacity must be nonnegative")
            if sink.name in seen_names:
                raise ValueError(f"Duplicate boundary name: {sink.name}")
            seen_names.add(sink.name)
            checked_drainage.append(
                DrainageSink(sink.name, cells, float(sink.capacity_m3_s))
            )
        self.inflow_boundaries = checked_inflows
        self.stage_boundaries = checked_stages
        self.drainage_sinks = checked_drainage
        self.boundary_inflow_by_name = {item.name: 0.0 for item in checked_inflows}
        self.boundary_inflow_by_name.update({item.name: 0.0 for item in checked_stages})
        self.boundary_outflow_by_name = {item.name: 0.0 for item in checked_stages}
        self.drainage_by_name = {item.name: 0.0 for item in checked_drainage}

    def set_spatial_fields(
        self,
        *,
        rainfall_mm_h: np.ndarray | None = None,
        infiltration_mm_h: np.ndarray | None = None,
        manning_n: np.ndarray | None = None,
    ) -> None:
        """Set optional per-cell forcing/parameter rasters on the aligned grid.

        Passing ``None`` clears that spatial field and returns to the scalar control.
        A caller may update rainfall between simulation chunks to replay radar frames.
        """

        self.spatial_rainfall_mm_h = self._validated_spatial_field(
            "rainfall_mm_h", rainfall_mm_h, 0.0, 2_000.0
        )
        self.spatial_infiltration_mm_h = self._validated_spatial_field(
            "infiltration_mm_h", infiltration_mm_h, 0.0, 500.0
        )
        self.spatial_manning_n = self._validated_spatial_field(
            "manning_n", manning_n, 0.005, 0.30
        )

    def _validated_spatial_field(
        self,
        name: str,
        field: np.ndarray | None,
        minimum: float,
        maximum: float,
    ):
        if field is None:
            return None
        array = np.asarray(field, dtype=np.float32)
        if array.shape != self.shape or not np.isfinite(array).all():
            raise ValueError(f"{name} must be a finite raster with shape {self.shape}")
        if np.any(array < minimum) or np.any(array > maximum):
            raise ValueError(f"{name} values must be within [{minimum}, {maximum}]")
        return self.xp.asarray(array)

    def _validated_boundary_cells(self, name: str, cells: np.ndarray) -> np.ndarray:
        result = np.asarray(cells, dtype=np.int64)
        if result.ndim != 2 or result.shape[1] != 2 or len(result) == 0:
            raise ValueError(f"Boundary {name!r} cells must be a nonempty N x 2 array")
        rows, cols = self.shape
        if (
            np.any(result[:, 0] < 0)
            or np.any(result[:, 0] >= rows)
            or np.any(result[:, 1] < 0)
            or np.any(result[:, 1] >= cols)
        ):
            raise ValueError(f"Boundary {name!r} contains cells outside the domain")
        fluid = self._to_numpy(self.fluid_mask)
        if not np.all(fluid[result[:, 0], result[:, 1]]):
            raise ValueError(f"Boundary {name!r} intersects inactive or building cells")
        return np.unique(result, axis=0)

    def synchronize_storage_reference(self) -> None:
        """Declare the current water field as the initial condition for mass balance."""

        self.initial_storage_m3 = (
            self._scalar(self.xp.sum(self.h)) * self.config.cell_size_m**2
        )

    def _make_rain_mask(self):
        xp = self.xp
        rows, cols = self.shape
        y, x = xp.mgrid[0:rows, 0:cols]
        x = x / max(cols - 1, 1)
        y = y / max(rows - 1, 1)
        rx = (x - self.config.rain_center_x) / (self.config.rain_width * 0.5)
        ry = (y - self.config.rain_center_y) / (self.config.rain_height * 0.5)
        # A rounded rectangular storm cell with a narrow feathered edge.
        distance = (xp.abs(rx) ** 6 + xp.abs(ry) ** 6) ** (1.0 / 6.0)
        mask = xp.clip((1.05 - distance) / 0.10, 0.0, 1.0).astype(xp.float32)
        return mask * self.fluid_mask.astype(xp.float32)

    def update_controls(self, **values: Any) -> None:
        allowed = {
            "rainfall_mm_h",
            "rain_duration_min",
            "rain_center_x",
            "rain_center_y",
            "rain_width",
            "rain_height",
            "infiltration_mm_h",
            "manning_n",
            "max_dt_s",
            "cfl",
            "open_outlet",
        }
        for key, value in values.items():
            if key in allowed and value is not None:
                setattr(self.config, key, value)
        self.config.validated()
        self._rain_mask = self._make_rain_mask()

    def _scalar(self, value: Any) -> float:
        if self.backend == "cuda":
            return float(value.get())
        return float(value)

    def _adaptive_dt(self) -> float:
        xp = self.xp
        max_h = self._scalar(xp.max(self.h))
        if max_h <= self.dry_depth_m:
            return self.config.max_dt_s
        u, v, _ = self.velocity_fields()
        max_wave = self._scalar(
            xp.max(xp.sqrt(u * u + v * v) + xp.sqrt(self.gravity * self.h))
        )
        stable = self.config.cfl * self.config.cell_size_m / max(max_wave, 1e-6)
        return min(self.config.max_dt_s, max(0.02, stable))

    def step(self, iterations: int = 4) -> dict[str, float]:
        iterations = min(64, max(1, int(iterations)))
        started = time.perf_counter()
        for _ in range(iterations):
            self._single_step()
        if self.backend == "cuda":
            cp.cuda.Stream.null.synchronize()
        wall = time.perf_counter() - started
        self.last_compute_ms = wall * 1000.0
        self.last_steps_per_second = iterations / max(wall, 1e-9)
        return {
            "compute_ms": self.last_compute_ms,
            "steps_per_second": self.last_steps_per_second,
        }

    def _single_step(self) -> None:
        xp = self.xp
        cfg = self.config
        dx = cfg.cell_size_m
        dt = self._adaptive_dt()
        cell_area = dx * dx

        for boundary in self.inflow_boundaries:
            rows = boundary.cells[:, 0]
            cols = boundary.cells[:, 1]
            volume = boundary.discharge_m3_s * dt
            depth = volume / (len(boundary.cells) * cell_area)
            self.h[rows, cols] += depth
            self.cumulative_boundary_inflow_m3 += volume
            self.boundary_inflow_by_name[boundary.name] += volume

        remaining_rain_s = cfg.rain_duration_min * 60.0 - self.time_s
        active_fraction = min(1.0, max(0.0, remaining_rain_s / dt))
        if self.spatial_rainfall_mm_h is None:
            rainfall_rate = self._rain_mask * (cfg.rainfall_mm_h / 3_600_000.0)
        else:
            rainfall_rate = (
                self.spatial_rainfall_mm_h
                * self.fluid_mask
                / 3_600_000.0
            )
        rain_depth = rainfall_rate * dt * active_fraction
        wet_available = self.h + rain_depth
        if self.spatial_infiltration_mm_h is None:
            infiltration_rate = cfg.infiltration_mm_h / 3_600_000.0
        else:
            infiltration_rate = self.spatial_infiltration_mm_h / 3_600_000.0
        infiltration = xp.minimum(wet_available, infiltration_rate * dt)
        infiltration *= self.fluid_mask
        self.h = wet_available - infiltration

        self.cumulative_rain_m3 += self._scalar(xp.sum(rain_depth)) * cell_area
        self.cumulative_infiltration_m3 += (
            self._scalar(xp.sum(infiltration)) * cell_area
        )

        surface = self.dem + self.h
        if self.spatial_manning_n is None:
            n2_x = cfg.manning_n * cfg.manning_n
            n2_y = n2_x
        else:
            n_x = 0.5 * (self.spatial_manning_n[:, :-1] + self.spatial_manning_n[:, 1:])
            n_y = 0.5 * (self.spatial_manning_n[:-1, :] + self.spatial_manning_n[1:, :])
            n2_x = n_x * n_x
            n2_y = n_y * n_y
        eps = 1e-8

        # East-west face discharge qx [m2/s], positive to the east.
        flow_depth_x = xp.maximum(surface[:, :-1], surface[:, 1:]) - xp.maximum(
            self.dem[:, :-1], self.dem[:, 1:]
        )
        slope_x = (surface[:, 1:] - surface[:, :-1]) / dx
        denominator_x = 1.0 + (
            self.gravity
            * dt
            * n2_x
            * xp.abs(self.qx)
            / (flow_depth_x ** (7.0 / 3.0) + eps)
        )
        qx_new = (self.qx - self.gravity * flow_depth_x * dt * slope_x) / denominator_x
        qx_new = xp.where(flow_depth_x > self.dry_depth_m, qx_new, 0.0)
        qx_new = xp.where(self._face_x_open, qx_new, 0.0)

        # North-south face discharge qy [m2/s], positive to the south.
        flow_depth_y = xp.maximum(surface[:-1, :], surface[1:, :]) - xp.maximum(
            self.dem[:-1, :], self.dem[1:, :]
        )
        slope_y = (surface[1:, :] - surface[:-1, :]) / dx
        denominator_y = 1.0 + (
            self.gravity
            * dt
            * n2_y
            * xp.abs(self.qy)
            / (flow_depth_y ** (7.0 / 3.0) + eps)
        )
        qy_new = (self.qy - self.gravity * flow_depth_y * dt * slope_y) / denominator_y
        qy_new = xp.where(flow_depth_y > self.dry_depth_m, qy_new, 0.0)
        qy_new = xp.where(self._face_y_open, qy_new, 0.0)

        # Per-cell outflow limiter: no cell may export more water than it stores.
        outgoing = xp.zeros_like(self.h)
        outgoing[:, :-1] += xp.maximum(qx_new, 0.0)
        outgoing[:, 1:] += xp.maximum(-qx_new, 0.0)
        outgoing[:-1, :] += xp.maximum(qy_new, 0.0)
        outgoing[1:, :] += xp.maximum(-qy_new, 0.0)
        limiter = xp.minimum(1.0, self.h * dx / (dt * outgoing + eps))
        qx_new *= xp.where(qx_new >= 0.0, limiter[:, :-1], limiter[:, 1:])
        qy_new *= xp.where(qy_new >= 0.0, limiter[:-1, :], limiter[1:, :])

        next_h = self.h.copy()
        transfer_x = (dt / dx) * qx_new
        transfer_y = (dt / dx) * qy_new
        next_h[:, :-1] -= transfer_x
        next_h[:, 1:] += transfer_x
        next_h[:-1, :] -= transfer_y
        next_h[1:, :] += transfer_y

        if cfg.open_outlet:
            outlet_q = (
                self._outlet_weight
                * self.h[-1, :]
                * xp.sqrt(self.gravity * self.h[-1, :])
            )
            outlet_q *= self.fluid_mask[-1, :]
            outlet_q = xp.minimum(outlet_q, next_h[-1, :] * dx / dt)
            next_h[-1, :] -= outlet_q * dt / dx
            self.cumulative_outflow_m3 += self._scalar(xp.sum(outlet_q)) * dt * dx

        for sink in self.drainage_sinks:
            rows = sink.cells[:, 0]
            cols = sink.cells[:, 1]
            available_depth = xp.maximum(next_h[rows, cols], 0.0)
            available_volume = self._scalar(xp.sum(available_depth)) * cell_area
            removed_volume = min(sink.capacity_m3_s * dt, available_volume)
            if removed_volume > 0.0:
                weights = available_depth / max(
                    self._scalar(xp.sum(available_depth)), 1e-12
                )
                next_h[rows, cols] -= weights * (removed_volume / cell_area)
                self.cumulative_drainage_m3 += removed_volume
                self.drainage_by_name[sink.name] += removed_volume

        for boundary in self.stage_boundaries:
            rows = boundary.cells[:, 0]
            cols = boundary.cells[:, 1]
            if boundary.value_type == "depth":
                target = xp.full(len(boundary.cells), max(0.0, boundary.stage_m))
            else:
                target = xp.maximum(boundary.stage_m - self.dem[rows, cols], 0.0)
            delta_volume = self._to_numpy(target - next_h[rows, cols]) * cell_area
            volume_in = float(np.maximum(delta_volume, 0.0).sum())
            volume_out = float(np.maximum(-delta_volume, 0.0).sum())
            next_h[rows, cols] = target
            self.cumulative_boundary_inflow_m3 += volume_in
            self.cumulative_boundary_outflow_m3 += volume_out
            self.boundary_inflow_by_name[boundary.name] += volume_in
            self.boundary_outflow_by_name[boundary.name] += volume_out

        self.h = xp.where(self.fluid_mask, xp.maximum(next_h, 0.0), 0.0)
        self.qx = qx_new
        self.qy = qy_new
        self.time_s += dt
        self.steps += 1
        self.last_dt_s = dt

    def velocity_fields(self):
        xp = self.xp
        qx_cell = xp.zeros_like(self.h)
        qy_cell = xp.zeros_like(self.h)
        qx_cell[:, 1:-1] = 0.5 * (self.qx[:, :-1] + self.qx[:, 1:])
        qx_cell[:, 0] = self.qx[:, 0]
        qx_cell[:, -1] = self.qx[:, -1]
        qy_cell[1:-1, :] = 0.5 * (self.qy[:-1, :] + self.qy[1:, :])
        qy_cell[0, :] = self.qy[0, :]
        qy_cell[-1, :] = self.qy[-1, :]
        wet_h = xp.maximum(self.h, self.dry_depth_m)
        u = xp.where(self.h > self.dry_depth_m, qx_cell / wet_h, 0.0)
        v = xp.where(self.h > self.dry_depth_m, qy_cell / wet_h, 0.0)
        speed = xp.sqrt(u * u + v * v)
        return u, v, speed

    def _to_numpy(self, array) -> np.ndarray:
        if self.backend == "cuda":
            return cp.asnumpy(array)
        return np.asarray(array)

    @staticmethod
    def _b64(array: np.ndarray) -> str:
        return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")

    def frame(self, include_dem: bool = False) -> dict[str, Any]:
        h = self._to_numpy(self.h).astype(np.float32, copy=False)
        u_gpu, v_gpu, speed_gpu = self.velocity_fields()
        u = self._to_numpy(u_gpu).astype(np.float32, copy=False)
        v = self._to_numpy(v_gpu).astype(np.float32, copy=False)
        speed = self._to_numpy(speed_gpu).astype(np.float32, copy=False)

        depth_scale = max(0.05, float(np.percentile(h, 99.8)), float(h.max()))
        speed_scale = max(0.10, float(np.percentile(speed, 99.8)), float(speed.max()))
        depth_q = np.clip(np.rint(h / depth_scale * 65535.0), 0, 65535).astype("<u2")
        speed_q = np.clip(np.rint(speed / speed_scale * 65535.0), 0, 65535).astype(
            "<u2"
        )
        direction_norm = np.maximum(speed, 1e-6)
        dir_x = np.clip(np.rint(u / direction_norm * 127.0), -127, 127).astype(np.int8)
        dir_y = np.clip(np.rint(v / direction_norm * 127.0), -127, 127).astype(np.int8)

        result: dict[str, Any] = {
            "shape": list(self.shape),
            "depth_u16": self._b64(depth_q),
            "depth_scale_m": depth_scale,
            "speed_u16": self._b64(speed_q),
            "speed_scale_m_s": speed_scale,
            "dir_x_i8": self._b64(dir_x),
            "dir_y_i8": self._b64(dir_y),
            "stats": self.stats(speed=speed_gpu),
            "config": asdict(self.config),
            "grid": self.grid_metadata,
        }
        if include_dem:
            dem = self._to_numpy(self.display_dem).astype(np.float32, copy=False)
            active = self._to_numpy(self.active_mask).astype(bool)
            dem_min = float(dem[active].min())
            dem_max = float(dem[active].max())
            dem_q = np.clip(
                np.rint((dem - dem_min) / max(dem_max - dem_min, 1e-9) * 65535.0),
                0,
                65535,
            ).astype("<u2")
            result.update(
                {
                    "dem_u16": self._b64(dem_q),
                    "dem_min_m": dem_min,
                    "dem_max_m": dem_max,
                    "active_mask_u8": self._b64(active.astype(np.uint8)),
                    "building_mask_u8": self._b64(
                        self._to_numpy(self.building_mask).astype(np.uint8)
                    ),
                }
            )
        return result

    def stats(self, speed=None) -> dict[str, Any]:
        xp = self.xp
        storage = self._scalar(xp.sum(self.h)) * self.config.cell_size_m**2
        expected = (
            self.initial_storage_m3
            + self.cumulative_rain_m3
            + self.cumulative_boundary_inflow_m3
            - self.cumulative_infiltration_m3
            - self.cumulative_outflow_m3
            - self.cumulative_boundary_outflow_m3
            - self.cumulative_drainage_m3
        )
        error = storage - expected
        throughput = (
            self.initial_storage_m3
            + self.cumulative_rain_m3
            + self.cumulative_boundary_inflow_m3
        )
        relative = abs(error) / max(throughput, 1e-9)
        if speed is None:
            _, _, speed = self.velocity_fields()
        return {
            "backend": self.backend,
            "device_name": self.device_name,
            "gpu_active": self.backend == "cuda",
            "simulation_time_s": self.time_s,
            "steps": self.steps,
            "dt_s": self.last_dt_s,
            "max_depth_m": self._scalar(xp.max(self.h)),
            "wet_cells": int(self._scalar(xp.sum(self.h > 0.001))),
            "max_speed_m_s": self._scalar(xp.max(speed)),
            "storage_m3": storage,
            "rainfall_m3": self.cumulative_rain_m3,
            "rain_active": self.time_s < self.config.rain_duration_min * 60.0
            and (
                self.config.rainfall_mm_h > 0.0
                if self.spatial_rainfall_mm_h is None
                else self._scalar(xp.max(self.spatial_rainfall_mm_h)) > 0.0
            ),
            "infiltration_m3": self.cumulative_infiltration_m3,
            "outflow_m3": self.cumulative_outflow_m3,
            "boundary_inflow_m3": self.cumulative_boundary_inflow_m3,
            "boundary_outflow_m3": self.cumulative_boundary_outflow_m3,
            "drainage_m3": self.cumulative_drainage_m3,
            "boundary_inflow_by_name_m3": dict(self.boundary_inflow_by_name),
            "boundary_outflow_by_name_m3": dict(self.boundary_outflow_by_name),
            "drainage_by_name_m3": dict(self.drainage_by_name),
            "building_cells": int(self._scalar(xp.sum(self.building_mask))),
            "active_cells": int(self._scalar(xp.sum(self.active_mask))),
            "mass_error_m3": error,
            "relative_mass_error": relative,
            "compute_ms": self.last_compute_ms,
            "steps_per_second": self.last_steps_per_second,
        }
