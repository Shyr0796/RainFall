#!/usr/bin/env python3
"""Run an uncalibrated Ref-configuration boundary/geometry adapter baseline."""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from urban_adapter import Boundary, UrbanLocalInertialAdapter

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "extracted" / "Dataset 2" / "Config_Ref.h5"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if not len(indices):
        return []
    out = []
    start = previous = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value > previous + 1:
            out.append((start, previous)); start = value
        previous = value
    out.append((start, previous))
    return [item for item in out if item[1] - item[0] >= 3]


def block_mean(array: np.ndarray, valid: np.ndarray, factor: int = 2) -> np.ndarray:
    nx = array.shape[0] // factor * factor
    ny = array.shape[1] // factor * factor
    a = array[:nx, :ny].reshape(nx // factor, factor, ny // factor, factor)
    m = valid[:nx, :ny].reshape(nx // factor, factor, ny // factor, factor)
    numerator = np.where(m, a, 0).sum(axis=(1, 3))
    denominator = m.sum(axis=(1, 3))
    return np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0)


def boundary_cells(mask: np.ndarray, edge: str, segment: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    start, end = segment
    if edge == "left": return np.zeros(end-start+1, int), np.arange(start, end+1)
    if edge == "right": return np.full(end-start+1, mask.shape[0]-1, int), np.arange(start, end+1)
    if edge == "bottom": return np.arange(start, end+1), np.zeros(end-start+1, int)
    return np.arange(start, end+1), np.full(end-start+1, mask.shape[1]-1, int)


def main(duration_s: float = 20.0) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True); LOGS.mkdir(parents=True, exist_ok=True)
    with h5py.File(INPUT) as h5:
        g = h5["Ref"]
        obs_v = g["V"][()]; obs_u = g["Vx"][()]; obs_w = g["Vy"][()]
        scalars = {name: float(g[name][()].reshape(-1)[0]) for name in
                   ("QA","QB","QC","Q1","Q2","Q3","hA","hB","hC","h1","h2","h3")}
    valid = np.isfinite(obs_v) & np.isfinite(obs_u) & np.isfinite(obs_w) & (obs_v > 0)
    factor = 2
    mask = block_mean(np.ones_like(obs_v), valid, factor) > 0.25
    u_obs = block_mean(obs_u, valid, factor); v_obs = block_mean(obs_w, valid, factor)
    speed_obs = np.hypot(u_obs, v_obs)

    left, right = runs(mask[0, :]), runs(mask[-1, :])
    bottom, top = runs(mask[:, 0]), runs(mask[:, -1])
    if not (len(left)==2 and len(bottom)==1 and len(right)==1 and len(top)==2):
        raise RuntimeError(f"unexpected six-opening geometry: {left=}, {bottom=}, {right=}, {top=}")
    # HDF axis 1 follows the paper's y coordinate, which increases from the top
    # of Fig. 3c downward.  Therefore array y=0 is inlet A and array y=max holds
    # outlets 1/2.  The earlier smoke run had these two edges reversed.
    inflows = [
        Boundary("B_left_upper", boundary_cells(mask,"left",left[0]), scalars["QB"]/3600),
        Boundary("C_left_lower", boundary_cells(mask,"left",left[1]), scalars["QC"]/3600),
        Boundary("A_y0", boundary_cells(mask,"bottom",bottom[0]), scalars["QA"]/3600),
    ]
    stages = [
        Boundary("3_right", boundary_cells(mask,"right",right[0]), scalars["h3"]),
        Boundary("1_ymax_left", boundary_cells(mask,"top",top[0]), scalars["h1"]),
        Boundary("2_ymax_right", boundary_cells(mask,"top",top[1]), scalars["h2"]),
    ]
    solver = UrbanLocalInertialAdapter(mask, dx=0.02, manning_n=0.010,
                                       inflows=inflows, stages=stages,
                                       initial_depth_m=np.mean([scalars["h1"],scalars["h2"],scalars["h3"]]))
    started = time.perf_counter(); steps = 0
    snapshots = []
    while solver.time_s < duration_s:
        solver.step(); steps += 1
        if steps % 1000 == 0: snapshots.append((solver.time_s, float(solver.h.max())))
    runtime = time.perf_counter() - started
    u, v, speed = solver.velocity()
    compare = mask & (speed_obs > 0) & np.isfinite(speed_obs)
    diff_angle = np.arctan2(np.sin(np.arctan2(v, u)-np.arctan2(v_obs,u_obs)),
                            np.cos(np.arctan2(v, u)-np.arctan2(v_obs,u_obs)))
    metrics = {
        "status": "EXECUTED_DIAGNOSTIC_BASELINE_NOT_FORMAL_VALIDATION",
        "config": "Ref", "duration_s": solver.time_s, "steps": steps,
        "runtime_s": runtime, "grid_shape": list(mask.shape), "dx_m": solver.dx,
        "manning_n_uncalibrated": solver.n, "comparison_cells": int(compare.sum()),
        "speed_rmse_m_s_surface_vs_depth_average": float(np.sqrt(np.mean((speed[compare]-speed_obs[compare])**2))),
        "speed_mae_m_s_surface_vs_depth_average": float(np.mean(np.abs(speed[compare]-speed_obs[compare]))),
        "direction_mae_deg_where_both_speed_gt_0p02": None,
        "storage_m3": float(solver.h.sum()*solver.dx**2),
        "inflow_volume_m3": solver.inflow_volume_m3,
        "stage_outflow_volume_m3": solver.stage_outflow_volume_m3,
        "stage_inflow_volume_m3": solver.stage_inflow_volume_m3,
        "stage_outflow_by_name_m3": solver.stage_outflow_by_name_m3,
        "stage_inflow_by_name_m3": solver.stage_inflow_by_name_m3,
        "mass_error_m3": solver.mass_error_m3(),
        "mass_error_fraction_of_inflow": abs(solver.mass_error_m3())/solver.inflow_volume_m3,
        "cautions": [
            "20 s is a computational smoke baseline, not demonstrated steady-state convergence.",
            "Geometry mask is derived from non-zero processed LSPIV cells and downsampled to 2 cm.",
            "Observed velocity is surface velocity; simulated velocity is depth averaged.",
            "No calibration, turbulence model, or surface-to-depth velocity observation operator was applied.",
            "Boundary placement was cross-checked against Li et al. Fig. 3c; HDF y=0 is the physical top inlet A.",
        ],
    }
    angle_mask = compare & (speed > 0.02) & (speed_obs > 0.02)
    if angle_mask.any():
        metrics["direction_mae_deg_where_both_speed_gt_0p02"] = float(np.degrees(np.mean(np.abs(diff_angle[angle_mask]))))
        metrics["direction_cells"] = int(angle_mask.sum())
    (RESULTS/"ref_baseline_metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    with (RESULTS/"ref_baseline_snapshots.csv").open("w",newline="") as f:
        writer=csv.writer(f); writer.writerow(["simulation_time_s","max_depth_m"]); writer.writerows(snapshots)
    np.savez_compressed(RESULTS/"ref_baseline_fields.npz", depth=solver.h,u=u,v=v,speed=speed,
                        obs_u=u_obs,obs_v=v_obs,obs_speed=speed_obs,mask=mask)
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),constrained_layout=True)
    for ax,a,title in zip(axes,(speed_obs,speed,speed-speed_obs),
                          ("Observed LSPIV surface speed","RainFall-adapter depth-average speed","Model - observation (non-equivalent)")):
        im=ax.imshow(np.where(mask,a,np.nan).T,origin="lower",cmap="coolwarm" if "Model -" in title else "turbo",
                     extent=(0,mask.shape[0]*.02,0,mask.shape[1]*.02))
        ax.set_title(title); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); fig.colorbar(im,ax=ax)
    fig.savefig(RESULTS/"ref_baseline_comparison.png",dpi=170); plt.close(fig)
    (LOGS/"ref_baseline.log").write_text(json.dumps({"metrics":metrics,"snapshots":snapshots},indent=2),encoding="utf-8")
    print(json.dumps(metrics,indent=2))


if __name__ == "__main__":
    main()
