#!/usr/bin/env python3
"""Calibration/blind-test protocol for the Li et al. urban-flume dataset.

The adapter is experimental.  Results are explicitly diagnostic until its
boundary and building-mask capabilities are integrated into the production
RainFall engine and all five blind configurations pass the geometry gate.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
LEGACY = REPO / "validation" / "experiments" / "05_urban_lspiv"
DATA = LEGACY / "data" / "extracted" / "Dataset 2"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"
sys.path.insert(0, str(LEGACY / "code"))
from urban_adapter import Boundary, UrbanLocalInertialAdapter  # noqa: E402


CALIBRATION = ("CO", "CE", "Ref")
BLIND = ("Px5", "Py5", "BU", "BS", "BD")
N_CANDIDATES = (0.008, 0.010, 0.012, 0.015, 0.020)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    out = []
    start = previous = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value > previous + 1:
            out.append((start, previous))
            start = value
        previous = value
    out.append((start, previous))
    return [item for item in out if item[1] - item[0] >= 3]


def block_mean(array: np.ndarray, valid: np.ndarray, factor: int) -> np.ndarray:
    nx = array.shape[0] // factor * factor
    ny = array.shape[1] // factor * factor
    a = array[:nx, :ny].reshape(nx // factor, factor, ny // factor, factor)
    m = valid[:nx, :ny].reshape(nx // factor, factor, ny // factor, factor)
    numerator = np.where(m, a, 0).sum(axis=(1, 3))
    denominator = m.sum(axis=(1, 3))
    return np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0)


def boundary_cells(mask: np.ndarray, edge: str, segment: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    start, end = segment
    if edge == "left":
        return np.zeros(end - start + 1, int), np.arange(start, end + 1)
    if edge == "right":
        return np.full(end - start + 1, mask.shape[0] - 1, int), np.arange(start, end + 1)
    if edge == "y0":
        return np.arange(start, end + 1), np.zeros(end - start + 1, int)
    return np.arange(start, end + 1), np.full(end - start + 1, mask.shape[1] - 1, int)


def load_case(config: str, factor: int) -> dict[str, object]:
    with h5py.File(DATA / f"Config_{config}.h5") as h5:
        group = h5[config]
        obs_speed = group["V"][()]
        obs_u = group["Vx"][()]
        obs_v = group["Vy"][()]
        scalars = {
            key: float(group[key][()].reshape(-1)[0])
            for key in ("QA", "QB", "QC", "Q1", "Q2", "Q3", "hA", "hB", "hC", "h1", "h2", "h3")
        }
    valid = np.isfinite(obs_speed) & np.isfinite(obs_u) & np.isfinite(obs_v) & (obs_speed > 0)
    mask = block_mean(np.ones_like(obs_speed), valid, factor) > 0.25
    u = block_mean(obs_u, valid, factor)
    v = block_mean(obs_v, valid, factor)
    speed = np.hypot(u, v)
    left = runs(mask[0, :])
    right = runs(mask[-1, :])
    y0 = runs(mask[:, 0])
    ymax = runs(mask[:, -1])
    gate = {
        "left_segments": left,
        "right_segments": right,
        "y0_segments": y0,
        "ymax_segments": ymax,
        "pass": len(left) == 2 and len(right) == 1 and len(y0) == 1 and len(ymax) == 2,
    }
    return {"mask": mask, "obs_u": u, "obs_v": v, "obs_speed": speed, "scalars": scalars, "gate": gate}


def run_case(config: str, n: float, factor: int = 2, duration_s: float = 30.0) -> dict[str, object]:
    case = load_case(config, factor)
    mask = case["mask"]
    gate = case["gate"]
    if not gate["pass"]:
        return {
            "config": config,
            "manning_n": n,
            "factor": factor,
            "status": "BLOCKED_GEOMETRY_GATE",
            "geometry_gate": gate,
        }
    scalars = case["scalars"]
    left, right = gate["left_segments"], gate["right_segments"]
    y0, ymax = gate["y0_segments"], gate["ymax_segments"]
    inflows = [
        Boundary("B", boundary_cells(mask, "left", left[0]), scalars["QB"] / 3600),
        Boundary("C", boundary_cells(mask, "left", left[1]), scalars["QC"] / 3600),
        Boundary("A", boundary_cells(mask, "y0", y0[0]), scalars["QA"] / 3600),
    ]
    stages = [
        Boundary("3", boundary_cells(mask, "right", right[0]), scalars["h3"]),
        Boundary("1", boundary_cells(mask, "ymax", ymax[0]), scalars["h1"]),
        Boundary("2", boundary_cells(mask, "ymax", ymax[1]), scalars["h2"]),
    ]
    solver = UrbanLocalInertialAdapter(
        mask,
        dx=0.01 * factor,
        manning_n=n,
        inflows=inflows,
        stages=stages,
        initial_depth_m=np.mean([scalars["h1"], scalars["h2"], scalars["h3"]]),
    )
    history = []
    next_sample = 1.0
    start = time.perf_counter()
    steps = 0
    while solver.time_s < duration_s:
        solver.step()
        steps += 1
        if solver.time_s >= next_sample:
            history.append(
                {
                    "time_s": solver.time_s,
                    "mean_depth_m": float(solver.h[mask].mean()),
                    **{f"out_{name}_m3": value for name, value in solver.stage_outflow_by_name_m3.items()},
                }
            )
            next_sample += 1.0
    runtime = time.perf_counter() - start
    u, v, speed = solver.velocity()
    obs_u, obs_v, obs_speed = case["obs_u"], case["obs_v"], case["obs_speed"]
    compare = mask & np.isfinite(obs_speed) & (obs_speed > 0)
    angle_mask = compare & (speed > 0.02) & (obs_speed > 0.02)
    delta_angle = np.arctan2(
        np.sin(np.arctan2(v, u) - np.arctan2(obs_v, obs_u)),
        np.cos(np.arctan2(v, u) - np.arctan2(obs_v, obs_u)),
    )

    last = pd.DataFrame(history).tail(11)
    elapsed = float(last["time_s"].iloc[-1] - last["time_s"].iloc[0])
    q_sim = np.array(
        [
            (last[f"out_{label}_m3"].iloc[-1] - last[f"out_{label}_m3"].iloc[0]) / elapsed
            for label in ("1", "2", "3")
        ]
    )
    q_obs = np.array([scalars[f"Q{i}"] / 3600 for i in (1, 2, 3)])
    p_sim = q_sim / max(q_sim.sum(), 1e-12)
    p_obs = q_obs / q_obs.sum()
    inlet_sim = np.array(
        [
            np.median(solver.h[inflows[0].cells]),
            np.median(solver.h[inflows[1].cells]),
            np.median(solver.h[inflows[2].cells]),
        ]
    )
    inlet_obs = np.array([scalars["hB"], scalars["hC"], scalars["hA"]])
    return {
        "config": config,
        "manning_n": n,
        "factor": factor,
        "dx_m": 0.01 * factor,
        "status": "EXECUTED_EXPERIMENTAL_ADAPTER",
        "geometry_gate": gate,
        "duration_s": solver.time_s,
        "steps": steps,
        "runtime_s": runtime,
        "mass_error_fraction": abs(solver.mass_error_m3()) / max(solver.inflow_volume_m3, 1e-12),
        "inlet_depth_mae_m_approx_operator": float(np.mean(np.abs(inlet_sim - inlet_obs))),
        "outlet_partition_total_variation": float(0.5 * np.sum(np.abs(p_sim - p_obs))),
        "observed_outlet_partition": p_obs.tolist(),
        "simulated_outlet_partition": p_sim.tolist(),
        "direction_mae_deg": float(np.degrees(np.mean(np.abs(delta_angle[angle_mask])))) if angle_mask.any() else None,
        "direction_cells": int(angle_mask.sum()),
        "speed_cells": int(compare.sum()),
        "speed_cross_sim_sim": float(np.sum(speed[compare] ** 2)),
        "speed_cross_sim_obs": float(np.sum(speed[compare] * obs_speed[compare])),
        "speed_obs_squared": float(np.sum(obs_speed[compare] ** 2)),
        "mean_depth_final_m": float(solver.h[mask].mean()),
        "mean_depth_last10s_range_m": float(last["mean_depth_m"].max() - last["mean_depth_m"].min()),
    }


def add_speed_metrics(row: dict[str, object], alpha: float) -> None:
    n = row["speed_cells"]
    sse = alpha**2 * row["speed_cross_sim_sim"] - 2 * alpha * row["speed_cross_sim_obs"] + row["speed_obs_squared"]
    row["surface_operator_alpha_calibration_only"] = alpha
    row["surface_speed_rmse_m_s"] = float(np.sqrt(max(sse, 0) / n))


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    calibration_rows = []
    for n in N_CANDIDATES:
        for config in CALIBRATION:
            row = run_case(config, n)
            calibration_rows.append(row)
            print(f"calibration {config=} {n=} status={row['status']}", flush=True)
    calibration = pd.DataFrame(calibration_rows)
    calibration["objective"] = (
        calibration["inlet_depth_mae_m_approx_operator"] / 0.002
        + calibration["outlet_partition_total_variation"] / 0.05
    )
    by_n = calibration.groupby("manning_n", as_index=False)["objective"].mean()
    selected_n = float(by_n.loc[by_n["objective"].idxmin(), "manning_n"])
    selected_calibration = [x for x in calibration_rows if x["manning_n"] == selected_n]
    alpha = sum(x["speed_cross_sim_obs"] for x in selected_calibration) / sum(
        x["speed_cross_sim_sim"] for x in selected_calibration
    )
    for row in calibration_rows:
        add_speed_metrics(row, alpha)

    blind_rows = []
    for config in BLIND:
        row = run_case(config, selected_n)
        if row["status"].startswith("EXECUTED"):
            add_speed_metrics(row, alpha)
        blind_rows.append(row)
        print(f"blind {config=} status={row['status']}", flush=True)

    grid_rows = []
    for factor in (1, 2, 4):
        row = run_case("Ref", selected_n, factor=factor)
        if row["status"].startswith("EXECUTED"):
            add_speed_metrics(row, alpha)
        grid_rows.append(row)
        print(f"grid Ref factor={factor} status={row['status']}", flush=True)

    pd.DataFrame(calibration_rows).drop(columns=["geometry_gate"]).to_csv(
        RESULTS / "calibration_runs.csv", index=False
    )
    pd.DataFrame(blind_rows).drop(columns=["geometry_gate"]).to_csv(
        RESULTS / "blind_runs.csv", index=False
    )
    pd.DataFrame(grid_rows).drop(columns=["geometry_gate"]).to_csv(
        RESULTS / "grid_sensitivity.csv", index=False
    )
    geometry = {config: load_case(config, 2)["gate"] for config in CALIBRATION + BLIND}
    (RESULTS / "geometry_gate.json").write_text(json.dumps(geometry, indent=2) + "\n", encoding="utf-8")

    executed_blind = [x for x in blind_rows if x["status"].startswith("EXECUTED")]
    summary = {
        "status": "PARTIAL_BLIND_PROTOCOL_EXECUTED_NOT_FORMAL_VALIDATION",
        "calibration_configs": list(CALIBRATION),
        "blind_configs_planned": list(BLIND),
        "blind_configs_executed": [x["config"] for x in executed_blind],
        "blind_configs_blocked": [x["config"] for x in blind_rows if not x["status"].startswith("EXECUTED")],
        "selected_manning_n": selected_n,
        "surface_to_depth_average_operator_alpha": alpha,
        "selection_objective": "mean(depth_MAE/0.002 + outlet_partition_TV/0.05) over CO, CE, Ref",
        "blind_aggregate": {
            "inlet_depth_mae_m_mean": float(np.mean([x["inlet_depth_mae_m_approx_operator"] for x in executed_blind])),
            "outlet_partition_total_variation_mean": float(np.mean([x["outlet_partition_total_variation"] for x in executed_blind])),
            "surface_speed_rmse_m_s_mean": float(np.mean([x["surface_speed_rmse_m_s"] for x in executed_blind])),
            "direction_mae_deg_mean": float(np.mean([x["direction_mae_deg"] for x in executed_blind])),
            "mass_error_fraction_max": float(np.max([x["mass_error_fraction"] for x in executed_blind])),
            "mean_depth_last10s_range_m_max": float(np.max([x["mean_depth_last10s_range_m"] for x in executed_blind])),
        },
        "pre_registered_threshold_checks": {
            "inlet_depth_mae_le_0p002_m": float(np.mean([x["inlet_depth_mae_m_approx_operator"] for x in executed_blind])) <= 0.002,
            "outlet_partition_tv_le_0p05": float(np.mean([x["outlet_partition_total_variation"] for x in executed_blind])) <= 0.05,
            "direction_mae_le_20_deg": float(np.mean([x["direction_mae_deg"] for x in executed_blind])) <= 20.0,
            "last10s_depth_range_le_0p0005_m": float(np.max([x["mean_depth_last10s_range_m"] for x in executed_blind])) <= 0.0005,
            "mass_error_fraction_le_1e_4": float(np.max([x["mass_error_fraction"] for x in executed_blind])) <= 1e-4,
        },
        "formal_claim_gate": {
            "pass": False,
            "reasons": [
                "BD cannot be reconstructed from non-zero LSPIV cells at outlet 2, so the fifth blind geometry was not run.",
                "Inlet depth is sampled at the computational opening rather than the exact ultrasonic gauge coordinate.",
                "The surface/depth-average velocity operator was calibrated empirically and requires uncertainty analysis.",
                "The adapter is experiment-local and not yet the production RainFall solver.",
                "The four executed blind configurations fail the depth, outlet-partition, direction and steady-state thresholds; only mass conservation passes.",
                "The selected Manning value lies at the upper edge of the search range, indicating unresolved calibration identifiability.",
            ],
        },
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    status = {
        "experiment": "07_urban_flume_blind",
        "status": summary["status"],
        "calibration_executed": True,
        "blind_executed": True,
        "formal_validation_complete": False,
        "blocked_geometry": summary["blind_configs_blocked"],
    }
    (RESULTS / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    blind_frame = pd.DataFrame(executed_blind)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.1))
    axes[0].bar(blind_frame["config"], blind_frame["inlet_depth_mae_m_approx_operator"] * 1000)
    axes[0].axhline(2, color="crimson", ls="--", lw=1, label="2 mm target")
    axes[0].set_ylabel("Inlet depth MAE (mm)")
    axes[1].bar(blind_frame["config"], blind_frame["outlet_partition_total_variation"])
    axes[1].axhline(0.05, color="crimson", ls="--", lw=1)
    axes[1].set_ylabel("Outlet partition TV")
    axes[2].bar(blind_frame["config"], blind_frame["direction_mae_deg"])
    axes[2].axhline(20, color="crimson", ls="--", lw=1)
    axes[2].set_ylabel("Velocity direction MAE (degrees)")
    for ax in axes:
        ax.set_xlabel("Blind urban form")
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Experimental RainFall adapter: locked-parameter blind diagnostics")
    fig.tight_layout()
    fig.savefig(RESULTS / "blind_metrics.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
