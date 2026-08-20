from __future__ import annotations

import json
import os
import statistics

from rainfall_ca import MountainFloodCA, SimulationConfig


def run_case(grid_size: int) -> dict[str, float | int | str]:
    os.environ.pop("RAINFALL_FORCE_CPU", None)
    sim = MountainFloodCA(
        SimulationConfig(grid_size=grid_size, rainfall_mm_h=120.0, max_dt_s=0.8)
    )
    sim.step(4)  # JIT warm-up; excluded from timing.
    rates = []
    for _ in range(5):
        stats = sim.step(32)
        rates.append(float(stats["steps_per_second"]))
    stats = sim.stats()
    return {
        "grid_size": grid_size,
        "cells": grid_size * grid_size,
        "backend": sim.backend,
        "device": sim.device_name,
        "median_steps_per_second": statistics.median(rates),
        "minimum_steps_per_second": min(rates),
        "relative_mass_error": float(stats["relative_mass_error"]),
        "simulated_seconds": float(stats["simulation_time_s"]),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            [run_case(n) for n in (96, 192, 256, 384)], ensure_ascii=False, indent=2
        )
    )
