#!/usr/bin/env python3
"""Fast conservation and wall-flux checks for the experiment-local adapter."""

import numpy as np

from urban_adapter import Boundary, UrbanLocalInertialAdapter


mask = np.ones((24, 12), dtype=bool)
mask[8:16, 4:8] = False
inlet = Boundary("in", (np.zeros(4, int), np.arange(4, 8)), 2e-4)
stage = Boundary("out", (np.full(4, 23, int), np.arange(4, 8)), 0.02)
model = UrbanLocalInertialAdapter(mask, 0.02, 0.01, [inlet], [stage], 0.02)
for _ in range(500):
    model.step()
assert abs(model.mass_error_m3()) < 1e-12
assert np.all(model.qx[7, 4:8] == 0) and np.all(model.qx[15, 4:8] == 0)
assert np.all(model.qy[8:16, 3] == 0) and np.all(model.qy[8:16, 7] == 0)
print("PASS: mass conservation and impermeable obstacle faces")
