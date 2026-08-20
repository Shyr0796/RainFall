from __future__ import annotations

import csv
import json
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
EXP = Path(__file__).resolve().parents[1]
DATASET = (
    EXP
    / "data"
    / "extracted"
    / "Test1_dataset_2010"
    / "Test1 dataset 2010"
)
PROCESSED = EXP / "data" / "processed"
RESULTS = EXP / "results"
PROCESSED.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

os.environ["RAINFALL_FORCE_CPU"] = "1"
from rainfall_ca.engine import MountainFloodCA, SimulationConfig  # noqa: E402


def read_ascii_grid(path: Path) -> tuple[np.ndarray, dict[str, float]]:
    header: dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for _ in range(6):
            key, value = handle.readline().split()
            header[key.lower()] = float(value)
    data = np.loadtxt(path, skiprows=6)
    expected = (int(header["nrows"]), int(header["ncols"]))
    if data.shape != expected:
        raise ValueError(f"Expected {expected}, found {data.shape}")
    return data, header


def write_png(path: Path, rgb: np.ndarray) -> None:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width, _ = rgb.shape
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


def draw_timeseries(
    hours: np.ndarray,
    lines: list[tuple[np.ndarray, tuple[int, int, int]]],
    ymin: float = 9.65,
    ymax: float = 10.40,
) -> np.ndarray:
    width, height, margin = 1000, 520, 55
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    image[margin : height - margin, margin] = 25
    image[height - margin, margin : width - margin] = 25
    for values, colour in lines:
        px = margin + hours / 20.0 * (width - 2 * margin - 1)
        py = height - margin - np.clip((values - ymin) / (ymax - ymin), 0, 1) * (height - 2 * margin - 1)
        finite = np.isfinite(values)
        for index in range(len(hours) - 1):
            if not (finite[index] and finite[index + 1]):
                continue
            x0, x1 = int(px[index]), int(px[index + 1])
            y0, y1 = int(py[index]), int(py[index + 1])
            count = max(abs(x1 - x0), abs(y1 - y0), 1)
            xs = np.linspace(x0, x1, count + 1).astype(int)
            ys = np.linspace(y0, y1, count + 1).astype(int)
            image[ys, xs] = colour
    return image


source_dem, header = read_ascii_grid(DATASET / "test1DEM.asc")
source_dx = header["cellsize"]
nrows, ncols = source_dem.shape
x_centres = header["xllcorner"] + (np.arange(ncols) + 0.5) * source_dx
# ESRI ASCII rows are north-to-south.
y_centres = header["yllcorner"] + (nrows - np.arange(nrows) - 0.5) * source_dx
x_keep = np.where((x_centres >= 0.0) & (x_centres < 700.0))[0]
y_keep = np.where((y_centres >= 0.0) & (y_centres < 100.0))[0]
cropped_2m = source_dem[np.ix_(y_keep, x_keep)]
if cropped_2m.shape != (50, 350):
    raise ValueError(f"Unexpected official-domain crop: {cropped_2m.shape}")

# The specification requests a 10 m model grid.  Block means are deterministic;
# retain both the source crop and resampled grid for auditability.
dem_10m = cropped_2m.reshape(10, 5, 70, 5).mean(axis=(1, 3)).astype(np.float32)
np.save(PROCESSED / "test1_dem_2m_official_domain.npy", cropped_2m.astype(np.float32))
np.save(PROCESSED / "test1_dem_10m_block_mean.npy", dem_10m)

bc_rows: list[tuple[float, float]] = []
with (DATASET / "Test1BC.csv").open("r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
        bc_rows.append((float(row["Time (mins)"]) * 60.0, float(row["Water level (m)"])))
bc_time_s = np.array([row[0] for row in bc_rows])
bc_level_m = np.array([row[1] for row in bc_rows])

grid_size = 72
row_start = (grid_size - dem_10m.shape[0]) // 2
row_stop = row_start + dem_10m.shape[0]
col_start = 1
col_stop = col_start + dem_10m.shape[1]
cfg = SimulationConfig(
    grid_size=grid_size,
    cell_size_m=10.0,
    rainfall_mm_h=0.0,
    infiltration_mm_h=0.0,
    manning_n=0.03,
    max_dt_s=10.0,
    cfl=0.35,
    open_outlet=False,
)
sim = MountainFloodCA(cfg)
sim.dem.fill(100.0)  # impermeable high wall around the exact 700 x 100 m rectangle
sim.dem[row_start:row_stop, col_start:col_stop] = dem_10m
domain = np.s_[row_start:row_stop, col_start:col_stop]
initial_level_m = 9.7
sim.h[domain] = np.maximum(initial_level_m - sim.dem[domain], 0.0)
cell_area = cfg.cell_size_m**2
initial_volume_m3 = float(np.sum(sim.h)) * cell_area
boundary_exchange_m3 = 0.0


def stage_at(time_s: float) -> float:
    return float(np.interp(time_s, bc_time_s, bc_level_m))


def impose_left_stage(stage_m: float) -> float:
    global boundary_exchange_m3
    boundary = np.s_[row_start:row_stop, col_start]
    before = float(np.sum(sim.h[boundary])) * cell_area
    sim.h[boundary] = np.maximum(stage_m - sim.dem[boundary], 0.0)
    after = float(np.sum(sim.h[boundary])) * cell_area
    exchange = after - before
    boundary_exchange_m3 += exchange
    return exchange


output_points: list[tuple[int, float, float]] = []
with (DATASET / "Test1output.csv").open("r", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
        output_points.append((int(row["Point ID"]), float(row["X"]), float(row["Y"])))


def point_surface(x_m: float, y_m: float) -> float:
    col = col_start + min(69, max(0, int(x_m // 10.0)))
    # DEM array is north-to-south, so y=50 lies at the middle; either middle row
    # is equivalent because the official Test 1 terrain is transverse-uniform.
    row_from_south = min(9, max(0, int(y_m // 10.0)))
    row = row_stop - 1 - row_from_south
    return float(sim.dem[row, col] + sim.h[row, col]) if sim.h[row, col] > sim.dry_depth_m else float("nan")


end_s = 20.0 * 3600.0
next_output_s = 0.0
records: list[dict[str, float]] = []
started = time.time()
while sim.time_s < end_s - 1e-9:
    impose_left_stage(stage_at(sim.time_s))
    target = min(end_s, next_output_s if next_output_s > sim.time_s + 1e-9 else end_s)
    maximum = min(10.0, end_s - sim.time_s)
    if next_output_s > sim.time_s + 1e-9:
        maximum = min(maximum, next_output_s - sim.time_s)
    sim.config.max_dt_s = maximum
    sim.step(1)
    impose_left_stage(stage_at(sim.time_s))
    if sim.time_s >= next_output_s - 1e-7:
        row: dict[str, float] = {
            "time_s": sim.time_s,
            "time_h": sim.time_s / 3600.0,
            "boundary_level_m": stage_at(sim.time_s),
        }
        for point_id, x_m, y_m in output_points:
            row[f"point_{point_id}_water_level_m"] = point_surface(x_m, y_m)
        records.append(row)
        next_output_s += 60.0

final_volume_m3 = float(np.sum(sim.h)) * cell_area
balance_error_m3 = final_volume_m3 - initial_volume_m3 - boundary_exchange_m3
balance_relative = abs(balance_error_m3) / max(abs(boundary_exchange_m3), initial_volume_m3, 1e-9)
point_metrics: dict[str, dict[str, float]] = {}
for point_id, _, _ in output_points:
    values = np.array([row[f"point_{point_id}_water_level_m"] for row in records])
    finite = values[np.isfinite(values)]
    point_metrics[str(point_id)] = {
        "peak_water_level_m": float(np.max(finite)),
        "peak_error_vs_expected_10_35_m": float(np.max(finite) - 10.35),
        "final_water_level_m": float(values[-1]),
        "final_error_vs_expected_10_25_m": float(values[-1] - 10.25),
    }

with (RESULTS / "test1_timeseries.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
    writer.writeheader()
    writer.writerows(records)

hours = np.array([row["time_h"] for row in records])
boundary_values = np.array([row["boundary_level_m"] for row in records])
plot_lines = [(boundary_values, (30, 30, 30))]
for point_id, _, _ in output_points:
    plot_lines.append(
        (np.array([row[f"point_{point_id}_water_level_m"] for row in records]), (25, 105 + point_id * 45, 210 - point_id * 40))
    )
write_png(RESULTS / "test1_water_levels.png", draw_timeseries(hours, plot_lines))

metrics = {
    "experiment": "UK_EA_SC120002_Test1",
    "classification": "standard numerical benchmark, not observations",
    "run_status": "COMPLETED_WITH_EXPERIMENT_STAGE_BOUNDARY",
    "source_files": {
        "dem": "test1DEM.asc",
        "boundary": "Test1BC.csv",
        "points": "Test1output.csv",
    },
    "configuration": {
        "official_domain_m": [700.0, 100.0],
        "source_dem_resolution_m": 2.0,
        "model_resolution_m": 10.0,
        "resampling": "5x5 block mean",
        "manning_n": 0.03,
        "duration_h": 20.0,
        "all_nonstage_boundaries": "closed high walls",
        "stage_boundary": "left edge; experiment-only Dirichlet water-level wrapper",
    },
    "water_balance": {
        "initial_volume_m3": initial_volume_m3,
        "net_boundary_exchange_m3": boundary_exchange_m3,
        "final_volume_m3": final_volume_m3,
        "closure_error_m3": balance_error_m3,
        "relative_closure_error": balance_relative,
    },
    "official_expected_outcomes": {
        "peak_point_water_level_m": 10.35,
        "final_retained_pond_level_m": 10.25,
        "source": "SC120002 technical report, Test 1",
    },
    "point_metrics": point_metrics,
    "runtime_s": time.time() - started,
    "limitations": [
        "No field observations are involved.",
        "The prescribed-stage boundary is implemented in this experiment, not in the core RainFall API.",
        "The official 2 m DEM is block-averaged to the specified 10 m model grid; sub-grid sill elevations may shift.",
        "Comparison is against official expected peak/final levels, not a full authoritative reference time series.",
    ],
}
(RESULTS / "test1_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
(RESULTS / "status.json").write_text(
    json.dumps(
        {
            "data_download": "COMPLETE_AND_ZIP_TESTED",
            "archive_sha256": "388c2789570e5975fe909033e34bedbe5d7bde5e6d7f9b7d7c1eaf04e58bc732",
            "data_audit": "COMPLETE_8_NESTED_ARCHIVES_8_DEM_GRIDS",
            "test1_run": metrics["run_status"],
            "evidence_class": metrics["classification"],
            "core_api_stage_boundary": "NOT_IMPLEMENTED_EXPERIMENT_WRAPPER_ONLY",
            "result_metrics": "results/test1_metrics.json",
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
(RESULTS / "test1_run.log").write_text(
    f"status={metrics['run_status']}\n"
    f"runtime_s={metrics['runtime_s']:.3f}\n"
    f"steps={sim.steps}\n"
    f"relative_closure_error={balance_relative:.9g}\n"
    + "\n".join(
        f"point_{point_id}: peak={values['peak_water_level_m']:.6f}, final={values['final_water_level_m']:.6f}"
        for point_id, values in point_metrics.items()
    )
    + "\nEvidence class: standard numerical benchmark, not observations.\n",
    encoding="utf-8",
)
print(json.dumps({"status": metrics["run_status"], "steps": sim.steps, "points": point_metrics}, indent=2))
