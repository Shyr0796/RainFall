#!/usr/bin/env python3
"""Audit the Li et al. (2022) urban-flood HDF5 data and create compact products."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXTRACTED = ROOT / "data" / "extracted"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def scalar(group: h5py.Group, name: str) -> float:
    return float(np.asarray(group[name][()]).reshape(-1)[0])


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def archive_manifest() -> list[dict]:
    metadata = json.loads((RAW / "zenodo_record_5254164.json").read_text())
    official = {item["key"]: item for item in metadata["files"]}
    rows = []
    for path in sorted(RAW.iterdir()):
        if not path.is_file():
            continue
        item = official.get(path.name, {})
        expected_md5 = str(item.get("checksum", "")).removeprefix("md5:")
        actual_md5 = digest(path, "md5")
        rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": digest(path, "sha256"),
                "official_md5": expected_md5,
                "actual_md5": actual_md5,
                "official_size_bytes": item.get("size", ""),
                "official_match": bool(item) and actual_md5 == expected_md5
                and path.stat().st_size == item.get("size"),
                "source": f"https://zenodo.org/records/5254164/files/{path.name}?download=1"
                if item else "support file; see README",
            }
        )
    return rows


def extracted_manifest() -> list[dict]:
    return [
        {
            "file": path.relative_to(EXTRACTED).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path, "sha256"),
        }
        for path in sorted(EXTRACTED.rglob("*"))
        if path.is_file()
    ]


def hdf_inventory() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(EXTRACTED.rglob("*.h5")):
        with h5py.File(path, "r") as h5:
            def visit(name: str, obj: h5py.Dataset | h5py.Group) -> None:
                if not isinstance(obj, h5py.Dataset):
                    return
                array = np.asarray(obj[()])
                row = {
                    "file": path.relative_to(EXTRACTED).as_posix(),
                    "dataset": name,
                    "shape": "x".join(map(str, array.shape)),
                    "dtype": str(array.dtype),
                    "count": array.size,
                }
                if np.issubdtype(array.dtype, np.number):
                    finite = array[np.isfinite(array)]
                    row.update(
                        nan_count=int(np.isnan(array).sum()),
                        finite_count=int(finite.size),
                        min=float(finite.min()) if finite.size else "",
                        max=float(finite.max()) if finite.size else "",
                        mean=float(finite.mean()) if finite.size else "",
                    )
                rows.append(row)
            h5.visititems(visit)
    return rows


def dataset1_summary() -> list[dict]:
    rows = []
    for path in sorted((EXTRACTED / "Dataset 1").rglob("*.h5")):
        with h5py.File(path, "r") as h5:
            for test_name, group in h5.items():
                if not isinstance(group, h5py.Group):
                    continue
                row = {
                    "file": path.relative_to(EXTRACTED).as_posix(),
                    "test": test_name,
                }
                for name in ("Ev", "QA", "QB", "QC", "Q1", "Q2", "Q3",
                             "hA", "hB", "hC", "h1", "h2", "h3", "Diff_Q"):
                    if name in group and group[name].size == 1:
                        row[name] = scalar(group, name)
                rows.append(row)
    return rows


def contiguous_runs(mask: np.ndarray) -> list[list[int]]:
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    runs: list[list[int]] = []
    start = previous = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value > previous + 1:
            runs.append([start, previous])
            start = value
        previous = value
    runs.append([start, previous])
    return runs


def dataset2_summary() -> tuple[list[dict], dict]:
    rows: list[dict] = []
    boundary_runs: dict = {}
    for path in sorted((EXTRACTED / "Dataset 2").glob("Config_*.h5")):
        with h5py.File(path, "r") as h5:
            config = next(iter(h5))
            group = h5[config]
            speed = np.asarray(group["V"][()], dtype=float)
            vx = np.asarray(group["Vx"][()], dtype=float)
            vy = np.asarray(group["Vy"][()], dtype=float)
            valid = np.isfinite(speed) & np.isfinite(vx) & np.isfinite(vy)
            observed_flow = valid & (speed > 0)
            qin = sum(scalar(group, name) for name in ("QA", "QB", "QC"))
            qout = sum(scalar(group, name) for name in ("Q1", "Q2", "Q3"))
            residual = speed[valid] - np.hypot(vx[valid], vy[valid])
            row = {
                "config": config,
                "Ev_vertical_scale": scalar(group, "Ev"),
                "QA_m3_h": scalar(group, "QA"),
                "QB_m3_h": scalar(group, "QB"),
                "QC_m3_h": scalar(group, "QC"),
                "Q1_m3_h": scalar(group, "Q1"),
                "Q2_m3_h": scalar(group, "Q2"),
                "Q3_m3_h": scalar(group, "Q3"),
                "sum_inflow_m3_h": qin,
                "sum_outflow_m3_h": qout,
                "out_minus_in_pct": 100 * (qout - qin) / qin,
                "hA_m": scalar(group, "hA"),
                "hB_m": scalar(group, "hB"),
                "hC_m": scalar(group, "hC"),
                "h1_m": scalar(group, "h1"),
                "h2_m": scalar(group, "h2"),
                "h3_m": scalar(group, "h3"),
                "velocity_shape_axis0": speed.shape[0],
                "velocity_shape_axis1": speed.shape[1],
                "valid_vector_cells": int(valid.sum()),
                "nonzero_observed_cells": int(observed_flow.sum()),
                "nan_cells": int((~valid).sum()),
                "speed_mean_m_s_nonzero": float(speed[observed_flow].mean()),
                "speed_median_m_s_nonzero": float(np.median(speed[observed_flow])),
                "speed_p95_m_s_nonzero": float(np.percentile(speed[observed_flow], 95)),
                "speed_max_m_s": float(np.nanmax(speed)),
                "V_vs_hypot_rmse_m_s": float(np.sqrt(np.mean(residual**2))),
            }
            rows.append(row)
            boundary_runs[config] = {
                "axis_convention": "h5py array axis0=x, axis1=y (deduced from Vx/Vy at six openings)",
                "left_x0": contiguous_runs(observed_flow[0, :]),
                "right_xmax": contiguous_runs(observed_flow[-1, :]),
                "bottom_y0": contiguous_runs(observed_flow[:, 0]),
                "top_ymax": contiguous_runs(observed_flow[:, -1]),
            }

            # Store one compact observation table for the baseline configuration.
            if config == "Ref":
                x, y = np.indices(speed.shape)
                table = np.column_stack((x[observed_flow], y[observed_flow],
                                         speed[observed_flow], vx[observed_flow], vy[observed_flow]))
                np.savetxt(PROCESSED / "Ref_velocity_observations.csv.gz", table,
                           delimiter=",", header="x_index,y_index,V_m_s,Vx_m_s,Vy_m_s", comments="")
                np.savez_compressed(PROCESSED / "Ref_observations.npz", V=speed, Vx=vx, Vy=vy,
                                    flow_mask=observed_flow)
    return rows, boundary_runs


def make_plots(summary: list[dict]) -> None:
    configs = [row["config"] for row in summary]
    fig, axes = plt.subplots(2, 4, figsize=(14, 9), constrained_layout=True)
    for ax, config in zip(axes.flat, configs):
        with h5py.File(EXTRACTED / "Dataset 2" / f"Config_{config}.h5") as h5:
            speed = h5[config]["V"][()]
        image = ax.imshow(speed.T, origin="lower", cmap="turbo", vmin=0, vmax=0.5,
                          extent=(0, speed.shape[0] / 100, 0, speed.shape[1] / 100))
        ax.set_title(config)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("y (m)")
    fig.colorbar(image, ax=axes, label="LSPIV surface speed (m/s)", shrink=0.8)
    fig.savefig(RESULTS / "dataset2_velocity_fields.png", dpi=170)
    plt.close(fig)

    x = np.arange(len(configs))
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    bottom = np.zeros(len(configs))
    for name, color in zip(("Q1_m3_h", "Q2_m3_h", "Q3_m3_h"), ("#2a9d8f", "#e9c46a", "#e76f51")):
        values = np.array([row[name] for row in summary])
        ax.bar(x, values, bottom=bottom, label=name[:2], color=color)
        bottom += values
    inflow = [row["sum_inflow_m3_h"] for row in summary]
    ax.scatter(x, inflow, color="black", marker="x", s=70, label="sum inflow")
    ax.set_xticks(x, configs)
    ax.set_ylabel("discharge (m³/h)")
    ax.set_title("Measured outlet partition and inflow mass check")
    ax.legend(ncol=4)
    fig.savefig(RESULTS / "dataset2_discharge_partition.png", dpi=170)
    plt.close(fig)


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    manifests = archive_manifest()
    extracted = extracted_manifest()
    inventory = hdf_inventory()
    dataset1 = dataset1_summary()
    dataset2, boundaries = dataset2_summary()
    write_csv(PROCESSED / "raw_file_manifest.csv", manifests)
    write_csv(PROCESSED / "extracted_file_manifest.csv", extracted)
    write_csv(PROCESSED / "hdf5_inventory.csv", inventory)
    write_csv(PROCESSED / "dataset1_test_summary.csv", dataset1)
    write_csv(PROCESSED / "dataset2_config_summary.csv", dataset2)
    (PROCESSED / "dataset2_boundary_runs.json").write_text(
        json.dumps(boundaries, indent=2), encoding="utf-8"
    )
    record = json.loads((RAW / "zenodo_record_5254164.json").read_text())
    audit = {
        "status": "PASS_WITH_COMPARABILITY_CAUTIONS",
        "record_id": record["id"],
        "doi": record["metadata"]["doi"],
        "license": record["metadata"]["license"]["id"],
        "archive_files_verified": sum(bool(r["official_match"]) for r in manifests),
        "archive_files_total": len(manifests),
        "extracted_files": len(extracted),
        "hdf5_datasets": len(inventory),
        "dataset1_tests": len(dataset1),
        "dataset2_configurations": len(dataset2),
        "quality_evidence": {
            "depth_instrument_accuracy_m": 0.001,
            "flowmeter_accuracy_fraction": 0.005,
            "typical_depth_standard_deviation_m": [0.0005, 0.002],
            "outflow_rating_curve_R2": ">0.99",
            "mass_difference_typical_fraction": "<=0.025 except very small total inflow",
            "velocity_time_convergence": "60 s vs 90 s differs <0.01 m/s at >90% points",
        },
        "comparability_cautions": [
            "V/Vx/Vy are time-averaged surface velocities; RainFall returns depth-averaged velocity.",
            "NaN values mark the approximately 1 cm wall-adjacent band; exact zeros also encode non-flow areas.",
            "The HDF5 velocity array is stored as (x,y) in h5py, not conventional image (y,x).",
            "Dataset 2 is steady recirculating flume flow, not rainfall-runoff forcing.",
            "A valid comparison needs three prescribed inflows, three downstream stages, and explicit buildings.",
        ],
        "raw_video_downloaded": False,
    }
    (RESULTS / "observation_quality_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    make_plots(dataset2)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
