#!/usr/bin/env python3
"""Audit the official USGS Muddy Creek observation and model archives."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import shapefile


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
METRICS = PROCESSED / "metrics" / "MuddyCreek_model_performance_calibration_metrics"
PT_DIR = METRICS / "MuddyCreek_PT_time_series"
FULL = PROCESSED / "full_model"
EVENTS = {
    "2021-03-17_validation": pd.Timestamp("2021-03-17 12:00:00"),
    "2021-04-29_validation": pd.Timestamp("2021-04-29 12:00:00"),
    "2021-05-27_calibration": pd.Timestamp("2021-05-27 12:00:00"),
    "2021-06-25_calibration": pd.Timestamp("2021-06-25 12:00:00"),
}


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_points(path: Path) -> list[dict[str, object]]:
    reader = shapefile.Reader(str(path))
    fields = [x[0] for x in reader.fields[1:]]
    rows = []
    for shape_record in reader.iterShapeRecords():
        row = dict(zip(fields, shape_record.record))
        if shape_record.shape.points:
            row["x"] = shape_record.shape.points[0][0]
            row["y"] = shape_record.shape.points[0][1]
        rows.append(row)
    return rows


def raster_record(path: Path) -> dict[str, object]:
    with rasterio.open(path) as src:
        band = src.read(1, masked=True)
        valid = band.compressed()
        return {
            "file": str(path.relative_to(ROOT)),
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtype": str(src.dtypes[0]),
            "crs": str(src.crs),
            "resolution_x": abs(float(src.transform.a)),
            "resolution_y": abs(float(src.transform.e)),
            "bounds": [float(v) for v in src.bounds],
            "nodata": src.nodata,
            "valid_cells": int(valid.size),
            "min": float(np.nanmin(valid)) if valid.size else None,
            "max": float(np.nanmax(valid)) if valid.size else None,
            "mean": float(np.nanmean(valid)) if valid.size else None,
        }


def hdf_inventory(path: Path) -> dict[str, object]:
    datasets = 0
    groups = 0
    samples: list[str] = []
    with h5py.File(path, "r") as handle:
        def visitor(name: str, obj: object) -> None:
            nonlocal datasets, groups
            if isinstance(obj, h5py.Dataset):
                datasets += 1
                if len(samples) < 20:
                    samples.append(name)
            elif isinstance(obj, h5py.Group):
                groups += 1
        handle.visititems(visitor)
    return {
        "file": str(path.relative_to(ROOT)),
        "groups": groups,
        "datasets": datasets,
        "sample_dataset_paths": samples,
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((RAW / "sciencebase_item.json").read_text(encoding="utf-8"))
    expected = {
        item["name"]: {
            "bytes": int(item.get("size", -1)),
            "md5": item.get("checksum", {}).get("value"),
        }
        for item in catalog["files"]
    }

    source_rows = []
    for path in sorted(RAW.iterdir()):
        if not path.is_file():
            continue
        published = expected.get(path.name, {})
        md5 = digest(path, "md5")
        source_rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "published_bytes": published.get("bytes"),
                "md5": md5,
                "published_md5": published.get("md5"),
                "size_match": path.stat().st_size == published.get("bytes"),
                "md5_match": md5 == published.get("md5"),
                "sha256": digest(path, "sha256"),
            }
        )
    pd.DataFrame(source_rows).to_csv(RESULTS / "source_manifest.csv", index=False)

    archive = RAW / "MuddyCreek_normal_existing_conditions.zip"
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        entries = [i for i in zf.infolist() if not i.is_dir()]
    extension_counts: dict[str, int] = {}
    for entry in entries:
        suffix = Path(entry.filename).suffix.lower() or "[none]"
        extension_counts[suffix] = extension_counts.get(suffix, 0) + 1

    pt_rows = []
    event_rows = []
    series_by_station: dict[str, pd.DataFrame] = {}
    for path in sorted(PT_DIR.glob("MuddyCreek_PT*_time_series.csv")):
        station = re.search(r"PT\d+", path.name).group(0)
        data = pd.read_csv(path)
        data["timestamp"] = pd.to_datetime(data["Date"] + " " + data["Time"], errors="coerce")
        data["elevation_ft"] = pd.to_numeric(data["Elevation, ft"], errors="coerce")
        data = data.sort_values("timestamp")
        seconds = data["timestamp"].diff().dt.total_seconds().dropna()
        series_by_station[station] = data
        pt_rows.append(
            {
                "station": station,
                "rows": len(data),
                "start": data["timestamp"].min().isoformat(),
                "end": data["timestamp"].max().isoformat(),
                "missing_timestamp": int(data["timestamp"].isna().sum()),
                "missing_elevation": int(data["elevation_ft"].isna().sum()),
                "duplicate_or_nonincreasing_time": int(seconds.le(0).sum()),
                "median_interval_seconds": float(seconds.median()),
                "intervals_equal_300_seconds_pct": float(seconds.eq(300).mean() * 100),
                "minimum_elevation_ft": float(data["elevation_ft"].min()),
                "maximum_elevation_ft": float(data["elevation_ft"].max()),
            }
        )
        for event_name, event_center in EVENTS.items():
            window = data.loc[
                data["timestamp"].between(
                    event_center - pd.Timedelta(hours=36),
                    event_center + pd.Timedelta(hours=36),
                )
            ]
            if window.empty:
                continue
            peak_row = window.loc[window["elevation_ft"].idxmax()]
            event_rows.append(
                {
                    "event": event_name,
                    "station": station,
                    "observed_peak_elevation_ft": float(peak_row["elevation_ft"]),
                    "observed_peak_time": peak_row["timestamp"].isoformat(),
                    "window_rows": int(len(window)),
                }
            )
    pt_quality = pd.DataFrame(pt_rows).sort_values("station")
    event_targets = pd.DataFrame(event_rows).sort_values(["event", "station"])
    pt_quality.to_csv(RESULTS / "pressure_transducer_quality.csv", index=False)
    event_targets.to_csv(RESULTS / "event_observation_targets.csv", index=False)

    point_sets = {
        "pressure_transducers": read_points(METRICS / "MuddyCreek_PT_locations" / "MuddyCreek_PT_locations.shp"),
        "high_water_marks": read_points(METRICS / "MuddyCreek_HWM_locations" / "MuddyCreek_HWM_locations.shp"),
    }
    for name, rows in point_sets.items():
        pd.DataFrame(rows).to_csv(RESULTS / f"{name}.csv", index=False)

    rasters = [raster_record(path) for path in sorted((PROCESSED / "depths").glob("*.tif"))]
    terrain = next(FULL.rglob("Existing_export.tif"))
    roughness = next(FULL.rglob("Manning's n.tif"))
    rasters.extend([raster_record(terrain), raster_record(roughness)])
    (RESULTS / "raster_inventory.json").write_text(
        json.dumps(rasters, indent=2) + "\n", encoding="utf-8"
    )

    hdf_paths = [
        next(FULL.rglob("Existing Conditions.hdf")),
        next(FULL.rglob("Manning's n.hdf")),
        next(FULL.rglob("SilverJackets-Ha.g09.hdf")),
    ]
    hdfs = [hdf_inventory(path) for path in hdf_paths]
    (RESULTS / "hdf_inventory.json").write_text(
        json.dumps(hdfs, indent=2) + "\n", encoding="utf-8"
    )

    metrics_text = (METRICS / "Model _performance_calibration_metrics.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    published_summary = {
        "hydrologic_events": {
            "2021-05-27_calibration": {"NSE": 0.909, "PBIAS_percent": -27.7},
            "2021-06-25_calibration": {"NSE": 0.947, "PBIAS_percent": -1.8},
            "2021-03-17_validation": {"NSE": 0.596, "PBIAS_percent": 23.9},
            "2021-04-29_validation": {"NSE": 0.736, "PBIAS_percent": -43.5},
        },
        "hydraulic_reference": {
            "text_table_present": "Table 7." in metrics_text,
            "note": "These are the publisher's HEC-HMS/HEC-RAS metrics, not RainFall results.",
        },
    }
    (RESULTS / "publisher_reference_metrics.json").write_text(
        json.dumps(published_summary, indent=2) + "\n", encoding="utf-8"
    )

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), sharex=False)
    for ax, (event_name, center) in zip(axes.flat, EVENTS.items()):
        for station, data in series_by_station.items():
            window = data.loc[
                data["timestamp"].between(center - pd.Timedelta(hours=24), center + pd.Timedelta(hours=24))
            ]
            if not window.empty:
                ax.plot(window["timestamp"], window["elevation_ft"], lw=1, label=station)
        ax.set_title(event_name.replace("_", " "))
        ax.set_ylabel("Observed WSE (ft, NAVD 88)")
        ax.tick_params(axis="x", rotation=22)
        ax.grid(alpha=0.2)
    axes[0, 0].legend(ncol=4, fontsize=7)
    fig.suptitle("USGS Muddy Creek 5-minute pressure-transducer observations")
    fig.tight_layout()
    fig.savefig(RESULTS / "event_observations.png", dpi=180)
    plt.close(fig)

    audit = {
        "source_integrity": {
            "catalogued_files_downloaded": len(source_rows),
            "all_downloaded_sizes_match": all(x["size_match"] for x in source_rows if x["published_bytes"] is not None),
            "all_zip_md5_match": all(x["md5_match"] for x in source_rows if x["file"].endswith(".zip")),
            "xml_md5_drift": next(x for x in source_rows if x["file"].endswith(".xml")),
        },
        "full_model_archive": {
            "zip_test": "PASS" if bad is None else f"FAIL:{bad}",
            "files": len(entries),
            "uncompressed_bytes": int(sum(x.file_size for x in entries)),
            "extension_counts": dict(sorted(extension_counts.items())),
            "contains_dem": terrain.exists(),
            "contains_roughness": roughness.exists(),
            "contains_hms_precipitation_store": any(FULL.rglob("*.dss")),
            "contains_ras_geometry": any(FULL.rglob("*.g*.hdf")),
        },
        "observations": {
            "pressure_transducers": len(pt_quality),
            "pressure_transducer_rows": int(pt_quality["rows"].sum()),
            "high_water_marks": len(point_sets["high_water_marks"]),
            "event_station_targets": len(event_targets),
        },
        "readiness": {
            "public_data_sufficient_for_adapter_development": True,
            "rainfall_model_executed": False,
            "formal_rainfall_validation_complete": False,
            "blocking_engine_gaps": [
                "HEC-DSS precipitation/hydrograph time series must be converted to an open tabular format.",
                "RainFall needs river/channel inflow and downstream stage boundary support for this catchment.",
                "Terrain, roughness and datum/unit conversion require a documented spatial adapter.",
                "Calibration and blind-test events must be frozen before parameter fitting.",
            ],
        },
    }
    (RESULTS / "audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "experiment": "09_usgs_muddy_creek",
        "status": "PUBLIC_ARCHIVE_COMPLETE_ADAPTER_REQUIRED",
        "data_downloaded": True,
        "data_integrity_checked": True,
        "observation_targets_extracted": True,
        "rainfall_model_executed": False,
        "formal_validation_complete": False,
    }
    (RESULTS / "status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": status, "audit": audit}, indent=2))


if __name__ == "__main__":
    main()
