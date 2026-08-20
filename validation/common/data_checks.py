"""Reproducibility helpers for downloaded and generated validation artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: str | Path) -> list[dict[str, object]]:
    base = Path(root)
    records: list[dict[str, object]] = []
    if not base.exists():
        return records
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        records.append(
            {
                "path": path.relative_to(base).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def write_inventory(root: str | Path, destination: str | Path) -> None:
    Path(destination).write_text(
        json.dumps(inventory(root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_nonempty(paths: Iterable[str | Path]) -> None:
    missing = [str(path) for path in paths if not Path(path).is_file() or Path(path).stat().st_size == 0]
    if missing:
        raise ValueError(f"missing or empty files: {missing}")

