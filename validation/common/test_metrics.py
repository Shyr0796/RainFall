import math

import numpy as np

from validation.common.metrics import (
    binary_extent_metrics,
    regression_metrics,
    velocity_vector_metrics,
)


def test_regression_identity():
    result = regression_metrics([1, 2, 3], [1, 2, 3])
    assert result.rmse == 0.0
    assert result.nse == 1.0
    assert result.kge == 1.0


def test_binary_extent_counts():
    result = binary_extent_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert result["hits"] == 1
    assert result["misses"] == 1
    assert result["false_alarms"] == 1
    assert math.isclose(result["csi_iou"], 1 / 3)


def test_direction_wrap_and_reverse():
    near_wrap = velocity_vector_metrics([1.0], [-0.01], [1.0], [0.01])
    assert near_wrap["direction_mae_deg"] < 2.0
    reverse = velocity_vector_metrics([1.0], [0.0], [-1.0], [0.0])
    assert np.isclose(reverse["direction_mae_deg"], 180.0)
