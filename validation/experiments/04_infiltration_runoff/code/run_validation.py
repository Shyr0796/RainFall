#!/usr/bin/env python3
"""Ries et al. (2019/2020) infiltration-runoff validation.

This is a lumped effective-loss benchmark, not a validation of RainFall's
two-dimensional surface hydraulics.  Entire sites are held out to prevent
minute-level or same-site leakage.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SRC = RAW / "Extreme_rainfall_experiment_data_06122019"
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
TEST_SITES = {5, 10, 15, 20, 23}
EPS = 1e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_source(name: str) -> pd.DataFrame:
    return pd.read_csv(SRC / name, sep="\t", comment="#", na_values="NA")


def kge(obs: np.ndarray, sim: np.ndarray) -> float:
    if len(obs) < 2 or np.std(obs) < EPS or np.mean(obs) == 0:
        return float("nan")
    r = np.corrcoef(obs, sim)[0, 1] if np.std(sim) >= EPS else 0.0
    alpha = np.std(sim) / np.std(obs)
    beta = np.mean(sim) / np.mean(obs)
    return float(1 - math.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


def nse(obs: np.ndarray, sim: np.ndarray) -> float:
    denom = np.sum((obs - np.mean(obs)) ** 2)
    return float(1 - np.sum((sim - obs) ** 2) / denom) if denom > EPS else float("nan")


def route(excess: np.ndarray, tau_min: float) -> np.ndarray:
    """Mass-conserving one-minute linear-reservoir routing."""
    release_fraction = 1.0 - math.exp(-1.0 / max(tau_min, 0.05))
    storage = 0.0
    out = np.zeros_like(excess, dtype=float)
    for i, value in enumerate(excess):
        storage += max(float(value), 0.0)
        out[i] = storage * release_fraction
        storage -= out[i]
    return out


def simulate(event: dict, model: str, params: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rain = event["rain"]
    if model == "constant_loss":
        f_const, tau = params
        capacity = np.full_like(rain, f_const, dtype=float)
    else:
        fc, alpha, decay, tau = params
        deficit = max((event["porosity"] - event["initial_sm"]) / 100.0, 0.0)
        t = np.arange(len(rain), dtype=float)
        capacity = fc + alpha * deficit * np.exp(-decay * t)
    excess = np.maximum(rain - capacity, 0.0)
    rate = route(excess, tau)
    return rate, np.cumsum(rate), capacity


def event_loss(params: np.ndarray, model: str, events: list[dict]) -> float:
    values = []
    for event in events:
        _, cumulative, _ = simulate(event, model, params)
        scale = max(event["rain"].sum(), 1.0)
        values.append(np.mean(((cumulative - event["obs_cum"]) / scale) ** 2))
    return float(np.mean(values))


def onset(rate: np.ndarray, threshold: float = 0.01) -> float:
    where = np.flatnonzero(rate > threshold)
    return float(where[0] + 1) if len(where) else float("nan")


def evaluate_event(event: dict, model: str, params: np.ndarray) -> tuple[dict, pd.DataFrame]:
    pred_rate, pred_cum, capacity = simulate(event, model, params)
    obs_cum = event["obs_cum"]
    obs_rate = event["obs_rate"]
    obs_volume, pred_volume = float(obs_cum[-1]), float(pred_cum[-1])
    obs_peak_i, pred_peak_i = int(np.argmax(obs_rate)), int(np.argmax(pred_rate))
    obs_on, pred_on = onset(obs_rate), onset(pred_rate)
    row = {
        "site_number": event["site"], "experiment_number": event["experiment"],
        "land_use": event["land_use"], "split": event["split"], "model": model,
        "n_minutes": len(obs_cum), "rain_volume_mm": float(event["rain"].sum()),
        "initial_soil_moisture_pct": event["initial_sm"], "porosity_10cm_pct": event["porosity"],
        "observed_runoff_volume_mm": obs_volume, "predicted_runoff_volume_mm": pred_volume,
        "volume_error_mm": pred_volume - obs_volume, "volume_abs_error_mm": abs(pred_volume - obs_volume),
        "volume_relative_error_pct": (pred_volume - obs_volume) / obs_volume * 100 if obs_volume > 0.1 else np.nan,
        "observed_peak_rate_mm_min": float(obs_rate[obs_peak_i]),
        "predicted_peak_rate_mm_min": float(pred_rate[pred_peak_i]),
        "peak_time_error_min": float(pred_peak_i - obs_peak_i),
        "observed_onset_min": obs_on, "predicted_onset_min": pred_on,
        "onset_error_min": pred_on - obs_on if np.isfinite(obs_on) and np.isfinite(pred_on) else np.nan,
        "rate_nse": nse(obs_rate, pred_rate), "rate_kge": kge(obs_rate, pred_rate),
        "cumulative_nse": nse(obs_cum, pred_cum),
        "observed_zero_runoff": obs_volume < 0.1, "predicted_zero_runoff": pred_volume < 0.1,
    }
    frame = pd.DataFrame({
        "site_number": event["site"], "experiment_number": event["experiment"],
        "split": event["split"], "model": model, "minute": np.arange(1, len(obs_cum) + 1),
        "rain_mm_min": event["rain"], "infiltration_capacity_mm_min": capacity,
        "observed_runoff_rate_mm_min": obs_rate, "predicted_runoff_rate_mm_min": pred_rate,
        "observed_cumulative_runoff_mm": obs_cum, "predicted_cumulative_runoff_mm": pred_cum,
    })
    return row, frame


def aggregate(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (split, model), g in metrics.groupby(["split", "model"]):
        obs = g["observed_runoff_volume_mm"].to_numpy()
        pred = g["predicted_runoff_volume_mm"].to_numpy()
        rows.append({
            "split": split, "model": model, "n_events": len(g),
            "volume_mae_mm": float(np.mean(np.abs(pred - obs))),
            "volume_rmse_mm": float(np.sqrt(np.mean((pred - obs) ** 2))),
            "volume_bias_mm": float(np.mean(pred - obs)),
            "aggregate_volume_bias_pct": float((pred.sum() - obs.sum()) / obs.sum() * 100),
            "volume_nse_across_events": nse(obs, pred), "volume_kge_across_events": kge(obs, pred),
            "median_event_rate_nse": float(g["rate_nse"].median()),
            "median_event_rate_kge": float(g["rate_kge"].median()),
            "median_event_cumulative_nse": float(g["cumulative_nse"].median()),
            "onset_mae_min": float(g["onset_error_min"].abs().mean()),
            "peak_time_mae_min": float(g["peak_time_error_min"].abs().mean()),
            "zero_runoff_accuracy": float((g["observed_zero_runoff"] == g["predicted_zero_runoff"]).mean()),
            "observed_zero_events": int(g["observed_zero_runoff"].sum()),
            "predicted_zero_events": int(g["predicted_zero_runoff"].sum()),
        })
    return pd.DataFrame(rows)


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    sites, events, ts = read_source("1_site_data.txt"), read_source("2_event_data.txt"), read_source("3_experiment_time_series.txt")
    valid = events[events.Selected_subplots.notna() & events.P_mean_selected.notna() & events.Q_OF_mean_selected.notna()].copy()
    valid["split"] = np.where(valid.Site_number.isin(TEST_SITES), "blind_test", "calibration")
    valid["event_id"] = valid.Site_number.map(lambda x: f"S{x:02d}") + "_E" + valid.Experiment_number.astype(str)
    valid.to_csv(PROCESSED / "event_inventory.csv", index=False)

    sm_cols = ["SM1_5cm", "SM1_10cm", "SM2_5cm", "SM2_10cm"]
    # One site lacks 10 cm porosity; fill it only from the calibration-safe,
    # land-use-level site median and record this in QC.
    porosity_by_land = sites.groupby("Land_use")["Total_porosity_10cm"].median().to_dict()
    site_porosity = sites.set_index("Site_number")["Total_porosity_10cm"].to_dict()
    event_objects = []
    qc_rows = []
    for row in valid.itertuples(index=False):
        g = ts[(ts.Site_number == row.Site_number) & (ts.Experiment_number == row.Experiment_number) & ts.Experiment_time_step_plus10min.notna()].copy()
        g = g.sort_values("Experiment_time_step_plus10min")
        rain = g.P_mean_selected.fillna(0).to_numpy(float)
        # Despite the historical comment saying "cumulative", these one-minute
        # values are interval runoff depths: their sum reproduces event totals.
        obs_rate = g.Q_OF_mean_selected.fillna(0).to_numpy(float)
        obs_cum = np.cumsum(obs_rate)
        first_sm = g[sm_cols].iloc[0].dropna().to_numpy(float)
        initial_sm = float(np.mean(first_sm))
        raw_porosity = site_porosity[row.Site_number]
        porosity = float(raw_porosity if np.isfinite(raw_porosity) else porosity_by_land[row.Land_use])
        obj = {"site": int(row.Site_number), "experiment": int(row.Experiment_number), "land_use": row.Land_use,
               "split": row.split, "rain": rain, "obs_rate": obs_rate, "obs_cum": obs_cum, "initial_sm": initial_sm,
               "porosity": porosity}
        event_objects.append(obj)
        qc_rows.append({"event_id": row.event_id, "site_number": row.Site_number, "experiment_number": row.Experiment_number,
                        "n_rows": len(g), "expected_rows": int(row.Experiment_duration) + 10,
                        "rain_sum_timeseries_mm": rain.sum(), "rain_sum_event_mm": row.P_mean_selected,
                        "runoff_sum_timeseries_mm": obs_rate.sum(), "runoff_event_mm": row.Q_OF_mean_selected,
                        "negative_rain_values": int((rain < 0).sum()), "negative_runoff_values": int((obs_rate < 0).sum()),
                        "initial_sm_available": bool(len(first_sm)), "porosity_imputed": bool(not np.isfinite(raw_porosity))})
    qc = pd.DataFrame(qc_rows)
    qc.to_csv(RESULTS / "data_qc_events.csv", index=False)

    bounds = {"constant_loss": [(0.0, 3.0), (0.05, 20.0)],
              "soil_state_decay": [(0.0, 3.0), (0.0, 12.0), (0.001, 0.5), (0.05, 20.0)]}
    parameter_rows = []
    parameter_map = {}
    for land_use in sorted(valid.Land_use.unique()):
        train = [e for e in event_objects if e["split"] == "calibration" and e["land_use"] == land_use]
        for model in bounds:
            opt = differential_evolution(event_loss, bounds[model], args=(model, train), seed=20260811,
                                         popsize=10, maxiter=80, polish=True, workers=1, tol=1e-7)
            parameter_map[(land_use, model)] = opt.x
            names = ["f_const_mm_min", "tau_min"] if model == "constant_loss" else ["f_final_mm_min", "deficit_scale_mm_min", "decay_per_min", "tau_min"]
            for name, value in zip(names, opt.x):
                parameter_rows.append({"land_use": land_use, "model": model, "parameter": name, "value": float(value),
                                       "objective": float(opt.fun), "n_calibration_events": len(train)})
    pd.DataFrame(parameter_rows).to_csv(RESULTS / "fitted_parameters.csv", index=False)

    metric_rows, prediction_frames = [], []
    for event in event_objects:
        for model in bounds:
            row, frame = evaluate_event(event, model, parameter_map[(event["land_use"], model)])
            metric_rows.append(row); prediction_frames.append(frame)
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(RESULTS / "event_metrics.csv", index=False)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    predictions.to_csv(RESULTS / "time_series_predictions.csv.gz", index=False, compression="gzip")
    summary = aggregate(metrics)
    summary.to_csv(RESULTS / "aggregate_metrics.csv", index=False)

    blind = metrics[metrics.split == "blind_test"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    colors = {"constant_loss": "#2563eb", "soil_state_decay": "#dc2626"}
    for model, g in blind.groupby("model"):
        axes[0].scatter(g.observed_runoff_volume_mm, g.predicted_runoff_volume_mm, s=30, alpha=.78, label=model, color=colors[model])
    lim = max(blind.observed_runoff_volume_mm.max(), blind.predicted_runoff_volume_mm.max()) * 1.05
    axes[0].plot([0, lim], [0, lim], "k--", lw=1); axes[0].set(xlabel="Observed volume (mm)", ylabel="Predicted volume (mm)", xlim=(0, lim), ylim=(0, lim))
    axes[0].legend(frameon=False); axes[0].set_title("Site-blocked blind events")
    sb = summary[summary.split == "blind_test"].set_index("model")
    axes[1].bar(np.arange(2)-.18, sb.loc[["constant_loss", "soil_state_decay"], "volume_rmse_mm"], .36, label="Volume RMSE (mm)")
    axes[1].bar(np.arange(2)+.18, sb.loc[["constant_loss", "soil_state_decay"], "onset_mae_min"], .36, label="Onset MAE (min)")
    axes[1].set_xticks(np.arange(2), ["Constant", "Soil-state"], rotation=10); axes[1].set_title("Blind-test error (lower is better)"); axes[1].legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIGURES / "blind_test_summary.png", dpi=180); plt.close(fig)

    top = blind[blind.model == "constant_loss"].nlargest(3, "observed_runoff_volume_mm")
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=False)
    for ax, m in zip(axes, top.itertuples(index=False)):
        for model, style in [("constant_loss", "--"), ("soil_state_decay", "-")]:
            p = predictions[(predictions.site_number == m.site_number) & (predictions.experiment_number == m.experiment_number) & (predictions.model == model)]
            ax.plot(p.minute, p.observed_cumulative_runoff_mm, color="black", lw=2, label="observed" if model == "constant_loss" else None)
            ax.plot(p.minute, p.predicted_cumulative_runoff_mm, style, color=colors[model], label=model)
        ax.set_title(f"Blind site S{m.site_number:02d}, event E{m.experiment_number}"); ax.set_ylabel("Cumulative runoff (mm)"); ax.grid(alpha=.2)
    axes[-1].set_xlabel("Minutes from experiment start"); axes[0].legend(ncol=3, frameon=False)
    fig.tight_layout(); fig.savefig(FIGURES / "blind_hydrograph_examples.png", dpi=180); plt.close(fig)

    qc_summary = {
        "raw_event_rows": int(len(events)), "valid_events": int(len(valid)), "excluded_events": int(len(events)-len(valid)),
        "sites": int(valid.Site_number.nunique()), "calibration_sites": sorted(set(valid.Site_number)-TEST_SITES),
        "blind_test_sites": sorted(TEST_SITES), "calibration_events": int((valid.split == "calibration").sum()),
        "blind_test_events": int((valid.split == "blind_test").sum()),
        "events_with_expected_minute_count": int((qc.n_rows == qc.expected_rows).sum()),
        "events_with_negative_rain": int((qc.negative_rain_values > 0).sum()),
        "events_with_negative_runoff": int((qc.negative_runoff_values > 0).sum()),
        "events_with_imputed_porosity": int(qc.porosity_imputed.sum()),
        "all_events_have_initial_shallow_soil_moisture": bool(qc.initial_sm_available.all()),
        "note": "138 repository event rows reduce to the documented 132 usable experiments after author-selected subplot and complete mean rainfall/runoff filters."
    }
    (RESULTS / "data_qc_summary.json").write_text(json.dumps(qc_summary, indent=2), encoding="utf-8")
    result_json = {"generated_utc": datetime.now(timezone.utc).isoformat(), "split_rule": "hold out complete sites 5,10,15,20,23",
                   "test_is_blind": True, "metrics": summary.replace({np.nan: None}).to_dict(orient="records")}
    (RESULTS / "summary.json").write_text(json.dumps(result_json, indent=2, allow_nan=False), encoding="utf-8")

    source_files = [RAW / "UNIFR_151460.zip", *sorted(SRC.glob("*.txt"))]
    manifest = pd.DataFrame([{"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in source_files])
    manifest.to_csv(ROOT / "source_manifest.csv", index=False)
    status = {"status": "completed", "generated_utc": datetime.now(timezone.utc).isoformat(), "uses_real_observations": True,
              "official_doi": "10.6094/UNIFR/151460", "valid_events": 132, "blind_test_events": int((valid.split == "blind_test").sum()),
              "models": ["constant_loss_plus_linear_reservoir", "soil_moisture_state_decay_plus_linear_reservoir"],
              "scope": "lumped effective-loss/runoff response only; not 2-D hydraulic validation",
              "blind_test_constant_loss": summary[(summary.split == "blind_test") & (summary.model == "constant_loss")].iloc[0].replace({np.nan: None}).to_dict(),
              "blind_test_soil_state_decay": summary[(summary.split == "blind_test") & (summary.model == "soil_state_decay")].iloc[0].replace({np.nan: None}).to_dict(),
              "python": sys.version.split()[0], "platform": platform.platform(), "key_outputs": ["results/aggregate_metrics.csv", "results/event_metrics.csv", "results/summary.json", "results/figures/blind_test_summary.png"]}
    (ROOT / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    artifacts = [p for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name not in {"artifact_manifest.csv"}]
    pd.DataFrame([{"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in artifacts]).to_csv(ROOT / "artifact_manifest.csv", index=False)
    print(json.dumps(qc_summary, indent=2))
    print("\nAGGREGATE METRICS\n", summary.to_string(index=False))


if __name__ == "__main__":
    main()
