#!/usr/bin/env python3
"""Audit the official NYC FloodNet event and deployment exports.

This program does not evaluate RainFall.  It establishes a reproducible,
quality-controlled observation target and pre-selects independent storm
clusters for a later event simulation.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
INCH_TO_M = 0.0254


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_profile(value: object) -> np.ndarray:
    if pd.isna(value):
        return np.array([], dtype=float)
    parsed = ast.literal_eval(str(value))
    return np.asarray(parsed, dtype=float)


def active_deployment(event: pd.Series, deployments: pd.DataFrame) -> pd.Series | None:
    candidates = deployments.loc[deployments["sensor_id"].eq(event.sensor_id)]
    candidates = candidates.loc[
        candidates["date_installed"].le(event.flood_start_time)
        & (
            candidates["date_removed"].isna()
            | candidates["date_removed"].ge(event.flood_end_time)
        )
    ]
    if candidates.empty:
        return None
    return candidates.sort_values("date_installed").iloc[-1]


def storm_clusters(events: pd.DataFrame, gap_hours: float = 12.0) -> pd.DataFrame:
    ordered = events.sort_values("flood_start_time").copy()
    gap = ordered["flood_start_time"].diff().dt.total_seconds().div(3600)
    ordered["storm_id"] = gap.gt(gap_hours).cumsum().add(1)
    rows: list[dict[str, object]] = []
    for storm_id, group in ordered.groupby("storm_id"):
        boroughs = sorted(x for x in group["borough"].dropna().unique())
        rows.append(
            {
                "storm_id": int(storm_id),
                "start_utc": group["flood_start_time"].min().isoformat(),
                "end_utc": group["flood_end_time"].max().isoformat(),
                "event_rows": int(len(group)),
                "unique_sensors": int(group["sensor_id"].nunique()),
                "borough_count": len(boroughs),
                "boroughs": ";".join(boroughs),
                "tidal_events": int(group["tidally_influenced"].eq("Yes").sum()),
                "non_tidal_events": int(group["tidally_influenced"].eq("No").sum()),
                "unknown_tidal_events": int(group["tidally_influenced"].isna().sum()),
                "max_depth_m_sensor": float(group["max_depth_m_sensor"].max()),
                "max_depth_m_local_low": float(group["max_depth_m_local_low"].max()),
                "median_duration_min": float(group["duration_mins"].median()),
            }
        )
    result = pd.DataFrame(rows)
    result["candidate_rank"] = (
        result.sort_values(
            ["unique_sensors", "borough_count", "max_depth_m_sensor"],
            ascending=[False, False, False],
        )
        .reset_index()
        .reset_index()
        .set_index("index")["level_0"]
        .add(1)
    )
    return result.sort_values("candidate_rank")


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    events_path = RAW / "floodnet_events.csv"
    deployments_path = RAW / "floodnet_deployments.csv"
    events = pd.read_csv(events_path)
    deployments = pd.read_csv(deployments_path)

    for column in ("flood_start_time", "flood_end_time"):
        events[column] = pd.to_datetime(events[column], utc=True, errors="coerce")
    for column in ("date_installed", "date_removed"):
        deployments[column] = pd.to_datetime(deployments[column], utc=True, errors="coerce")

    depths = events["flood_profile_depth_inches"].map(parse_profile)
    times = events["flood_profile_time_secs"].map(parse_profile)
    same_length = np.array([len(d) == len(t) and len(d) >= 2 for d, t in zip(depths, times)])
    monotonic = np.array([len(t) >= 2 and np.all(np.diff(t) > 0) for t in times])
    profile_max = np.array([float(np.max(d)) if len(d) else np.nan for d in depths])
    max_delta = np.abs(profile_max - events["max_depth_inches"].to_numpy(float))
    profile_duration_min = np.array(
        [(t[-1] - t[0]) / 60 if len(t) >= 2 else np.nan for t in times]
    )
    duration_delta = np.abs(profile_duration_min - events["duration_mins"].to_numpy(float))

    joined_rows = []
    active_hits = 0
    for _, event in events.iterrows():
        deployment = active_deployment(event, deployments)
        row = event.to_dict()
        if deployment is not None:
            active_hits += 1
            for column in (
                "tidally_influenced",
                "borough",
                "latitude",
                "longitude",
                "lowest_point_height_delta_inches",
                "date_installed",
                "date_removed",
            ):
                row[column] = deployment[column]
        else:
            for column in (
                "tidally_influenced",
                "borough",
                "latitude",
                "longitude",
                "lowest_point_height_delta_inches",
                "date_installed",
                "date_removed",
            ):
                row[column] = np.nan
        joined_rows.append(row)
    joined = pd.DataFrame(joined_rows)
    joined["max_depth_m_sensor"] = joined["max_depth_inches"] * INCH_TO_M
    delta = pd.to_numeric(joined["lowest_point_height_delta_inches"], errors="coerce")
    joined["max_depth_m_local_low"] = (joined["max_depth_inches"] + delta) * INCH_TO_M
    joined["profile_point_count"] = [len(x) for x in depths]
    joined["profile_equal_length"] = same_length
    joined["profile_monotonic_time"] = monotonic
    joined["profile_max_abs_error_inches"] = max_delta
    joined["profile_duration_abs_error_mins"] = duration_delta

    clusters = storm_clusters(joined)
    clusters.to_csv(RESULTS / "candidate_storms.csv", index=False)
    joined.drop(columns=["flood_profile_depth_inches", "flood_profile_time_secs"]).to_csv(
        RESULTS / "event_sensor_metrics.csv", index=False
    )
    joined.loc[
        (~joined["profile_equal_length"])
        | (~joined["profile_monotonic_time"])
        | joined["profile_max_abs_error_inches"].gt(0.011)
        | joined["profile_duration_abs_error_mins"].gt(0.02)
        | joined["borough"].isna()
    ].drop(columns=["flood_profile_depth_inches", "flood_profile_time_secs"]).to_csv(
        RESULTS / "flagged_events.csv", index=False
    )

    profile_rows = []
    for event_index, (event, depth, seconds) in enumerate(zip(joined.itertuples(), depths, times)):
        if len(depth) != len(seconds):
            continue
        for d, sec in zip(depth, seconds):
            profile_rows.append(
                {
                    "event_index": event_index,
                    "sensor_id": event.sensor_id,
                    "event_start_utc": event.flood_start_time.isoformat(),
                    "elapsed_seconds": float(sec),
                    "depth_m_sensor": float(d * INCH_TO_M),
                }
            )
    with (PROCESSED / "event_profiles_long.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=profile_rows[0].keys())
        writer.writeheader()
        writer.writerows(profile_rows)

    qc = {
        "dataset_snapshot": {
            "event_rows": int(len(events)),
            "unique_event_sensors": int(events["sensor_id"].nunique()),
            "deployment_rows": int(len(deployments)),
            "unique_deployment_sensors": int(deployments["sensor_id"].nunique()),
            "event_time_min_utc": events["flood_start_time"].min().isoformat(),
            "event_time_max_utc": events["flood_end_time"].max().isoformat(),
        },
        "profile_qc": {
            "valid_equal_length_profiles": int(same_length.sum()),
            "strictly_monotonic_time_profiles": int(monotonic.sum()),
            "max_matches_summary_within_0_011_in": int(np.sum(max_delta <= 0.011)),
            "largest_profile_max_difference_inches": float(np.nanmax(max_delta)),
            "duration_matches_summary_within_0_02_min": int(np.sum(duration_delta <= 0.02)),
            "largest_duration_difference_minutes": float(np.nanmax(duration_delta)),
            "total_profile_points": int(sum(map(len, depths))),
        },
        "deployment_join": {
            "events_with_active_deployment": active_hits,
            "events_without_active_deployment": int(len(events) - active_hits),
            "events_with_local_low_delta": int(delta.notna().sum()),
            "tidal_events": int(joined["tidally_influenced"].eq("Yes").sum()),
            "non_tidal_events": int(joined["tidally_influenced"].eq("No").sum()),
        },
        "storm_clustering": {
            "gap_hours": 12,
            "storm_clusters": int(len(clusters)),
            "top_candidate": clusters.iloc[0].to_dict(),
            "note": "Ranking is a reproducible screening rule, not a calibration/test split.",
        },
        "interpretation_limits": [
            "The event export contains only detected, human-QC flood episodes; it does not supply continuous dry-period observations.",
            "Flood depth is measured below the sensor. Local-low depth is an estimate obtained by adding deployment elevation delta.",
            "Rainfall, tide, DEM, drainage and boundary-condition inputs are not contained in this export.",
            "This audit does not constitute RainFall validation.",
        ],
    }
    (RESULTS / "qc_summary.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )

    manifest = []
    for path in sorted(RAW.iterdir()):
        if path.is_file():
            manifest.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            )
    (RESULTS / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    top = clusters.head(15).sort_values("candidate_rank", ascending=False)
    fig, ax = plt.subplots(figsize=(9, 5.4))
    colors = plt.cm.Blues(np.linspace(0.38, 0.88, len(top)))
    ax.barh(top["start_utc"].str[:10], top["unique_sensors"], color=colors)
    ax.set_xlabel("Unique FloodNet sensors in 12 h-gap storm cluster")
    ax.set_ylabel("Cluster start (UTC)")
    ax.set_title("NYC FloodNet candidate city-scale flood events")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(RESULTS / "candidate_storms.png", dpi=180)
    plt.close(fig)

    mappable = joined.dropna(subset=["longitude", "latitude", "max_depth_m_sensor"])
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    scatter = ax.scatter(
        mappable["longitude"],
        mappable["latitude"],
        c=mappable["max_depth_m_sensor"],
        s=np.clip(mappable["max_depth_m_sensor"] * 170, 8, 110),
        cmap="viridis",
        alpha=0.52,
        edgecolors="none",
    )
    fig.colorbar(scatter, ax=ax, label="Event maximum depth at sensor (m)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("All quality-controlled FloodNet event maxima")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(RESULTS / "event_maxima_map.png", dpi=180)
    plt.close(fig)

    status = {
        "experiment": "08_nyc_floodnet",
        "status": "DATA_AUDIT_COMPLETE_MODEL_RUN_PENDING",
        "data_downloaded": True,
        "data_audited": True,
        "rainfall_boundary_inputs_downloaded": False,
        "rainfall_model_executed": False,
        "formal_validation_complete": False,
        "reason": "The official event observations are ready, but event rainfall, tide, DEM, drainage and boundary inputs must be assembled before an honest model comparison.",
    }
    (RESULTS / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": status, "qc": qc}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
