from __future__ import annotations

import json
import statistics
import time
import warnings

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

from fastapi.testclient import TestClient

from rainfall_ca.api import app

latencies_ms = []
payload_sizes = []
with TestClient(app) as client:
    client.post("/api/step", json={"iterations": 16})  # Warm-up.
    for _ in range(20):
        started = time.perf_counter()
        response = client.post("/api/step", json={"iterations": 16})
        response.raise_for_status()
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        payload_sizes.append(len(response.content))

median_ms = statistics.median(latencies_ms)
print(
    json.dumps(
        {
            "grid_size": 192,
            "iterations_per_frame": 16,
            "samples": len(latencies_ms),
            "median_response_ms": median_ms,
            "p95_response_ms": sorted(latencies_ms)[18],
            "median_payload_kib": statistics.median(payload_sizes) / 1024.0,
            "implied_max_fps_excluding_browser_draw": 1000.0 / median_ms,
        },
        ensure_ascii=False,
        indent=2,
    )
)
