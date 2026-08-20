# 02 Analytic shallow-water benchmark (SWASHES family)

This experiment evaluates a one-dimensional Ritter dry-bed dam-break solution,
embedded as a row-uniform two-dimensional case.  The exact solution is a standard
analytic shallow-water benchmark represented in the SWASHES benchmark family.

Source:

- Delestre et al. (2013), *SWASHES: a compilation of shallow water analytic
  solutions for hydraulic and environmental studies*, International Journal for
  Numerical Methods in Fluids, https://doi.org/10.1002/fld.3741
- Project/paper preprint: https://arxiv.org/abs/1110.0288

Run:

```bash
RAINFALL_FORCE_CPU=1 UV_CACHE_DIR=/tmp/rainfall_uv_cache \
  uv run python validation/experiments/02_swashes/code/run_ritter.py
```

Important interpretation: RainFall implements a **local-inertial reduced model**,
whereas the Ritter solution solves the full frictionless shallow-water equations.
The comparison is therefore an equation-scope diagnostic, not observational
validation.  Water-volume conservation is a direct verification check; depth,
velocity and front-position differences quantify the reduced model's departure
from the full-SWE analytic solution.

