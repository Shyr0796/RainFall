from __future__ import annotations

import json
import os
from dataclasses import asdict

import numpy as np

from rainfall_ca import MountainFloodCA, SimulationConfig

os.environ.pop("RAINFALL_FORCE_CPU", None)
base = SimulationConfig(
    grid_size=96,
    seed=86,
    rainfall_mm_h=120.0,
    rain_duration_min=5.0,
    infiltration_mm_h=4.0,
    open_outlet=False,
    cfl=0.35,
)
target_time_s = 600.0


def run(max_dt_s: float) -> tuple[np.ndarray, dict]:
    config = SimulationConfig(**asdict(base))
    config.max_dt_s = max_dt_s
    sim = MountainFloodCA(config)
    while sim.time_s < target_time_s - 1e-9:
        sim.config.max_dt_s = min(max_dt_s, target_time_s - sim.time_s)
        sim.step(1)
    return sim._to_numpy(sim.h), sim.stats()


results = {}
fields = {}
for max_dt in (1.0, 0.5, 0.25):
    field, stats = run(max_dt)
    fields[max_dt] = field
    results[str(max_dt)] = {
        "steps": stats["steps"],
        "storage_m3": stats["storage_m3"],
        "max_depth_m": stats["max_depth_m"],
        "relative_mass_error": stats["relative_mass_error"],
    }

reference = fields[0.25]
for max_dt in (1.0, 0.5):
    difference = fields[max_dt] - reference
    results[str(max_dt)]["depth_rmse_vs_0.25s_m"] = float(
        np.sqrt(np.mean(difference**2))
    )
    results[str(max_dt)]["max_abs_depth_difference_vs_0.25s_m"] = float(
        np.max(np.abs(difference))
    )

print(
    json.dumps(
        {
            "backend": "cuda",
            "target_time_s": target_time_s,
            "results_by_max_dt_s": results,
        },
        ensure_ascii=False,
        indent=2,
    )
)
