from __future__ import annotations

import csv
import json
import math
import os
import platform
import struct
import sys
import time
import zlib
from dataclasses import asdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(parents=True, exist_ok=True)

os.environ["RAINFALL_FORCE_CPU"] = "1"
from rainfall_ca.engine import MountainFloodCA, SimulationConfig  # noqa: E402


def write_png(path: Path, rgb: np.ndarray) -> None:
    """Write an uint8 RGB image using only the Python standard library."""
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError("RGB image required")
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def heatmap_rgb(field: np.ndarray, scale_max: float | None = None, zoom: int = 5) -> np.ndarray:
    upper = float(scale_max if scale_max is not None else np.max(field))
    norm = np.clip(field / max(upper, 1e-12), 0.0, 1.0)
    # Dark blue -> cyan -> yellow, deliberately simple and dependency-free.
    r = np.clip(2.2 * norm - 0.7, 0, 1)
    g = np.clip(2.0 * norm, 0, 1)
    b = np.clip(1.3 - 1.1 * norm, 0, 1)
    rgb = (255 * np.stack([r, g, b], axis=-1)).astype(np.uint8)
    return np.repeat(np.repeat(rgb, zoom, axis=0), zoom, axis=1)


def run_to(sim: MountainFloodCA, target_s: float, max_dt_s: float) -> None:
    while sim.time_s < target_s - 1e-10:
        sim.config.max_dt_s = min(max_dt_s, target_s - sim.time_s)
        sim.step(1)


def base_config(**overrides: object) -> SimulationConfig:
    values: dict[str, object] = {
        "grid_size": 48,
        "cell_size_m": 5.0,
        "seed": 117,
        "relief_m": 60.0,
        "north_south_drop_m": 30.0,
        "rainfall_mm_h": 120.0,
        "rain_duration_min": 30.0,
        "infiltration_mm_h": 0.0,
        "manning_n": 0.04,
        "max_dt_s": 0.5,
        "cfl": 0.35,
        "open_outlet": False,
    }
    values.update(overrides)
    return SimulationConfig(**values)


rows: list[dict[str, object]] = []
details: dict[str, object] = {}


def record(test: str, metric: str, value: float, criterion: str, passed: bool | None) -> None:
    rows.append(
        {
            "test": test,
            "metric": metric,
            "value": value,
            "criterion": criterion,
            "status": "PASS" if passed else ("FAIL" if passed is False else "SKIP"),
        }
    )


started = time.time()

# 1. Closed-domain balance on the normal synthetic catchment.
sim = MountainFloodCA(base_config(rainfall_mm_h=150.0, infiltration_mm_h=5.0))
sim.step(300)
mass_stats = sim.stats()
mass_error = float(mass_stats["relative_mass_error"])
record("closed_domain_mass", "relative_mass_error", mass_error, "< 2e-5", mass_error < 2e-5)
details["closed_domain_mass"] = mass_stats
write_png(OUT / "closed_domain_depth.png", heatmap_rgb(np.asarray(sim.h), zoom=6))

# 2. Exact accumulation under uniform rain and constant infiltration on a flat bed.
rain_mm_h = 60.0
infil_mm_h = 12.0
target_s = 120.0
uniform = MountainFloodCA(
    base_config(rainfall_mm_h=rain_mm_h, infiltration_mm_h=infil_mm_h, max_dt_s=0.5)
)
uniform.dem.fill(0.0)
uniform._rain_mask.fill(1.0)
run_to(uniform, target_s, 0.5)
expected_depth = (rain_mm_h - infil_mm_h) / 3_600_000.0 * target_s
uniform_field = np.asarray(uniform.h)
uniform_max_abs = float(np.max(np.abs(uniform_field - expected_depth)))
record(
    "uniform_rain_infiltration",
    "max_abs_depth_error_m",
    uniform_max_abs,
    "< 2e-7 m",
    uniform_max_abs < 2e-7,
)
details["uniform_rain_infiltration"] = {
    "rainfall_mm_h": rain_mm_h,
    "infiltration_mm_h": infil_mm_h,
    "duration_s": target_s,
    "analytic_depth_m": expected_depth,
    "model_mean_depth_m": float(np.mean(uniform_field)),
    "max_abs_depth_error_m": uniform_max_abs,
    "stats": uniform.stats(),
}

# 3. Well-balanced lake at rest on the generated irregular bed.
lake = MountainFloodCA(base_config(rainfall_mm_h=0.0, max_dt_s=0.2))
level = float(np.max(lake.dem)) + 0.25
lake.h[:] = level - lake.dem
initial_lake = np.asarray(lake.h).copy()
lake.step(25)
lake_depth_error = float(np.max(np.abs(np.asarray(lake.h) - initial_lake)))
lake_flux = float(max(np.max(np.abs(lake.qx)), np.max(np.abs(lake.qy))))
record("lake_at_rest", "max_abs_depth_change_m", lake_depth_error, "< 3e-6 m", lake_depth_error < 3e-6)
record("lake_at_rest", "max_abs_unit_discharge_m2_s", lake_flux, "< 3e-6", lake_flux < 3e-6)
details["lake_at_rest"] = {
    "steps": lake.steps,
    "duration_s": lake.time_s,
    "max_abs_depth_change_m": lake_depth_error,
    "max_abs_unit_discharge_m2_s": lake_flux,
}

# 4. Known diagonal slope: the first-step flux should point downslope.
slope_sim = MountainFloodCA(base_config(rainfall_mm_h=0.0, max_dt_s=0.05, manning_n=0.03))
n = slope_sim.config.grid_size
y, x = np.mgrid[0:n, 0:n]
expected_angle_deg = 30.0
angle = math.radians(expected_angle_deg)
slope = 0.01
slope_sim.dem[:] = 50.0 - slope_sim.config.cell_size_m * slope * (
    math.cos(angle) * x + math.sin(angle) * y
)
slope_sim.h.fill(0.10)
slope_sim.step(1)
measured_angle_deg = math.degrees(
    math.atan2(float(np.mean(slope_sim.qy)), float(np.mean(slope_sim.qx)))
)
angle_error_deg = abs(measured_angle_deg - expected_angle_deg)
record("diagonal_slope", "direction_error_deg", angle_error_deg, "< 0.5 deg", angle_error_deg < 0.5)
details["diagonal_slope"] = {
    "bed_slope": slope,
    "expected_angle_deg": expected_angle_deg,
    "measured_angle_deg": measured_angle_deg,
    "direction_error_deg": angle_error_deg,
}

# 5. A finite water patch must move down a north-south slope without losing mass.
patch = MountainFloodCA(base_config(rainfall_mm_h=0.0, max_dt_s=0.5))
patch.dem[:] = np.linspace(20.0, 0.0, n, dtype=np.float32)[:, None]
patch.h[3:8, 15:33] = 0.12
y_index = np.arange(n, dtype=np.float64)[:, None]
initial_storage_cells = float(np.sum(patch.h))
initial_centroid = float(np.sum(patch.h * y_index) / np.sum(patch.h))
patch.step(100)
final_centroid = float(np.sum(patch.h * y_index) / np.sum(patch.h))
patch_mass_rel = abs(float(np.sum(patch.h)) - initial_storage_cells) / initial_storage_cells
centroid_shift = final_centroid - initial_centroid
record("downslope_patch", "centroid_shift_cells", centroid_shift, "> 0.2", centroid_shift > 0.2)
record("downslope_patch", "relative_storage_error", patch_mass_rel, "< 2e-5", patch_mass_rel < 2e-5)
details["downslope_patch"] = {
    "initial_centroid_row": initial_centroid,
    "final_centroid_row": final_centroid,
    "centroid_shift_cells": centroid_shift,
    "relative_storage_error": patch_mass_rel,
}

# 6. Outlet bookkeeping.
outlet = MountainFloodCA(base_config(rainfall_mm_h=0.0, open_outlet=True, max_dt_s=0.5))
outlet.dem.fill(0.0)
outlet.h[-1, :] = 0.10
initial_volume = float(np.sum(outlet.h)) * outlet.config.cell_size_m**2
outlet.step(1)
final_volume = float(np.sum(outlet.h)) * outlet.config.cell_size_m**2
outlet_closure = abs(initial_volume - final_volume - outlet.cumulative_outflow_m3)
record("open_outlet", "absolute_closure_error_m3", outlet_closure, "< 1e-3 m3", outlet_closure < 1e-3)
details["open_outlet"] = {
    "initial_volume_m3": initial_volume,
    "final_volume_m3": final_volume,
    "reported_outflow_m3": outlet.cumulative_outflow_m3,
    "closure_error_m3": outlet_closure,
}

# 7. Time-step sensitivity.  This is a convergence diagnostic, not an exact solution.
timestep_fields: dict[float, np.ndarray] = {}
timestep_stats: dict[str, object] = {}
for maximum_dt in (1.0, 0.5, 0.25):
    dt_sim = MountainFloodCA(
        base_config(
            grid_size=64,
            cell_size_m=10.0,
            seed=86,
            rainfall_mm_h=120.0,
            rain_duration_min=5.0,
            infiltration_mm_h=4.0,
            max_dt_s=maximum_dt,
        )
    )
    run_to(dt_sim, 600.0, maximum_dt)
    timestep_fields[maximum_dt] = np.asarray(dt_sim.h).copy()
    timestep_stats[str(maximum_dt)] = dt_sim.stats()

reference = timestep_fields[0.25]
dt_errors: dict[str, object] = {}
for maximum_dt in (1.0, 0.5):
    diff = timestep_fields[maximum_dt] - reference
    rmse = float(np.sqrt(np.mean(diff * diff)))
    maximum = float(np.max(np.abs(diff)))
    dt_errors[str(maximum_dt)] = {"rmse_m": rmse, "max_abs_m": maximum}
    record("timestep_sensitivity", f"rmse_{maximum_dt:g}s_vs_0.25s_m", rmse, "reported; no universal threshold", None)

coarse_rmse = float(dt_errors["1.0"]["rmse_m"])
medium_rmse = float(dt_errors["0.5"]["rmse_m"])
refinement_improves = medium_rmse <= coarse_rmse + 1e-12
record(
    "timestep_sensitivity",
    "error_decreases_with_refinement",
    float(refinement_improves),
    "0.5s RMSE <= 1.0s RMSE",
    refinement_improves,
)
details["timestep_sensitivity"] = {
    "reference_max_dt_s": 0.25,
    "target_time_s": 600.0,
    "runs": timestep_stats,
    "errors": dt_errors,
}
write_png(OUT / "timestep_reference_depth.png", heatmap_rgb(reference, zoom=6))

# 8. CPU/GPU comparison, only meaningful when the auto-selected backend is CUDA.
compare_cfg = base_config(grid_size=64, rainfall_mm_h=135.0, infiltration_mm_h=6.0)
os.environ["RAINFALL_FORCE_CPU"] = "1"
cpu = MountainFloodCA(compare_cfg)
os.environ.pop("RAINFALL_FORCE_CPU", None)
gpu = MountainFloodCA(SimulationConfig(**asdict(compare_cfg)))
cpu.step(60)
gpu.step(60)
if gpu.backend == "cuda":
    gpu_h = gpu._to_numpy(gpu.h)
    max_cpu_gpu = float(np.max(np.abs(np.asarray(cpu.h) - gpu_h)))
    record("cpu_gpu_consistency", "max_abs_depth_difference_m", max_cpu_gpu, "< 2e-6 m", max_cpu_gpu < 2e-6)
    cpu_gpu_status = "completed"
else:
    max_cpu_gpu = math.nan
    record("cpu_gpu_consistency", "max_abs_depth_difference_m", max_cpu_gpu, "requires CUDA backend", None)
    cpu_gpu_status = "skipped_no_cuda_backend"
details["cpu_gpu_consistency"] = {
    "status": cpu_gpu_status,
    "cpu_backend": cpu.backend,
    "candidate_backend": gpu.backend,
    "candidate_device": gpu.device_name,
    "max_abs_depth_difference_m": max_cpu_gpu,
}

with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["test", "metric", "value", "criterion", "status"])
    writer.writeheader()
    writer.writerows(rows)

payload = {
    "experiment": "01_numerical_verification",
    "scope": "synthetic numerical verification; no observational validation",
    "generated_unix_s": time.time(),
    "runtime_s": time.time() - started,
    "environment": {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
    },
    "summary": {
        "pass": sum(row["status"] == "PASS" for row in rows),
        "fail": sum(row["status"] == "FAIL" for row in rows),
        "skip": sum(row["status"] == "SKIP" for row in rows),
    },
    "checks": rows,
    "details": details,
}
(OUT / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=True), encoding="utf-8")
(OUT / "run.log").write_text(
    "Numerical verification completed.\n"
    + json.dumps(payload["summary"], ensure_ascii=False)
    + "\nScope: synthetic numerical verification only; no observations used.\n",
    encoding="utf-8",
)
print(json.dumps(payload["summary"], ensure_ascii=False))

