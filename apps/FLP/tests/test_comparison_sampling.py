import numpy as np
import pytest

from silverstar_flp.core.comparison import (
    Series_Compare,
    Series_ComparisonView,
    Series_ExactTimestampMatch,
    Series_SamplingGet,
)
from silverstar_flp.core.dataset import TimeSeries


def _Series_Create(timestamps, values=None, valid=None):
    n = len(timestamps)
    return TimeSeries(
        np.asarray(timestamps, dtype=np.uint64),
        np.asarray(values if values is not None else np.arange(n), dtype=float),
        "m",
        "position",
        "test",
        np.asarray(valid if valid is not None else [True] * n),
    )


def test_exact_subset_retains_nonlinear_full_output(monkeypatch):
    source = _Series_Create(np.arange(0, 81, 10), [0, 50, 20, -30, 4, 90, 70, 25, 8])
    recorded = _Series_Create([0, 40, 80], [0, 4, 8])
    indices, matched = Series_ExactTimestampMatch(source.timestamp_us, recorded.timestamp_us)
    np.testing.assert_array_equal(indices, [0, 4, 8])
    assert matched.all()
    monkeypatch.setattr(np, "interp", lambda *a, **k: pytest.fail("exact compare interpolated"))
    comparison = Series_Compare(recorded, source)
    assert comparison.comparison_mode == "exact"
    assert comparison.statistics.maximum_absolute_error == 0
    view = Series_ComparisonView(recorded, source)
    np.testing.assert_array_equal(view.timestamp_us, recorded.timestamp_us)
    np.testing.assert_array_equal(view.values, recorded.values)
    assert view.metadata["display_only"]
    assert source.count == 9 and view.count == 3
    assert source.values[1] == 50 and not source.values.flags.writeable


def test_missing_is_invalid_in_view_and_interpolation_is_explicit():
    source = _Series_Create([0, 40, 80], [0, 4, 8])
    recorded = _Series_Create([0, 30, 80], [0, 3, 8])
    view = Series_ComparisonView(recorded, source)
    assert view.metadata["missing_timestamp_us"] == (30,)
    assert view.metadata["missing_exact_match_count"] == 1
    assert not view.valid[1] and np.isnan(view.values[1])
    assert Series_Compare(recorded, source).comparison_mode == "interpolated"


def test_matching_preserves_uint64_and_rejects_duplicate_source_ambiguity():
    base = 2**63
    indices, matched = Series_ExactTimestampMatch(
        np.asarray([base, base + 1, base + 1, base + 2], dtype=np.uint64),
        np.asarray([base, base + 1, base + 2, base + 3], dtype=np.uint64),
    )
    np.testing.assert_array_equal(indices, [0, -1, 3, -1])
    np.testing.assert_array_equal(matched, [True, False, True, False])


def test_validity_is_combined_and_empty_match_is_safe():
    source = _Series_Create([0, 10, 20], valid=[True, False, True])
    target = _Series_Create([0, 10, 20], valid=[False, True, True])
    assert Series_ComparisonView(target, source).valid.tolist() == [False, False, True]
    assert Series_Compare(target, source).statistics.sample_count == 1
    assert not Series_ComparisonView(target, _Series_Create([])).valid.any()


@pytest.mark.parametrize(
    "times,rate,period",
    [
        ([0, 40000, 80000, 120000], 25, 40000),
        ([0, 10000, 20000, 30000], 100, 10000),
        ([0, 40000, 80000, 400000, 440000], 25, 40000),
        ([0], None, None),
        ([0, 0, 40000], 25, 40000),
        ([], None, None),
    ],
)
def test_measured_rate_uses_positive_median_intervals(times, rate, period):
    sampling = Series_SamplingGet(_Series_Create(times))
    assert sampling.sample_count == len(times)
    assert sampling.measured_rate_hz == rate
    assert sampling.median_period_us == period
