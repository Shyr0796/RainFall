#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from rainfall_ca.geospatial import prepare_urban_domain, save_urban_domain


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Align a GeoTIFF DEM and building Shapefile into one solver grid."
    )
    parser.add_argument("--dem", required=True, help="Input DEM raster (for example GeoTIFF)")
    parser.add_argument("--buildings", required=True, help="Building Shapefile/GPKG/GeoJSON")
    parser.add_argument("--output", required=True, help="Output compressed .npz domain")
    parser.add_argument("--target-crs", help="Projected output CRS, e.g. EPSG:32650")
    parser.add_argument("--resolution-m", type=float, help="Optional square grid resolution")
    parser.add_argument("--height-field", help="Building height attribute")
    parser.add_argument("--default-height-m", type=float, default=10.0)
    parser.add_argument(
        "--height-mode", choices=("relative", "absolute"), default="relative"
    )
    parser.add_argument("--vertical-scale-to-m", type=float, default=1.0)
    parser.add_argument("--building-height-scale-to-m", type=float, default=1.0)
    parser.add_argument("--ground-elevation-field")
    parser.add_argument("--building-ground-scale-to-m", type=float, default=1.0)
    parser.add_argument("--dem-vertical-datum")
    parser.add_argument("--building-vertical-datum")
    parser.add_argument("--building-to-dem-vertical-offset-m", type=float)
    parser.add_argument(
        "--roof-base-source",
        choices=("dem_cell", "building_ground"),
        default="dem_cell",
    )
    parser.add_argument(
        "--missing-height-policy", choices=("default", "error"), default="default"
    )
    parser.add_argument("--minimum-height-m", type=float, default=0.1)
    parser.add_argument("--max-ground-mismatch-m", type=float)
    parser.add_argument("--strict-vertical", action="store_true")
    parser.add_argument("--all-touched", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    domain = prepare_urban_domain(
        args.dem,
        args.buildings,
        target_crs=args.target_crs,
        resolution_m=args.resolution_m,
        height_field=args.height_field,
        default_height_m=args.default_height_m,
        height_mode=args.height_mode,
        vertical_scale_to_m=args.vertical_scale_to_m,
        building_height_scale_to_m=args.building_height_scale_to_m,
        ground_elevation_field=args.ground_elevation_field,
        building_ground_scale_to_m=args.building_ground_scale_to_m,
        dem_vertical_datum=args.dem_vertical_datum,
        building_vertical_datum=args.building_vertical_datum,
        building_to_dem_vertical_offset_m=args.building_to_dem_vertical_offset_m,
        roof_base_source=args.roof_base_source,
        missing_height_policy=args.missing_height_policy,
        minimum_height_m=args.minimum_height_m,
        max_ground_mismatch_m=args.max_ground_mismatch_m,
        strict_vertical=args.strict_vertical,
        all_touched=args.all_touched,
    )
    output = save_urban_domain(domain, args.output)
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(
        json.dumps(
            {"domain_file": str(output), "grid": asdict(domain.grid), "audit": domain.audit},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "manifest": str(manifest), **domain.audit}))


if __name__ == "__main__":
    main()
