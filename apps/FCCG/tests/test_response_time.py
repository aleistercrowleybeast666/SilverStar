from __future__ import annotations

import pytest

from silverstar_fccg.project.response_time import (
    IsrTimingBudget,
    ResponseTime_Analyze,
    TaskTimingBudget,
)


def test_response_time_counts_blocking_same_priority_and_isr() -> None:
    tasks = (
        TaskTimingBudget("Device", 7, 1000, 1000, 100),
        TaskTimingBudget("INS", 7, 1000, 1000, 200),
        TaskTimingBudget("Estimator", 6, 5000, 5000, 400, 50),
    )
    isrs = (IsrTimingBudget("UART", 1000, 25),)
    result = ResponseTime_Analyze(tasks, isrs)
    assert tuple(item.response_us for item in result) == (325, 325, 775)
    assert all(item.schedulable for item in result)


def test_response_time_rejects_overload_and_unknown_bounds() -> None:
    result = ResponseTime_Analyze((
        TaskTimingBudget("A", 2, 100, 100, 80),
        TaskTimingBudget("B", 1, 100, 100, 80),
    ), ())
    assert not result[1].schedulable
    with pytest.raises(ValueError):
        ResponseTime_Analyze((TaskTimingBudget("A", 2, 0, 100, 10),), ())
