from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from pathlib import Path

os.environ["RAINFALL_FORCE_CPU"] = "1"

import fiona
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.transform import from_origin

from rainfall_ca.engine import (
    FixedStageBoundary,
    MountainFloodCA,
    SimulationConfig,
    SpecifiedFluxBoundary,
)
from rainfall_ca.geospatial import prepare_urban_domain, save_urban_domain


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"


def build_inputs() -> tuple[Path, Path, float]:
    DATA.mkdir(parents=True, exist_ok=True)
    dem_path = DATA / "synthetic_city_dem.tif"
    shape_path = DATA / "synthetic_buildings.shp"
    rows, cols, dx = 60, 80, 2.0
    transform = from_origin(400_000.0, 1_000.0, dx, dx)
    y, x = np.mgrid[:rows, :cols]
    terrain = (12.0 - 0.0025 * dx * x - 0.0005 * dx * y).astype(np.float32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=cols,
        height=rows,
        count=1,
        dtype="float32",
        crs="EPSG:32650",
        transform=transform,
    ) as dst:
        dst.write(terrain, 1)

    schema = {"geometry": "Polygon", "properties": {"height_m": "float"}}
    blocks = []
    for c0, c1 in ((15, 35), (45, 65)):
        for r0, r1 in ((2, 8), (14, 27), (34, 47), (54, 58)):
            west = 400_000.0 + c0 * dx
            east = 400_000.0 + c1 * dx
            north = 1_000.0 - r0 * dx
            south = 1_000.0 - r1 * dx
            blocks.append(
                {
                    "type": "Polygon",
                    "coordinates": [[
                        (west, south), (east, south), (east, north),
                        (west, north), (west, south),
                    ]],
                }
            )
    with fiona.open(
        shape_path,
        "w",
        driver="ESRI Shapefile",
        crs="EPSG:32650",
        schema=schema,
    ) as vector:
        for index, geometry in enumerate(blocks):
            vector.write(
                {"geometry": geometry, "properties": {"height_m": 8.0 + index}}
            )
    expected_area_m2 = sum(
        (c1 - c0) * dx * (r1 - r0) * dx
        for c0, c1 in ((15, 35), (45, 65))
        for r0, r1 in ((2, 8), (14, 27), (34, 47), (54, 58))
    )
    return dem_path, shape_path, expected_area_m2


def boundaries(cols: int):
    bands = ((9, 13), (28, 33), (48, 53))
    inflows = []
    stages = []
    for index, (start, stop) in enumerate(bands, 1):
        rr = np.arange(start, stop)
        inflows.append(
            SpecifiedFluxBoundary(
                f"inlet_{index}", np.column_stack((rr, np.zeros_like(rr))), 0.10
            )
        )
        stages.append(
            FixedStageBoundary(
                f"outlet_{index}",
                np.column_stack((rr, np.full_like(rr, cols - 1))),
                0.005,
                "depth",
            )
        )
    return inflows, stages


def run_case(domain, with_buildings: bool):
    config = SimulationConfig(
        grid_size=60,
        cell_size_m=domain.cell_size_m,
        rainfall_mm_h=0.0,
        infiltration_mm_h=0.0,
        manning_n=0.035,
        max_dt_s=0.10,
        cfl=0.35,
        open_outlet=False,
    )
    sim = MountainFloodCA(config)
    mask = domain.building_mask if with_buildings else np.zeros_like(domain.building_mask)
    sim.configure_domain(
        domain.terrain_dem_m,
        surface_dem_m=domain.surface_dem_m if with_buildings else domain.terrain_dem_m,
        cell_size_m=domain.cell_size_m,
        active_mask=domain.active_mask,
        building_mask=mask,
        grid_metadata=asdict(domain.grid),
    )
    inflows, stages = boundaries(domain.grid.width)
    sim.configure_boundaries(inflows=inflows, stages=stages)
    snapshots = []
    while sim.time_s < 1_200.0:
        sim.step(40)
        stats = sim.stats()
        snapshots.append(
            {
                "time_s": stats["simulation_time_s"],
                "storage_m3": stats["storage_m3"],
                "max_depth_m": stats["max_depth_m"],
                "max_speed_m_s": stats["max_speed_m_s"],
                "relative_mass_error": stats["relative_mass_error"],
            }
        )
    _, _, speed = sim.velocity_fields()
    return sim, snapshots, sim._to_numpy(speed)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    dem_path, shape_path, expected_area = build_inputs()
    domain = prepare_urban_domain(
        dem_path, shape_path, height_field="height_m", default_height_m=10.0
    )
    save_urban_domain(domain, DATA / "prepared_city_domain.npz")
    built, built_series, built_speed = run_case(domain, True)
    open_case, open_series, open_speed = run_case(domain, False)
    built_h = built._to_numpy(built.h)
    open_h = open_case._to_numpy(open_case.h)

    building_face_flux = max(
        float(np.max(np.abs(built._to_numpy(built.qx)[:, :-1]) * domain.building_mask[:, 1:-1])),
        float(np.max(np.abs(built._to_numpy(built.qy)[:-1, :]) * domain.building_mask[1:-1, :])),
    )
    area_error = domain.audit["building_plan_area_m2"] - expected_area
    metrics = {
        "status": "COMPLETED_SYNTHETIC_CORE_REGRESSION",
        "formal_real_event_validation": False,
        "crs": domain.grid.crs,
        "shape": [domain.grid.height, domain.grid.width],
        "cell_size_m": domain.cell_size_m,
        "feature_count": domain.audit["feature_count"],
        "building_cells": domain.audit["building_cells"],
        "expected_building_area_m2": expected_area,
        "rasterized_building_area_m2": domain.audit["building_plan_area_m2"],
        "building_area_error_m2": area_error,
        "max_building_depth_m": float(np.max(built_h[domain.building_mask])),
        "max_building_adjacent_face_flux_m2_s": building_face_flux,
        "with_buildings": built.stats(),
        "without_buildings": open_case.stats(),
        "max_depth_change_m": float(np.max(built_h) - np.max(open_h)),
        "max_speed_change_m_s": float(np.max(built_speed) - np.max(open_speed)),
        "paired_depth_mae_m": float(np.mean(np.abs(built_h - open_h))),
        "paired_depth_max_abs_difference_m": float(np.max(np.abs(built_h - open_h))),
        "paired_speed_mae_m_s": float(np.mean(np.abs(built_speed - open_speed))),
        "gates": {
            "crs_aligned": domain.grid.crs == "EPSG:32650",
            "building_area_exact": abs(area_error) < 1e-9,
            "building_storage_zero": float(np.max(built_h[domain.building_mask])) == 0.0,
            "building_face_flux_zero": building_face_flux == 0.0,
            "mass_balance": built.stats()["relative_mass_error"] < 5e-5,
        },
    }
    metrics["all_gates_pass"] = all(metrics["gates"].values())
    (RESULTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (RESULTS / "domain_audit.json").write_text(
        json.dumps(
            {"grid": asdict(domain.grid), "audit": domain.audit},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    with (RESULTS / "timeseries.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case", *built_series[0].keys()])
        writer.writeheader()
        writer.writerows({"case": "buildings", **row} for row in built_series)
        writer.writerows({"case": "no_buildings", **row} for row in open_series)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    panels = (
        (domain.surface_dem_m, "Surface DEM with roofs (m)", "terrain"),
        (domain.building_mask, "Solid building mask", "gray_r"),
        (built_h, "Final water depth with buildings (m)", "Blues"),
        (built_speed, "Final depth-averaged speed (m/s)", "magma"),
    )
    for axis, (field, title, cmap) in zip(axes.flat, panels):
        image = axis.imshow(field, cmap=cmap)
        axis.set_title(title)
        axis.set_xlabel("column")
        axis.set_ylabel("row")
        fig.colorbar(image, ax=axis, shrink=0.78)
    fig.savefig(RESULTS / "urban_gis_core.png", dpi=180)
    plt.close(fig)
    (LOGS / "run.log").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"all_gates_pass": metrics["all_gates_pass"], "results": str(RESULTS)}))


if __name__ == "__main__":
    main()
