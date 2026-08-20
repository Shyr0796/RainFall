"""Small, dependency-light validation metrics used by all experiments.

The functions deliberately return NaN when a metric is undefined rather than
silently manufacturing a favourable score.  Inputs are flattened and compared
only where both observation and simulation are finite.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


def _paired(observed: Any, simulated: Any) -> tuple[np.ndarray, np.ndarray]:
    obs = np.asarray(observed, dtype=float).ravel()
    sim = np.asarray(simulated, dtype=float).ravel()
    if obs.shape != sim.shape:
        raise ValueError(f"shape mismatch: observed={obs.shape}, simulated={sim.shape}")
    valid = np.isfinite(obs) & np.isfinite(sim)
    return obs[valid], sim[valid]


@dataclass(frozen=True)
class RegressionMetrics:
    n: int
    mae: float
    rmse: float
    bias: float
    nse: float
    kge: float


def regression_metrics(observed: Any, simulated: Any) -> RegressionMetrics:
    obs, sim = _paired(observed, simulated)
    if not obs.size:
        return RegressionMetrics(0, *(float("nan"),) * 5)
    residual = sim - obs
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual**2)))
    bias = float(np.mean(residual))
    denominator = float(np.sum((obs - np.mean(obs)) ** 2))
    nse = float(1.0 - np.sum(residual**2) / denominator) if denominator > 0 else float("nan")
    obs_std = float(np.std(obs))
    sim_std = float(np.std(sim))
    obs_mean = float(np.mean(obs))
    if obs.size >= 2 and obs_std > 0 and obs_mean != 0:
        correlation = float(np.corrcoef(obs, sim)[0, 1]) if sim_std > 0 else float("nan")
        variability = sim_std / obs_std
        ratio = float(np.mean(sim)) / obs_mean
        kge = (
            float(1.0 - np.sqrt((correlation - 1) ** 2 + (variability - 1) ** 2 + (ratio - 1) ** 2))
            if np.isfinite(correlation)
            else float("nan")
        )
    else:
        kge = float("nan")
    return RegressionMetrics(obs.size, mae, rmse, bias, nse, kge)


def binary_extent_metrics(observed_wet: Any, simulated_wet: Any) -> dict[str, float | int]:
    obs = np.asarray(observed_wet, dtype=bool).ravel()
    sim = np.asarray(simulated_wet, dtype=bool).ravel()
    if obs.shape != sim.shape:
        raise ValueError(f"shape mismatch: observed={obs.shape}, simulated={sim.shape}")
    hits = int(np.sum(obs & sim))
    misses = int(np.sum(obs & ~sim))
    false_alarms = int(np.sum(~obs & sim))
    correct_negatives = int(np.sum(~obs & ~sim))

    def ratio(a: int, b: int) -> float:
        return float(a / b) if b else float("nan")

    return {
        "n": int(obs.size),
        "hits": hits,
        "misses": misses,
        "false_alarms": false_alarms,
        "correct_negatives": correct_negatives,
        "csi_iou": ratio(hits, hits + misses + false_alarms),
        "pod_recall": ratio(hits, hits + misses),
        "far": ratio(false_alarms, hits + false_alarms),
        "precision": ratio(hits, hits + false_alarms),
    }


def velocity_vector_metrics(
    observed_u: Any,
    observed_v: Any,
    simulated_u: Any,
    simulated_v: Any,
    *,
    observed_depth: Any | None = None,
    simulated_depth: Any | None = None,
    minimum_speed: float = 0.0,
    minimum_depth: float = 0.0,
) -> dict[str, float | int]:
    ou = np.asarray(observed_u, dtype=float).ravel()
    ov = np.asarray(observed_v, dtype=float).ravel()
    su = np.asarray(simulated_u, dtype=float).ravel()
    sv = np.asarray(simulated_v, dtype=float).ravel()
    if not (ou.shape == ov.shape == su.shape == sv.shape):
        raise ValueError("velocity components must have matching shapes")
    obs_speed = np.hypot(ou, ov)
    sim_speed = np.hypot(su, sv)
    valid = np.isfinite(ou) & np.isfinite(ov) & np.isfinite(su) & np.isfinite(sv)
    valid &= (obs_speed >= minimum_speed) & (sim_speed >= minimum_speed)
    if observed_depth is not None or simulated_depth is not None:
        if observed_depth is None or simulated_depth is None:
            raise ValueError("both observed_depth and simulated_depth are required")
        oh = np.asarray(observed_depth, dtype=float).ravel()
        sh = np.asarray(simulated_depth, dtype=float).ravel()
        if oh.shape != ou.shape or sh.shape != ou.shape:
            raise ValueError("depth and velocity shapes must match")
        valid &= np.isfinite(oh) & np.isfinite(sh) & (oh >= minimum_depth) & (sh >= minimum_depth)

    evaluated = int(np.sum(valid))
    total = int(valid.size)
    if not evaluated:
        return {
            "n_total": total,
            "n_evaluated": 0,
            "masked_fraction": 1.0 if total else float("nan"),
            "rmse_u": float("nan"),
            "rmse_v": float("nan"),
            "vector_rmse": float("nan"),
            "speed_mae": float("nan"),
            "direction_median_deg": float("nan"),
            "direction_mae_deg": float("nan"),
            "within_15_deg": float("nan"),
            "within_30_deg": float("nan"),
            "within_45_deg": float("nan"),
        }

    du = su[valid] - ou[valid]
    dv = sv[valid] - ov[valid]
    dot = su[valid] * ou[valid] + sv[valid] * ov[valid]
    cross = np.abs(su[valid] * ov[valid] - sv[valid] * ou[valid])
    angle = np.degrees(np.arctan2(cross, dot))
    return {
        "n_total": total,
        "n_evaluated": evaluated,
        "masked_fraction": float(1.0 - evaluated / total),
        "rmse_u": float(np.sqrt(np.mean(du**2))),
        "rmse_v": float(np.sqrt(np.mean(dv**2))),
        "vector_rmse": float(np.sqrt(np.mean(du**2 + dv**2))),
        "speed_mae": float(np.mean(np.abs(sim_speed[valid] - obs_speed[valid]))),
        "direction_median_deg": float(np.median(angle)),
        "direction_mae_deg": float(np.mean(angle)),
        "within_15_deg": float(np.mean(angle <= 15.0)),
        "within_30_deg": float(np.mean(angle <= 30.0)),
        "within_45_deg": float(np.mean(angle <= 45.0)),
    }


def as_jsonable(metrics: RegressionMetrics | dict[str, Any]) -> dict[str, Any]:
    return asdict(metrics) if isinstance(metrics, RegressionMetrics) else dict(metrics)

