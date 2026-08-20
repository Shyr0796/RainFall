#!/usr/bin/env python3
"""Audit the official USGS gauge series without pretending to simulate it."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
PROCESSED = ROOT / "data" / "processed"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_usgs_rdb(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as stream:
        for raw_line in stream:
            if not raw_line.startswith("USGS\t"):
                continue
            fields = raw_line.rstrip("\n").split("\t")
            if len(fields) < 8:
                continue
            records.append(
                {
                    "site_no": fields[1],
                    "datetime_local": datetime.strptime(fields[2], "%Y-%m-%d %H:%M"),
                    "timezone": fields[3],
                    "discharge_cfs": float(fields[4]),
                    "discharge_quality": fields[5],
                    "gage_height_ft": float(fields[6]),
                    "gage_height_quality": fields[7],
                }
            )
    if not records:
        raise ValueError(f"no USGS data records found in {path}")
    return records


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    source = RAW / "usgs_nwis_05485605_05485640_2018.tsv"
    records = read_usgs_rdb(source)
    by_site: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_site[str(record["site_no"])].append(record)

    summaries: dict[str, object] = {}
    for site, rows in sorted(by_site.items()):
        peak_q = max(rows, key=lambda item: float(item["discharge_cfs"]))
        peak_h = max(rows, key=lambda item: float(item["gage_height_ft"]))
        summaries[site] = {
            "records": len(rows),
            "start_local": rows[0]["datetime_local"].isoformat(),
            "end_local": rows[-1]["datetime_local"].isoformat(),
            "peak_discharge_cfs": peak_q["discharge_cfs"],
            "peak_discharge_datetime_local": peak_q["datetime_local"].isoformat(),
            "peak_gage_height_ft": peak_h["gage_height_ft"],
            "peak_gage_datetime_local": peak_h["datetime_local"].isoformat(),
            "all_values_approved": all(
                row["discharge_quality"] == "A" and row["gage_height_quality"] == "A"
                for row in rows
            ),
        }

    serializable_rows = []
    for row in records:
        output = dict(row)
        output["datetime_local"] = row["datetime_local"].isoformat()
        serializable_rows.append(output)
    with (RESULTS / "gauge_timeseries.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(serializable_rows[0]))
        writer.writeheader()
        writer.writerows(serializable_rows)

    figure, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for site, rows in sorted(by_site.items()):
        time = [row["datetime_local"] for row in rows]
        axes[0].plot(time, [row["discharge_cfs"] for row in rows], label=site)
        axes[1].plot(time, [row["gage_height_ft"] for row in rows], label=site)
    axes[0].set_ylabel("Discharge (ft³/s)")
    axes[1].set_ylabel("Gage height (ft)")
    axes[1].set_xlabel("Local time (CDT)")
    axes[0].legend(title="USGS site")
    axes[0].grid(alpha=0.25)
    axes[1].grid(alpha=0.25)
    figure.suptitle("Fourmile Creek observed hydrographs, 29 Jun–3 Jul 2018")
    figure.tight_layout()
    figure.savefig(RESULTS / "observed_hydrographs.png", dpi=180)
    plt.close(figure)

    hwm_path = PROCESSED / "high_water_marks_table3.csv"
    with hwm_path.open(encoding="utf-8") as stream:
        hwm_rows = list(csv.DictReader(stream))
    surveyed = [
        row
        for row in hwm_rows
        if row["downstream_hwm_ft_navd88"] or row["upstream_hwm_ft_navd88"]
    ]
    hwm_figure, hwm_axis = plt.subplots(figsize=(10, 5.5))
    downstream_x = [float(row["river_miles"]) for row in surveyed if row["downstream_hwm_ft_navd88"]]
    downstream_y = [float(row["downstream_hwm_ft_navd88"]) for row in surveyed if row["downstream_hwm_ft_navd88"]]
    upstream_x = [float(row["river_miles"]) for row in surveyed if row["upstream_hwm_ft_navd88"]]
    upstream_y = [float(row["upstream_hwm_ft_navd88"]) for row in surveyed if row["upstream_hwm_ft_navd88"]]
    hwm_axis.plot(downstream_x, downstream_y, "o-", label="Downstream HWM")
    hwm_axis.plot(upstream_x, upstream_y, "s--", label="Upstream HWM")
    hwm_axis.set_xlabel("Distance upstream from creek mouth (river miles)")
    hwm_axis.set_ylabel("Elevation (ft NAVD 88)")
    hwm_axis.set_title("Fourmile Creek high-water marks, 1 July 2018")
    hwm_axis.grid(alpha=0.25)
    hwm_axis.legend()
    hwm_figure.tight_layout()
    hwm_figure.savefig(RESULTS / "observed_high_water_profile.png", dpi=180)
    plt.close(hwm_figure)

    report = {
        "status": "data_audit_completed_simulation_blocked",
        "simulation_blocker": (
            "Current RainFall lacks river-channel geometry and prescribed stage/discharge "
            "boundaries; these observations are not compared to a fabricated simulation."
        ),
        "sites": summaries,
        "high_water_marks": {
            "table_rows": len(hwm_rows),
            "locations_with_elevation": len(surveyed),
            "surveyed_bridge_locations": sum(row["observation_type"] == "surveyed_hwm" for row in surveyed),
            "recorded_stage_locations": sum(
                row["observation_type"] == "recorded_stage_not_surveyed_hwm" for row in surveyed
            ),
            "vertical_datum": "NAVD 88",
            "source": "USGS OFR 2021-1044 Table 3",
        },
        "source": {
            "path": source.relative_to(ROOT).as_posix(),
            "sha256": sha256(source),
            "retrieval_url": (
                "https://waterservices.usgs.gov/nwis/iv/?format=rdb&"
                "sites=05485605,05485640&startDT=2018-06-29&endDT=2018-07-03&"
                "parameterCd=00060,00065&siteStatus=all"
            ),
        },
    }
    (RESULTS / "event_data_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    manifest = [
        {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(RAW.iterdir())
        if path.is_file()
    ]
    (RESULTS / "raw_data_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
