from __future__ import annotations

import csv
import json
import math
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(parents=True, exist_ok=True)
os.environ["RAINFALL_FORCE_CPU"] = "1"

from rainfall_ca.engine import MountainFloodCA, SimulationConfig  # noqa: E402


def write_png(path: Path, rgb: np.ndarray) -> None:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[j].tobytes() for j in range(h))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def draw_profiles(x: np.ndarray, series: list[tuple[np.ndarray, tuple[int, int, int]]]) -> np.ndarray:
    width, height, margin = 1000, 520, 55
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    image[margin : height - margin, margin] = 20
    image[height - margin, margin : width - margin] = 20
    xmin, xmax = float(x.min()), float(x.max())
    ymax = max(float(np.nanmax(values)) for values, _ in series) * 1.05
    for values, colour in series:
        px = margin + (x - xmin) / (xmax - xmin) * (width - 2 * margin - 1)
        py = height - margin - np.clip(values / max(ymax, 1e-12), 0, 1) * (height - 2 * margin - 1)
        for i in range(len(x) - 1):
            x0, x1 = int(px[i]), int(px[i + 1])
            y0, y1 = int(py[i]), int(py[i + 1])
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            xs = np.linspace(x0, x1, steps + 1).astype(int)
            ys = np.linspace(y0, y1, steps + 1).astype(int)
            valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
            image[ys[valid], xs[valid]] = colour
    return image


grid_size = 192
dx = 1.0
initial_depth_m = 1.0
target_time_s = 2.5
cfg = SimulationConfig(
    grid_size=grid_size,
    cell_size_m=dx,
    rainfall_mm_h=0.0,
    infiltration_mm_h=0.0,
    manning_n=0.01,
    max_dt_s=0.04,
    cfl=0.25,
    open_outlet=False,
)
sim = MountainFloodCA(cfg)
sim.config.manning_n = 0.0  # frictionless analytic problem; bypass UI validation clamp
sim.dem.fill(0.0)
dam_col = grid_size // 2
sim.h[:, :dam_col] = initial_depth_m
sim.h[:, dam_col:] = 0.0
initial_volume = float(np.sum(sim.h)) * dx * dx

started = time.time()
while sim.time_s < target_time_s - 1e-10:
    sim.config.max_dt_s = min(0.04, target_time_s - sim.time_s)
    sim.step(1)

model_h = np.mean(np.asarray(sim.h), axis=0)
model_u = np.mean(np.asarray(sim.velocity_fields()[0]), axis=0)
x = (np.arange(grid_size, dtype=float) + 0.5 - dam_col) * dx
g = sim.gravity
c0 = math.sqrt(g * initial_depth_m)
left_edge = -c0 * target_time_s
right_edge = 2.0 * c0 * target_time_s
exact_h = np.zeros_like(x)
exact_u = np.zeros_like(x)
left = x < left_edge
fan = (x >= left_edge) & (x <= right_edge)
exact_h[left] = initial_depth_m
exact_h[fan] = (2.0 * c0 - x[fan] / target_time_s) ** 2 / (9.0 * g)
exact_u[fan] = (2.0 / 3.0) * (c0 + x[fan] / target_time_s)

window = (x >= left_edge - 2 * dx) & (x <= right_edge + 2 * dx)
depth_rmse = float(np.sqrt(np.mean((model_h[window] - exact_h[window]) ** 2)))
depth_mae = float(np.mean(np.abs(model_h[window] - exact_h[window])))
velocity_wet = window & (exact_h > 1e-3) & (model_h > 1e-3)
velocity_rmse = float(np.sqrt(np.mean((model_u[velocity_wet] - exact_u[velocity_wet]) ** 2)))
model_wet_indices = np.where(model_h > 1e-3)[0]
model_front_x = float(x[model_wet_indices[-1]]) if len(model_wet_indices) else math.nan
front_error_m = abs(model_front_x - right_edge)
final_volume = float(np.sum(sim.h)) * dx * dx
relative_volume_error = abs(final_volume - initial_volume) / initial_volume

metrics = {
    "experiment": "02_swashes_ritter_dam_break",
    "classification": "analytic full-SWE comparison; equation-scope diagnostic, not observations",
    "source": {
        "citation": "Delestre et al. (2013), SWASHES",
        "doi": "https://doi.org/10.1002/fld.3741",
        "preprint": "https://arxiv.org/abs/1110.0288",
    },
    "configuration": {
        "grid_size": grid_size,
        "cell_size_m": dx,
        "initial_left_depth_m": initial_depth_m,
        "initial_right_depth_m": 0.0,
        "target_time_s": target_time_s,
        "friction": 0.0,
        "boundary": "closed; comparison before waves reach domain boundaries",
        "max_dt_s": 0.04,
        "cfl": 0.25,
    },
    "metrics": {
        "depth_rmse_active_window_m": depth_rmse,
        "depth_mae_active_window_m": depth_mae,
        "velocity_rmse_common_wet_m_s": velocity_rmse,
        "analytic_front_x_m": right_edge,
        "model_front_x_m_at_h_gt_1mm": model_front_x,
        "front_position_error_m": front_error_m,
        "initial_volume_m3": initial_volume,
        "final_volume_m3": final_volume,
        "relative_volume_error": relative_volume_error,
    },
    "interpretation": {
        "volume_conservation_status": "PASS" if relative_volume_error < 2e-5 else "FAIL",
        "full_swe_profile_status": "DIAGNOSTIC_ONLY",
        "reason": "RainFall omits advective acceleration, while Ritter is a full shallow-water solution.",
    },
    "runtime_s": time.time() - started,
}
(OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
with (OUT / "profiles.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["x_m", "model_depth_m", "analytic_depth_m", "model_u_m_s", "analytic_u_m_s"])
    writer.writerows(zip(x, model_h, exact_h, model_u, exact_u))
write_png(
    OUT / "depth_profile.png",
    draw_profiles(x, [(exact_h, (25, 95, 190)), (model_h, (220, 95, 30))]),
)
write_png(
    OUT / "velocity_profile.png",
    draw_profiles(x, [(exact_u, (25, 95, 190)), (np.maximum(model_u, 0), (220, 95, 30))]),
)
(OUT / "run.log").write_text(
    "Ritter benchmark completed.\n"
    f"depth_rmse_m={depth_rmse:.9g}\n"
    f"velocity_rmse_m_s={velocity_rmse:.9g}\n"
    f"front_error_m={front_error_m:.9g}\n"
    f"relative_volume_error={relative_volume_error:.9g}\n"
    "Interpretation: equation-scope diagnostic, not observational validation.\n",
    encoding="utf-8",
)
print(json.dumps(metrics["metrics"], indent=2))

