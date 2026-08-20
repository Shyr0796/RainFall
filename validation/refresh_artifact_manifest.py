#!/usr/bin/env python3
"""Create a checksum inventory for all validation inputs and outputs."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def role(path: Path) -> str:
    parts = set(path.parts)
    if "raw" in parts:
        return "raw_input"
    if "processed" in parts:
        return "processed_input"
    if "results" in parts:
        return "result"
    if "logs" in parts:
        return "log"
    if "code" in parts:
        return "code"
    return "documentation"


def main() -> None:
    rows = []
    for collection in ("experiments", "advanced"):
        for path in sorted((ROOT / collection).rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            rows.append(
                {
                    "experiment": path.relative_to(ROOT / collection).parts[0],
                    "role": role(path),
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    destination = ROOT / "artifact_manifest.csv"
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["experiment", "role", "path", "bytes", "sha256"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{destination}: {len(rows)} files")


if __name__ == "__main__":
    main()
