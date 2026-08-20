from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(slots=True)
class GridMetadata:
    """Spatial metadata shared by the DEM, buildings and solver grid."""

    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    cell_size_x_m: float
    cell_size_y_m: float
    bounds: tuple[float, float, float, float]
    source_dem: str | None = None
    source_buildings: str | None = None


@dataclass(slots=True)
class UrbanDomain:
    """A metric hydraulic domain prepared from a raster DEM and building vectors."""

    terrain_dem_m: np.ndarray
    surface_dem_m: np.ndarray
    active_mask: np.ndarray
    building_mask: np.ndarray
    building_height_m: np.ndarray
    grid: GridMetadata
    audit: dict[str, Any]

    @property
    def cell_size_m(self) -> float:
        if not math.isclose(
            self.grid.cell_size_x_m, self.grid.cell_size_y_m, rel_tol=1e-5
        ):
            raise ValueError("The hydraulic solver currently requires square cells")
        return 0.5 * (self.grid.cell_size_x_m + self.grid.cell_size_y_m)


def _require_gis():
    try:
        import fiona
        import rasterio
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "GIS support is optional; install it with `uv sync --extra gis`."
        ) from exc
    return fiona, rasterio


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _vector_component_hashes(path: Path) -> dict[str, str]:
    if path.suffix.lower() != ".shp":
        return {path.name: _sha256(path)}
    components: dict[str, str] = {}
    for candidate in sorted(path.parent.glob(f"{path.stem}.*")):
        if candidate.is_file():
            components[candidate.name] = _sha256(candidate)
    return components


def _metric_factor(crs: Any) -> float | None:
    if crs is None or not crs.is_projected:
        return None
    try:
        _, factor = crs.linear_units_factor
        return float(factor)
    except (AttributeError, TypeError, ValueError):
        return None


def _local_utm_crs(src_crs: Any, bounds: Any, rasterio: Any) -> Any:
    from rasterio.warp import transform_bounds

    west, south, east, north = transform_bounds(
        src_crs, "EPSG:4326", *bounds, densify_pts=21
    )
    lon = 0.5 * (west + east)
    lat = 0.5 * (south + north)
    zone = min(60, max(1, int(math.floor((lon + 180.0) / 6.0)) + 1))
    epsg = (32600 if lat >= 0.0 else 32700) + zone
    return rasterio.crs.CRS.from_epsg(epsg)


def prepare_urban_domain(
    dem_path: str | Path,
    building_path: str | Path,
    *,
    target_crs: str | None = None,
    resolution_m: float | None = None,
    height_field: str | None = None,
    default_height_m: float = 10.0,
    height_mode: str = "relative",
    vertical_scale_to_m: float = 1.0,
    building_height_scale_to_m: float = 1.0,
    ground_elevation_field: str | None = None,
    building_ground_scale_to_m: float = 1.0,
    dem_vertical_datum: str | None = None,
    building_vertical_datum: str | None = None,
    building_to_dem_vertical_offset_m: float | None = None,
    roof_base_source: str = "dem_cell",
    missing_height_policy: str = "default",
    minimum_height_m: float = 0.1,
    max_ground_mismatch_m: float | None = None,
    strict_vertical: bool = False,
    all_touched: bool = False,
) -> UrbanDomain:
    """Align a DEM and building polygons in one CRS and hydraulic grid.

    ``height_mode='relative'`` interprets the vector height as building height above
    local ground. ``'absolute'`` interprets it as roof elevation in the DEM datum.
    The returned building mask remains the authoritative solid-volume geometry;
    the raised surface DEM is intended for visualization/export and optional models.
    """

    fiona, rasterio = _require_gis()
    from fiona.transform import transform_geom
    from rasterio.enums import Resampling
    from rasterio.features import rasterize
    from rasterio.transform import array_bounds
    from rasterio.warp import calculate_default_transform, reproject

    dem_path = Path(dem_path).expanduser().resolve()
    building_path = Path(building_path).expanduser().resolve()
    if not dem_path.is_file():
        raise FileNotFoundError(dem_path)
    if not building_path.is_file():
        raise FileNotFoundError(building_path)
    if resolution_m is not None and resolution_m <= 0:
        raise ValueError("resolution_m must be positive")
    if (
        default_height_m < 0
        or vertical_scale_to_m <= 0
        or building_height_scale_to_m <= 0
        or building_ground_scale_to_m <= 0
    ):
        raise ValueError("height values must be nonnegative and all scales positive")
    if height_mode not in {"relative", "absolute"}:
        raise ValueError("height_mode must be 'relative' or 'absolute'")
    if roof_base_source not in {"dem_cell", "building_ground"}:
        raise ValueError("roof_base_source must be 'dem_cell' or 'building_ground'")
    if roof_base_source == "building_ground" and not ground_elevation_field:
        raise ValueError("building_ground roof base requires ground_elevation_field")
    if missing_height_policy not in {"default", "error"}:
        raise ValueError("missing_height_policy must be 'default' or 'error'")
    if minimum_height_m < 0:
        raise ValueError("minimum_height_m must be nonnegative")
    if max_ground_mismatch_m is not None and max_ground_mismatch_m < 0:
        raise ValueError("max_ground_mismatch_m must be nonnegative")
    if strict_vertical:
        if not dem_vertical_datum:
            raise ValueError("strict_vertical requires dem_vertical_datum")
        if ground_elevation_field and not building_vertical_datum:
            raise ValueError(
                "strict_vertical with a ground field requires building_vertical_datum"
            )
    datum_offset_m = 0.0
    if ground_elevation_field:
        if dem_vertical_datum and building_vertical_datum:
            same_datum = dem_vertical_datum.strip().upper() == building_vertical_datum.strip().upper()
            if not same_datum and building_to_dem_vertical_offset_m is None:
                raise ValueError(
                    "Building and DEM vertical datums differ; provide an audited offset"
                )
        datum_offset_m = float(building_to_dem_vertical_offset_m or 0.0)

    with rasterio.open(dem_path) as src:
        if src.crs is None:
            raise ValueError("DEM has no CRS; assign one before hydraulic use")
        dst_crs = rasterio.crs.CRS.from_user_input(target_crs) if target_crs else src.crs
        if target_crs is None and _metric_factor(dst_crs) is None:
            dst_crs = _local_utm_crs(src.crs, src.bounds, rasterio)

        unit_factor = _metric_factor(dst_crs)
        if unit_factor is None:
            raise ValueError("Target CRS must be projected with known linear units")
        resolution_units = resolution_m / unit_factor if resolution_m else None
        needs_warp = dst_crs != src.crs or resolution_units is not None
        if needs_warp:
            transform, width, height = calculate_default_transform(
                src.crs,
                dst_crs,
                src.width,
                src.height,
                *src.bounds,
                resolution=resolution_units,
            )
            terrain = np.full((height, width), np.nan, dtype=np.float32)
            source = src.read(1, masked=True).filled(np.nan).astype(np.float32)
            reproject(
                source=source,
                destination=terrain,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs=dst_crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
        else:
            transform = src.transform
            width, height = src.width, src.height
            terrain = src.read(1, masked=True).filled(np.nan).astype(np.float32)

    terrain *= np.float32(vertical_scale_to_m)
    active_mask = np.isfinite(terrain)
    if not np.any(active_mask):
        raise ValueError("DEM contains no finite cells after reprojection")

    geometries: list[dict[str, Any]] = []
    height_shapes: list[tuple[dict[str, Any], float]] = []
    ground_shapes: list[tuple[dict[str, Any], float]] = []
    feature_id_shapes: list[tuple[dict[str, Any], int]] = []
    skipped_empty = 0
    fallback_heights = 0
    missing_ground_elevations = 0
    with fiona.open(building_path) as vector:
        vector_crs = vector.crs_wkt or vector.crs
        if not vector_crs:
            raise ValueError("Building vector has no CRS; provide a .prj or defined CRS")
        for feature in vector:
            geometry = feature.get("geometry")
            if not geometry:
                skipped_empty += 1
                continue
            geometry = transform_geom(vector_crs, dst_crs.to_wkt(), geometry)
            properties = feature.get("properties", {})
            raw_height = (
                properties.get(height_field)
                if height_field
                else default_height_m
            )
            try:
                height_value = float(raw_height) * building_height_scale_to_m
                if not np.isfinite(height_value) or height_value < minimum_height_m:
                    raise ValueError
            except (TypeError, ValueError):
                if missing_height_policy == "error":
                    raise ValueError(
                        f"Building height is missing/invalid for feature {feature.get('id')}"
                    )
                height_value = float(default_height_m)
                fallback_heights += 1
            geometries.append(geometry)
            height_shapes.append((geometry, height_value))
            feature_id_shapes.append((geometry, len(geometries)))
            if ground_elevation_field:
                raw_ground = properties.get(ground_elevation_field)
                try:
                    ground_value = (
                        float(raw_ground) * building_ground_scale_to_m + datum_offset_m
                    )
                    if not np.isfinite(ground_value):
                        raise ValueError
                except (TypeError, ValueError):
                    missing_ground_elevations += 1
                else:
                    ground_shapes.append((geometry, ground_value))

    if geometries:
        building_mask = rasterize(
            geometries,
            out_shape=(height, width),
            transform=transform,
            fill=0,
            default_value=1,
            all_touched=all_touched,
            dtype="uint8",
        ).astype(bool)
        building_height = rasterize(
            height_shapes,
            out_shape=(height, width),
            transform=transform,
            fill=0.0,
            all_touched=all_touched,
            dtype="float32",
        )
        feature_ids = rasterize(
            feature_id_shapes,
            out_shape=(height, width),
            transform=transform,
            fill=0,
            all_touched=all_touched,
            dtype="int32",
        )
        building_ground = rasterize(
            ground_shapes,
            out_shape=(height, width),
            transform=transform,
            fill=np.nan,
            all_touched=all_touched,
            dtype="float32",
        ) if ground_shapes else np.full((height, width), np.nan, dtype=np.float32)
    else:
        building_mask = np.zeros((height, width), dtype=bool)
        building_height = np.zeros((height, width), dtype=np.float32)
        feature_ids = np.zeros((height, width), dtype=np.int32)
        building_ground = np.full((height, width), np.nan, dtype=np.float32)
    building_mask &= active_mask
    building_height = np.where(building_mask, building_height, 0.0).astype(np.float32)

    surface = terrain.copy()
    if height_mode == "relative":
        if roof_base_source == "building_ground":
            valid_ground = building_mask & np.isfinite(building_ground)
            if not np.all(valid_ground[building_mask]):
                raise ValueError(
                    "roof_base_source='building_ground' requires a valid ground value for every building cell"
                )
            surface[building_mask] = (
                building_ground[building_mask] + building_height[building_mask]
            )
        else:
            surface[building_mask] = terrain[building_mask] + building_height[building_mask]
    else:
        surface[building_mask] = np.maximum(
            terrain[building_mask], building_height[building_mask]
        )

    cell_x_m = abs(float(transform.a)) * unit_factor
    cell_y_m = abs(float(transform.e)) * unit_factor
    west, south, east, north = array_bounds(height, width, transform)
    grid = GridMetadata(
        crs=dst_crs.to_string(),
        transform=tuple(float(value) for value in transform[:6]),
        width=width,
        height=height,
        cell_size_x_m=cell_x_m,
        cell_size_y_m=cell_y_m,
        bounds=(float(west), float(south), float(east), float(north)),
        source_dem=str(dem_path),
        source_buildings=str(building_path),
    )
    cell_area = cell_x_m * cell_y_m
    ground_errors: list[float] = []
    if ground_shapes:
        for feature_id in range(1, len(geometries) + 1):
            cells = (feature_ids == feature_id) & active_mask
            grounds = building_ground[cells]
            grounds = grounds[np.isfinite(grounds)]
            if not np.any(cells) or grounds.size == 0:
                continue
            # The vector field is defined as the lowest ground elevation at the
            # footprint, so compare it with the minimum bare-earth DEM cell.
            ground_errors.append(float(np.min(terrain[cells]) - grounds[0]))
    ground_error_array = np.asarray(ground_errors, dtype=np.float64)
    ground_check = {
        "compared_features": int(ground_error_array.size),
        "dem_minus_vector_mean_m": (
            float(np.mean(ground_error_array)) if ground_error_array.size else None
        ),
        "dem_minus_vector_median_m": (
            float(np.median(ground_error_array)) if ground_error_array.size else None
        ),
        "absolute_error_mae_m": (
            float(np.mean(np.abs(ground_error_array))) if ground_error_array.size else None
        ),
        "absolute_error_p95_m": (
            float(np.percentile(np.abs(ground_error_array), 95))
            if ground_error_array.size
            else None
        ),
        "absolute_error_max_m": (
            float(np.max(np.abs(ground_error_array))) if ground_error_array.size else None
        ),
        "within_0_5_m_fraction": (
            float(np.mean(np.abs(ground_error_array) <= 0.5))
            if ground_error_array.size
            else None
        ),
        "within_1_m_fraction": (
            float(np.mean(np.abs(ground_error_array) <= 1.0))
            if ground_error_array.size
            else None
        ),
        "within_2_m_fraction": (
            float(np.mean(np.abs(ground_error_array) <= 2.0))
            if ground_error_array.size
            else None
        ),
    }
    if (
        max_ground_mismatch_m is not None
        and ground_error_array.size
        and ground_check["absolute_error_p95_m"] > max_ground_mismatch_m
    ):
        raise ValueError(
            "Building ground elevations fail the DEM coupling gate: "
            f"p95={ground_check['absolute_error_p95_m']:.3f} m > "
            f"{max_ground_mismatch_m:.3f} m"
        )
    audit = {
        "dem_sha256": _sha256(dem_path),
        "building_component_sha256": _vector_component_hashes(building_path),
        "feature_count": len(geometries),
        "skipped_empty_geometries": skipped_empty,
        "fallback_height_count": fallback_heights,
        "missing_ground_elevation_count": missing_ground_elevations,
        "height_field": height_field,
        "default_height_m": default_height_m,
        "height_mode": height_mode,
        "vertical_scale_to_m": vertical_scale_to_m,
        "building_height_scale_to_m": building_height_scale_to_m,
        "ground_elevation_field": ground_elevation_field,
        "building_ground_scale_to_m": building_ground_scale_to_m,
        "dem_vertical_datum": dem_vertical_datum,
        "building_vertical_datum": building_vertical_datum,
        "building_to_dem_vertical_offset_m": datum_offset_m,
        "roof_base_source": roof_base_source,
        "missing_height_policy": missing_height_policy,
        "minimum_height_m": minimum_height_m,
        "max_ground_mismatch_m": max_ground_mismatch_m,
        "strict_vertical": strict_vertical,
        "ground_coupling_check": ground_check,
        "all_touched": all_touched,
        "active_cells": int(active_mask.sum()),
        "building_cells": int(building_mask.sum()),
        "building_plan_area_m2": float(building_mask.sum() * cell_area),
        "solid_volume_proxy_m3": float((building_height * cell_area).sum()),
        "building_height_min_m": (
            float(building_height[building_mask].min()) if np.any(building_mask) else None
        ),
        "building_height_median_m": (
            float(np.median(building_height[building_mask])) if np.any(building_mask) else None
        ),
        "building_height_max_m": (
            float(building_height[building_mask].max()) if np.any(building_mask) else None
        ),
    }
    return UrbanDomain(
        terrain_dem_m=terrain,
        surface_dem_m=surface,
        active_mask=active_mask,
        building_mask=building_mask,
        building_height_m=building_height,
        grid=grid,
        audit=audit,
    )


def save_urban_domain(domain: UrbanDomain, output_path: str | Path) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.dumps(
        {"grid": asdict(domain.grid), "audit": domain.audit},
        ensure_ascii=False,
        sort_keys=True,
    )
    np.savez_compressed(
        output,
        terrain_dem_m=domain.terrain_dem_m.astype(np.float32),
        surface_dem_m=domain.surface_dem_m.astype(np.float32),
        active_mask=domain.active_mask.astype(np.uint8),
        building_mask=domain.building_mask.astype(np.uint8),
        building_height_m=domain.building_height_m.astype(np.float32),
        metadata_json=np.asarray(metadata),
    )
    return output


def load_urban_domain(path: str | Path) -> UrbanDomain:
    source = Path(path).expanduser().resolve()
    with np.load(source, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        return UrbanDomain(
            terrain_dem_m=archive["terrain_dem_m"].astype(np.float32),
            surface_dem_m=archive["surface_dem_m"].astype(np.float32),
            active_mask=archive["active_mask"].astype(bool),
            building_mask=archive["building_mask"].astype(bool),
            building_height_m=archive["building_height_m"].astype(np.float32),
            grid=GridMetadata(**metadata["grid"]),
            audit=metadata["audit"],
        )
