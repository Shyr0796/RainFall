from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import numpy as np


EXP = Path(__file__).resolve().parents[1]
RAW = EXP / "data" / "raw"
EXTRACTED = EXP / "data" / "extracted"
PROCESSED = EXP / "data" / "processed"
RESULTS = EXP / "results"
for directory in (RAW, EXTRACTED, PROCESSED, RESULTS):
    directory.mkdir(parents=True, exist_ok=True)

archive = RAW / "Benchmarking_Model_Data.zip"
if not archive.exists():
    raise SystemExit(
        "Missing data/raw/Benchmarking_Model_Data.zip. Download it from the URL in data/source.json."
    )

digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(RAW / "Benchmarking_Model_Data.zip.sha256").write_text(
    f"{digest}  {archive.name}\n", encoding="utf-8"
)


def safe_extract(handle: zipfile.ZipFile, destination: Path) -> None:
    base = destination.resolve()
    for member in handle.infolist():
        target = (destination / member.filename).resolve()
        if target != base and base not in target.parents:
            raise ValueError(f"Unsafe archive path: {member.filename}")
    handle.extractall(destination)


with zipfile.ZipFile(archive) as zf:
    safe_extract(zf, EXTRACTED)

# The official outer package is an archive of per-test ZIP files.  Preserve the
# nested ZIPs and extract each one into a same-stem directory for a complete,
# reproducible inventory.
nested_archives = sorted(EXTRACTED.glob("*.zip"))
for nested_archive in nested_archives:
    nested_destination = EXTRACTED / nested_archive.stem
    nested_destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(nested_archive) as nested_zip:
        safe_extract(nested_zip, nested_destination)

inventory: list[dict[str, object]] = []
for path in sorted(p for p in EXTRACTED.rglob("*") if p.is_file()):
    rel = path.relative_to(EXTRACTED).as_posix()
    inventory.append(
        {
            "path": rel,
            "bytes": path.stat().st_size,
            "suffix": path.suffix.lower(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
with (RESULTS / "extracted_inventory.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["path", "bytes", "suffix", "sha256"])
    writer.writeheader()
    writer.writerows(inventory)


def read_numeric_grid(path: Path) -> tuple[np.ndarray, dict[str, float]] | None:
    """Read a simple ESRI ASCII grid, tolerating comma or whitespace rows."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = [fh.readline().strip() for _ in range(6)]
        header: dict[str, float] = {}
        for line in first:
            parts = line.replace(",", " ").split()
            if len(parts) != 2:
                return None
            header[parts[0].lower()] = float(parts[1])
        if "ncols" not in header or "nrows" not in header:
            return None
        data = np.loadtxt(path, skiprows=6)
        if data.shape != (int(header["nrows"]), int(header["ncols"])):
            return None
        return data, header
    except (OSError, ValueError):
        return None


name_counts: dict[str, int] = {}
for item in inventory:
    parts = Path(str(item["path"])).parts
    group = parts[0] if parts else "root"
    name_counts[group] = name_counts.get(group, 0) + 1

candidate_patterns = re.compile(r"dem|dtm|terrain|elev|bed|grid", re.I)
grid_candidates: list[dict[str, object]] = []
for item in inventory:
    path = EXTRACTED / str(item["path"])
    if path.suffix.lower() not in {".asc", ".txt", ".grd", ".csv"}:
        continue
    if not candidate_patterns.search(path.name) and path.suffix.lower() != ".asc":
        continue
    parsed = read_numeric_grid(path)
    if parsed is None:
        continue
    data, header = parsed
    nodata = header.get("nodata_value")
    finite = np.isfinite(data)
    if nodata is not None:
        finite &= data != nodata
    grid_candidates.append(
        {
            "path": path.relative_to(EXTRACTED).as_posix(),
            "shape": list(data.shape),
            "cellsize": header.get("cellsize"),
            "minimum": float(np.min(data[finite])) if np.any(finite) else None,
            "maximum": float(np.max(data[finite])) if np.any(finite) else None,
            "header": header,
        }
    )

# Choose the smallest valid DEM-like grid for a transparent ingestion smoke test.
# This verifies parsing/resampling readiness only; it does not run a changed
# hydraulic benchmark without its prescribed boundary conditions.
adaptation: dict[str, object]
if grid_candidates:
    chosen = min(grid_candidates, key=lambda row: int(row["shape"][0]) * int(row["shape"][1]))
    chosen_path = EXTRACTED / str(chosen["path"])
    dem, header = read_numeric_grid(chosen_path)  # type: ignore[misc]
    nodata = header.get("nodata_value")
    valid = np.isfinite(dem)
    if nodata is not None:
        valid &= dem != nodata
    fill = float(np.median(dem[valid]))
    clean = np.where(valid, dem, fill).astype(np.float32)
    np.save(PROCESSED / "selected_dem.npy", clean)
    (PROCESSED / "selected_dem_metadata.json").write_text(
        json.dumps(
            {
                "source_relative_path": chosen["path"],
                "source_header": header,
                "shape": list(clean.shape),
                "dtype": str(clean.dtype),
                "nodata_replacement": "median of valid cells",
                "purpose": "ingestion smoke test only; no hydraulic result claimed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    adaptation = {
        "status": "INGESTION_READY_CORE_BOUNDARY_UNSUPPORTED",
        "selected_grid": chosen,
        "processed_dem": "data/processed/selected_dem.npy",
        "hydraulic_blocker": (
            "Current MountainFloodCA does not expose the benchmark package's general "
            "time-varying inflow/stage boundary conditions or obstacle masks. Test 1 is "
            "run separately with an explicit experiment-only stage-boundary wrapper; this "
            "does not imply that the core API supports all official tests."
        ),
    }
else:
    adaptation = {
        "status": "NO_SIMPLE_ASCII_DEM_IDENTIFIED",
        "hydraulic_blocker": "No simple ESRI ASCII DEM was identified automatically; inspect proprietary/binary inputs manually.",
    }

report = {
    "experiment": "03_uk_ea_benchmarks",
    "classification": "standard numerical benchmark/model intercomparison; not field observations",
    "archive": {
        "path": archive.relative_to(EXP).as_posix(),
        "bytes": archive.stat().st_size,
        "sha256": digest,
    },
    "inventory": {
        "file_count": len(inventory),
        "total_extracted_bytes": sum(int(item["bytes"]) for item in inventory),
        "nested_archives_extracted": [path.name for path in nested_archives],
        "top_level_counts": name_counts,
        "suffix_counts": {
            suffix: sum(1 for item in inventory if item["suffix"] == suffix)
            for suffix in sorted({str(item["suffix"]) for item in inventory})
        },
    },
    "dem_grid_candidates": grid_candidates,
    "adaptation": adaptation,
}
(RESULTS / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
(RESULTS / "run.log").write_text(
    f"Archive SHA256: {digest}\n"
    f"Extracted files: {len(inventory)}\n"
    f"DEM-like ASCII grids: {len(grid_candidates)}\n"
    f"Adaptation status: {adaptation['status']}\n"
    "Evidence class: standard numerical benchmark, not observations.\n",
    encoding="utf-8",
)
print(json.dumps({"files": len(inventory), "grids": len(grid_candidates), "adaptation": adaptation["status"]}))
