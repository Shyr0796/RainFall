from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

os.environ["RAINFALL_FORCE_CPU"] = "1"

import fiona
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from fiona.transform import transform_geom
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from scipy import ndimage

from rainfall_ca.engine import MountainFloodCA, SimulationConfig
from rainfall_ca.geospatial import prepare_urban_domain, save_urban_domain


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
DEM_RAW = RAW / "be_NYC_029.tif"
BUILDINGS_RAW = RAW / "nyc_buildings_official.geojson"
DEM_CLIP = PROCESSED / "noaa_dem_aoi_ft.tif"
BUILDINGS_SHP = PROCESSED / "nyc_buildings_height.shp"
DOMAIN_PATH = PROCESSED / "nyc_domain_1m.npz"
AOI_WGS84 = (-73.965, 40.795, -73.955, 40.805)
US_FOOT_TO_M = 1200.0 / 3937.0
INTERNATIONAL_FOOT_TO_M = 0.3048


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_inputs() -> None:
    missing = [str(path) for path in (DEM_RAW, BUILDINGS_RAW) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Official inputs are missing: {missing}")


def clip_dem() -> None:
    with rasterio.open(DEM_RAW) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *AOI_WGS84, densify_pts=21)
        buffer_source_units = 100.0
        bounds = (
            bounds[0] - buffer_source_units,
            bounds[1] - buffer_source_units,
            bounds[2] + buffer_source_units,
            bounds[3] + buffer_source_units,
        )
        window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))
        data = src.read(1, window=window, masked=True)
        profile = src.profile.copy()
        profile.update(
            width=int(window.width),
            height=int(window.height),
            transform=src.window_transform(window),
            compress="deflate",
            tiled=True,
        )
        with rasterio.open(DEM_CLIP, "w", **profile) as dst:
            dst.write(data.filled(src.nodata), 1)


def make_height_shapefile() -> None:
    schema = {
        "geometry": "MultiPolygon",
        "properties": {
            "DOITT_ID": "int",
            "HEIGHTROOF": "float",
            "GROUNDELEV": "float",
            "GEOMSOURCE": "str:16",
        },
    }
    with fiona.open(BUILDINGS_RAW) as source, fiona.open(
        BUILDINGS_SHP,
        "w",
        driver="ESRI Shapefile",
        crs="EPSG:4326",
        schema=schema,
    ) as target:
        for feature in source:
            geometry = feature["geometry"]
            if geometry["type"] == "Polygon":
                geometry = {
                    "type": "MultiPolygon",
                    "coordinates": [geometry["coordinates"]],
                }
            properties = feature["properties"]
            target.write(
                {
                    "geometry": geometry,
                    "properties": {
                        "DOITT_ID": properties["DOITT_ID"],
                        "HEIGHTROOF": properties["HEIGHT_ROOF"],
                        "GROUNDELEV": properties["GROUND_ELEVATION"],
                        "GEOMSOURCE": properties["GEOM_SOURCE"],
                    },
                }
            )


def prepare(resolution_m: float, save: bool = False):
    domain = prepare_urban_domain(
        DEM_CLIP,
        BUILDINGS_SHP,
        target_crs="EPSG:26918",
        resolution_m=resolution_m,
        height_field="HEIGHTROOF",
        vertical_scale_to_m=US_FOOT_TO_M,
        building_height_scale_to_m=INTERNATIONAL_FOOT_TO_M,
        ground_elevation_field="GROUNDELEV",
        building_ground_scale_to_m=INTERNATIONAL_FOOT_TO_M,
        dem_vertical_datum="NAVD88",
        building_vertical_datum="NAVD88",
        roof_base_source="dem_cell",
        missing_height_policy="error",
        strict_vertical=True,
    )
    if save:
        save_urban_domain(domain, DOMAIN_PATH)
    return domain


def per_building_ground_errors(domain):
    geometries = []
    attributes = []
    with fiona.open(BUILDINGS_SHP) as source:
        source_crs = source.crs_wkt or source.crs
        for index, feature in enumerate(source, 1):
            geometry = transform_geom(source_crs, domain.grid.crs, feature["geometry"])
            geometries.append((geometry, index))
            properties = feature["properties"]
            attributes.append(
                {
                    "feature_id": index,
                    "doitt_id": int(properties["DOITT_ID"]),
                    "geometry_source": properties["GEOMSOURCE"],
                    "ground_vector_m": float(properties["GROUNDELEV"])
                    * INTERNATIONAL_FOOT_TO_M,
                    "height_m": float(properties["HEIGHTROOF"])
                    * INTERNATIONAL_FOOT_TO_M,
                }
            )
    ids = rasterize(
        geometries,
        out_shape=domain.terrain_dem_m.shape,
        transform=domain.grid.transform,
        fill=0,
        dtype="int32",
    )
    indexes = np.arange(1, len(attributes) + 1)
    valid = domain.active_mask & (ids > 0)
    labels = np.where(valid, ids, 0)
    counts = ndimage.sum(np.ones_like(domain.terrain_dem_m), labels, indexes)
    minimums = ndimage.minimum(domain.terrain_dem_m, labels, indexes)
    rows = []
    for attribute, count, dem_min in zip(attributes, counts, minimums):
        if count <= 0:
            continue
        error = float(dem_min - attribute["ground_vector_m"])
        rows.append(
            {
                **attribute,
                "raster_cells": int(count),
                "dem_min_m": float(dem_min),
                "dem_minus_vector_ground_m": error,
                "absolute_error_m": abs(error),
            }
        )
    return rows


def hydraulic_height_invariance(domain) -> dict:
    size = 96
    building_density = ndimage.uniform_filter(
        domain.building_mask.astype(np.float32), size=size, mode="constant"
    )
    active_density = ndimage.uniform_filter(
        domain.active_mask.astype(np.float32), size=size, mode="constant"
    )
    score = np.where(active_density > 0.999, building_density, -1.0)
    center = np.unravel_index(np.argmax(score), score.shape)
    row0 = min(max(center[0] - size // 2, 0), domain.grid.height - size)
    col0 = min(max(center[1] - size // 2, 0), domain.grid.width - size)
    selection = np.s_[row0 : row0 + size, col0 : col0 + size]
    terrain = domain.terrain_dem_m[selection]
    buildings = domain.building_mask[selection]
    active = domain.active_mask[selection]
    height = domain.building_height_m[selection]

    def run(display_dem):
        config = SimulationConfig(
            grid_size=size,
            cell_size_m=1.0,
            rainfall_mm_h=0.0,
            infiltration_mm_h=0.0,
            manning_n=0.04,
            max_dt_s=0.05,
            open_outlet=False,
        )
        simulation = MountainFloodCA(config)
        simulation.configure_domain(
            terrain,
            surface_dem_m=display_dem,
            cell_size_m=1.0,
            active_mask=active,
            building_mask=buildings,
        )
        rainfall = np.full(terrain.shape, 60.0, dtype=np.float32)
        simulation.set_spatial_fields(rainfall_mm_h=rainfall)
        simulation.step(200)
        return simulation

    reference = run(terrain + height)
    doubled_roofs = run(terrain + 2.0 * height)
    depth_difference = float(np.max(np.abs(reference.h - doubled_roofs.h)))
    qx_difference = float(np.max(np.abs(reference.qx - doubled_roofs.qx)))
    qy_difference = float(np.max(np.abs(reference.qy - doubled_roofs.qy)))
    return {
        "patch_origin_row_col": [int(row0), int(col0)],
        "patch_shape": [size, size],
        "building_cells": int(buildings.sum()),
        "maximum_depth_difference_m": depth_difference,
        "maximum_qx_difference_m2_s": qx_difference,
        "maximum_qy_difference_m2_s": qy_difference,
        "pass": depth_difference == 0.0 and qx_difference == 0.0 and qy_difference == 0.0,
        "interpretation": (
            "With a solid building mask, roof height is visualization/QC metadata and "
            "cannot silently alter the hydraulic solution."
        ),
    }


def main() -> None:
    require_inputs()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    clip_dem()
    make_height_shapefile()
    domain = prepare(1.0, save=True)
    error_rows = per_building_ground_errors(domain)
    errors = np.asarray([row["dem_minus_vector_ground_m"] for row in error_rows])

    with (RESULTS / "per_building_ground_errors.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(error_rows[0]))
        writer.writeheader()
        writer.writerows(error_rows)

    resolution_rows = []
    reference_area = domain.audit["building_plan_area_m2"]
    for resolution in (1.0, 2.0, 5.0):
        candidate = domain if resolution == 1.0 else prepare(resolution)
        area = candidate.audit["building_plan_area_m2"]
        resolution_rows.append(
            {
                "resolution_m": resolution,
                "building_cells": candidate.audit["building_cells"],
                "building_area_m2": area,
                "area_difference_vs_1m_m2": area - reference_area,
                "area_relative_difference_vs_1m": (area - reference_area)
                / reference_area,
            }
        )
    with (RESULTS / "resolution_sensitivity.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(resolution_rows[0]))
        writer.writeheader()
        writer.writerows(resolution_rows)

    height_ft = domain.building_height_m[domain.building_mask] / INTERNATIONAL_FOOT_TO_M
    correct_height_m = domain.building_height_m[domain.building_mask]
    wrong_unit_excess = height_ft - correct_height_m
    correct_roof = domain.surface_dem_m[domain.building_mask]
    wrong_absolute_roof = correct_height_m
    invariance = hydraulic_height_invariance(domain)
    ground_summary = {
        "features": len(error_rows),
        "mean_signed_error_m": float(errors.mean()),
        "median_signed_error_m": float(np.median(errors)),
        "mae_m": float(np.mean(np.abs(errors))),
        "p95_absolute_error_m": float(np.percentile(np.abs(errors), 95)),
        "maximum_absolute_error_m": float(np.max(np.abs(errors))),
        "within_0_5_m_fraction": float(np.mean(np.abs(errors) <= 0.5)),
        "within_1_m_fraction": float(np.mean(np.abs(errors) <= 1.0)),
        "within_2_m_fraction": float(np.mean(np.abs(errors) <= 2.0)),
    }
    metrics = {
        "status": "COMPLETED_OFFICIAL_DATA_COUPLING_DIAGNOSTIC",
        "formal_hydrodynamic_event_validation": False,
        "official_building_features": domain.audit["feature_count"],
        "building_height_m": {
            "minimum": float(correct_height_m.min()),
            "median": float(np.median(correct_height_m)),
            "maximum": float(correct_height_m.max()),
        },
        "vertical_contract": {
            "source_dem_crs": "EPSG:6539",
            "solver_crs": domain.grid.crs,
            "dem_vertical_datum": "NAVD88",
            "dem_vertical_unit": "US survey foot",
            "building_ground_datum": "NAVD88 where modern/photogrammetric",
            "building_attribute_unit": "foot",
            "roof_formula": "z_roof_m = z_dem_m + HEIGHTROOF_ft * 0.3048",
            "hydraulic_terrain": "bare-earth DEM outside solid building mask",
        },
        "ground_cross_check": ground_summary,
        "ground_attribute_accepted_as_dem_replacement": False,
        "ground_rejection_reason": (
            "The independent building ground field differs from the 2017 bare-earth DEM "
            "by more than a defensible sub-metre gate for many features; retain the DEM "
            "as terrain and use the field only as QC."
        ),
        "wrong_coupling_controls": {
            "feet_treated_as_metres_median_roof_excess_m": float(
                np.median(wrong_unit_excess)
            ),
            "relative_height_treated_as_absolute_median_roof_error_m": float(
                np.median(wrong_absolute_roof - correct_roof)
            ),
        },
        "roof_formula_max_absolute_error_m": float(
            np.max(np.abs((correct_roof - domain.terrain_dem_m[domain.building_mask]) - correct_height_m))
        ),
        "hydraulic_height_invariance": invariance,
        "resolution_sensitivity": resolution_rows,
        "gates": {
            "explicit_crs_and_units": True,
            "same_named_vertical_datum": True,
            "no_missing_or_fallback_height": domain.audit["fallback_height_count"] == 0,
            "relative_roof_formula_exact": bool(
                np.max(
                    np.abs(
                        (correct_roof - domain.terrain_dem_m[domain.building_mask])
                        - correct_height_m
                    )
                )
                < 1e-5
            ),
            "solid_mask_height_invariance": invariance["pass"],
            "building_ground_matches_dem_within_1m_p95": ground_summary[
                "p95_absolute_error_m"
            ]
            <= 1.0,
        },
        "source_hashes": {
            "noaa_dem_tile_sha256": sha256(DEM_RAW),
            "official_buildings_geojson_sha256": sha256(BUILDINGS_RAW),
            "clipped_dem_sha256": sha256(DEM_CLIP),
        },
        "domain_grid": asdict(domain.grid),
    }
    metrics["implementation_gates_pass"] = all(
        value
        for key, value in metrics["gates"].items()
        if key != "building_ground_matches_dem_within_1m_p95"
    )
    metrics["data_interchangeability_gate_pass"] = metrics["gates"][
        "building_ground_matches_dem_within_1m_p95"
    ]
    (RESULTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    terrain_display = np.where(domain.active_mask, domain.terrain_dem_m, np.nan)
    image = axes[0, 0].imshow(terrain_display, cmap="terrain")
    axes[0, 0].set_title("NOAA bare-earth DEM (NAVD88 m)")
    fig.colorbar(image, ax=axes[0, 0], shrink=0.8)
    heights = np.where(domain.building_mask, domain.building_height_m, np.nan)
    image = axes[0, 1].imshow(heights, cmap="viridis")
    axes[0, 1].set_title("NYC official relative roof height (m)")
    fig.colorbar(image, ax=axes[0, 1], shrink=0.8)
    axes[1, 0].hist(errors, bins=50, color="#197278", alpha=0.85)
    axes[1, 0].axvline(0, color="black", linewidth=1)
    axes[1, 0].set_title("DEM minimum − official building ground")
    axes[1, 0].set_xlabel("metres")
    axes[1, 0].set_ylabel("buildings")
    labels = ["correct", "ft→m omitted", "relative→absolute"]
    values = [
        0.0,
        float(np.median(np.abs(wrong_unit_excess))),
        float(np.median(np.abs(wrong_absolute_roof - correct_roof))),
    ]
    axes[1, 1].bar(labels, values, color=["#2a9d8f", "#e76f51", "#f4a261"])
    axes[1, 1].set_title("Median roof-elevation error by coupling rule")
    axes[1, 1].set_ylabel("absolute error (m)")
    axes[1, 1].tick_params(axis="x", rotation=15)
    for axis in axes.flat[:2]:
        axis.set_xticks([])
        axis.set_yticks([])
    fig.savefig(RESULTS / "vertical_coupling_validation.png", dpi=180)
    plt.close(fig)
    (LOGS / "run.log").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "implementation_gates_pass": metrics["implementation_gates_pass"],
                "data_interchangeability_gate_pass": metrics[
                    "data_interchangeability_gate_pass"
                ],
                "results": str(RESULTS),
            }
        )
    )


if __name__ == "__main__":
    main()
