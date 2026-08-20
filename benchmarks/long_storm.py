from __future__ import annotations

import json
import math
import os

from rainfall_ca import MountainFloodCA, SimulationConfig

os.environ.pop("RAINFALL_FORCE_CPU", None)
sim = MountainFloodCA(
    SimulationConfig(
        grid_size=192,
        seed=42,
        rainfall_mm_h=200.0,
        rain_duration_min=30.0,
        infiltration_mm_h=0.0,
        max_dt_s=1.5,
        open_outlet=True,
    )
)

snapshots = []
next_snapshot_s = 1800.0
storm_end_s = 1800.0
end_s = 14400.0

while sim.time_s < end_s:
    remaining_s = end_s - sim.time_s
    if remaining_s < sim.config.max_dt_s * 64:
        sim.config.max_dt_s = min(1.5, remaining_s)
        sim.step(1)
    else:
        sim.step(64)
    if sim.time_s >= next_snapshot_s:
        stats = sim.stats()
        snapshots.append(
            {
                "time_s": stats["simulation_time_s"],
                "max_depth_m": stats["max_depth_m"],
                "max_speed_m_s": stats["max_speed_m_s"],
                "storage_m3": stats["storage_m3"],
                "outflow_m3": stats["outflow_m3"],
                "relative_mass_error": stats["relative_mass_error"],
            }
        )
        next_snapshot_s += 1800.0

final = sim.stats()
assert math.isfinite(float(final["max_depth_m"]))
assert math.isfinite(float(final["max_speed_m_s"]))
assert float(final["relative_mass_error"]) < 1e-4
assert float(final["outflow_m3"]) > 0.0
assert snapshots[-1]["storage_m3"] < snapshots[1]["storage_m3"]

print(
    json.dumps(
        {
            "backend": sim.backend,
            "device": sim.device_name,
            "storm_duration_s": storm_end_s,
            "total_duration_s": end_s,
            "snapshots": snapshots,
            "final": final,
            "checks": {
                "finite": True,
                "mass_error_below_1e-4": True,
                "outlet_volume_m3": final["outflow_m3"],
                "storage_receded_after_rain": True,
            },
        },
        ensure_ascii=False,
        indent=2,
    )
)
