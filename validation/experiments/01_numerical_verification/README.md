# 01 Numerical verification

This experiment checks numerical properties of the current `MountainFloodCA`
implementation.  It does **not** constitute validation against observations.

Checks:

- closed-domain water balance under rainfall;
- an exactly uniform rainfall-minus-infiltration accumulation case;
- lake-at-rest preservation over an irregular bed;
- flux direction on a known diagonal slope;
- downhill movement of a finite water patch;
- open-outlet volume accounting;
- maximum-time-step sensitivity;
- CPU/GPU consistency when a CUDA backend is actually available.

Run from the repository root:

```bash
RAINFALL_FORCE_CPU=1 UV_CACHE_DIR=/tmp/rainfall_uv_cache \
  uv run python validation/experiments/01_numerical_verification/code/run_verification.py
```

Outputs are written to `results/`.  `summary.csv` is the compact machine-readable
check table; `metrics.json` preserves configuration and detailed values.  A GPU
check is marked `SKIP` when the automatic backend falls back to NumPy.

