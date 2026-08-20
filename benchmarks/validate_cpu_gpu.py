from __future__ import annotations

import json
import os
from dataclasses import asdict

import numpy as np

from rainfall_ca import MountainFloodCA, SimulationConfig

config = SimulationConfig(
    grid_size=96,
    seed=117,
    rainfall_mm_h=135.0,
    infiltration_mm_h=6.0,
    max_dt_s=0.5,
    open_outlet=False,
)

os.environ["RAINFALL_FORCE_CPU"] = "1"
cpu = MountainFloodCA(config)
os.environ.pop("RAINFALL_FORCE_CPU", None)
gpu = MountainFloodCA(SimulationConfig(**asdict(config)))

cpu.step(60)
gpu.step(60)
gpu_h = gpu._to_numpy(gpu.h)
abs_error = np.abs(cpu.h - gpu_h)

result = {
    "cpu_backend": cpu.backend,
    "gpu_backend": gpu.backend,
    "gpu_device": gpu.device_name,
    "steps": 60,
    "max_abs_depth_difference_m": float(abs_error.max()),
    "mean_abs_depth_difference_m": float(abs_error.mean()),
    "cpu_relative_mass_error": float(cpu.stats()["relative_mass_error"]),
    "gpu_relative_mass_error": float(gpu.stats()["relative_mass_error"]),
}
print(json.dumps(result, ensure_ascii=False, indent=2))
