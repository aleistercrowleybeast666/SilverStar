from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.math import Quaternion_GeodesicErrorDeg, Quaternion_Normalize


@dataclass(frozen=True, slots=True)
class ComparisonStatistics:
    sample_count: int
    mean_error: float
    mean_absolute_error: float
    root_mean_square_error: float
    maximum_absolute_error: float


@dataclass(frozen=True, slots=True)
class SeriesComparison:
    timestamp_us: np.ndarray
    error: np.ndarray
    statistics: ComparisonStatistics
    unit: str
    quantity: str
    comparison_mode: str = "exact"


@dataclass(frozen=True, slots=True)
class SeriesSampling:
    sample_count: int
    measured_rate_hz: float | None
    median_period_us: float | None


def Series_SamplingGet(series: TimeSeries) -> SeriesSampling:
    timestamps = series.timestamp_us[series.valid]
    intervals = np.diff(timestamps)
    intervals = intervals[intervals > 0]
    period = float(np.median(intervals)) if intervals.size else None
    return SeriesSampling(series.count, 1e6 / period if period else None, period)


def Series_ExactTimestampMatch(
    source_timestamps: np.ndarray,
    target_timestamps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return indices (-1 for missing/ambiguous) and an exact match mask; never interpolate."""
    source = np.asarray(source_timestamps, dtype=np.uint64)
    target = np.asarray(target_timestamps, dtype=np.uint64)
    if source.ndim != 1 or target.ndim != 1:
        raise ValueError("timestamp_arrays_must_be_one_dimensional")
    if source.size > 1 and np.any(source[1:] < source[:-1]):
        raise ValueError("source_timestamps_must_be_monotonic")
    left = np.searchsorted(source, target, side="left")
    right = np.searchsorted(source, target, side="right")
    matched = (right - left) == 1
    return np.where(matched, left, -1), matched


def Series_ComparisonView(recorded: TimeSeries, recomputed: TimeSeries) -> TimeSeries:
    indices, matched = Series_ExactTimestampMatch(recomputed.timestamp_us, recorded.timestamp_us)
    values = np.full((recorded.count,) + recomputed.values.shape[1:], np.nan)
    values[matched] = recomputed.values[indices[matched]]
    valid = recorded.valid & matched
    valid[matched] &= recomputed.valid[indices[matched]]
    missing = recorded.valid & ~matched
    source_rate = Series_SamplingGet(recomputed)
    display_rate = Series_SamplingGet(recorded)
    return TimeSeries(
        timestamp_us=recorded.timestamp_us,
        values=values,
        unit=recomputed.unit,
        quantity=recomputed.quantity,
        source=recomputed.source,
        valid=valid,
        columns=recomputed.columns,
        metadata={
            **recomputed.metadata,
            "display_only": True,
            "comparison_sampling": "recorded_timestamps",
            "recorded_count": int(np.count_nonzero(recorded.valid)),
            "exact_match_count": int(np.count_nonzero(recorded.valid & matched)),
            "missing_exact_match_count": int(np.count_nonzero(missing)),
            "missing_timestamp_us": tuple(int(v) for v in recorded.timestamp_us[missing]),
            "source_rate_hz": source_rate.measured_rate_hz,
            "display_rate_hz": display_rate.measured_rate_hz,
        },
    )


def _Values_Interpolate(
    source_timestamp_us: np.ndarray,
    source_values: np.ndarray,
    target_timestamp_us: np.ndarray,
) -> np.ndarray:
    source_timestamps = np.asarray(source_timestamp_us, dtype=np.uint64)
    target_timestamps = np.asarray(target_timestamp_us, dtype=np.uint64)
    values = np.asarray(source_values, dtype=np.float64)
    if source_timestamps.size == 0:
        return np.empty((0,) + values.shape[1:], dtype=np.float64)
    origin = min(int(source_timestamps[0]), int(target_timestamps[0]))
    source_time = (source_timestamps.astype(np.float64) - origin) * 1.0e-6
    target_time = (target_timestamps.astype(np.float64) - origin) * 1.0e-6
    if values.ndim == 1:
        return np.interp(target_time, source_time, values)
    return np.column_stack(
        [np.interp(target_time, source_time, values[:, index]) for index in range(values.shape[1])]
    )


def _Quaternion_Interpolate(
    source_timestamp_us: np.ndarray,
    source_values: np.ndarray,
    target_timestamp_us: np.ndarray,
) -> np.ndarray:
    source_timestamps = np.asarray(source_timestamp_us, dtype=np.uint64)
    source = np.asarray(source_values, dtype=np.float64)
    target_timestamps = np.asarray(target_timestamp_us, dtype=np.uint64)
    output = np.empty((len(target_timestamps), 4), dtype=np.float64)
    for output_index, timestamp in enumerate(target_timestamps):
        right = int(np.searchsorted(source_timestamps, timestamp, side="left"))
        if right <= 0:
            output[output_index] = Quaternion_Normalize(source[0])
            continue
        if right >= len(source_timestamps):
            output[output_index] = Quaternion_Normalize(source[-1])
            continue
        left = right - 1
        interval = int(source_timestamps[right]) - int(source_timestamps[left])
        fraction = (
            0.0 if interval <= 0 else (int(timestamp) - int(source_timestamps[left])) / interval
        )
        first = Quaternion_Normalize(source[left]).astype(np.float64)
        second = Quaternion_Normalize(source[right]).astype(np.float64)
        dot = float(np.dot(first, second))
        if dot < 0.0:
            second = -second
            dot = -dot
        if dot > 0.9995:
            interpolated = first + fraction * (second - first)
        else:
            theta = np.arccos(np.clip(dot, -1.0, 1.0))
            interpolated = (
                np.sin((1.0 - fraction) * theta) / np.sin(theta) * first
                + np.sin(fraction * theta) / np.sin(theta) * second
            )
        output[output_index] = Quaternion_Normalize(interpolated)
    return output


def Series_Compare(
    recorded: TimeSeries,
    recomputed: TimeSeries,
    *,
    quaternion: bool = False,
) -> SeriesComparison:
    if recorded.count == 0 or recomputed.count == 0:
        empty = np.asarray([], dtype=np.float64)
        statistics = ComparisonStatistics(0, float("nan"), float("nan"), float("nan"), float("nan"))
        return SeriesComparison(
            np.asarray([], dtype=np.uint64), empty, statistics, recorded.unit, recorded.quantity
        )
    start = max(int(recorded.timestamp_us[0]), int(recomputed.timestamp_us[0]))
    end = min(int(recorded.timestamp_us[-1]), int(recomputed.timestamp_us[-1]))
    mask = recorded.valid & (recorded.timestamp_us >= start) & (recorded.timestamp_us <= end)
    timestamps = recorded.timestamp_us[mask]
    recorded_values = np.asarray(recorded.values[mask], dtype=np.float64)
    indices, matched = Series_ExactTimestampMatch(recomputed.timestamp_us, timestamps)
    mode = "exact" if np.all(matched) else "interpolated"
    if mode == "exact":
        recomputed_values = np.asarray(recomputed.values[indices], dtype=np.float64).copy()
        recomputed_values[~recomputed.valid[indices]] = np.nan
    elif quaternion:
        recomputed_values = _Quaternion_Interpolate(
            recomputed.timestamp_us, recomputed.values, timestamps
        )
    else:
        recomputed_values = _Values_Interpolate(
            recomputed.timestamp_us, recomputed.values, timestamps
        )
    if quaternion:
        error = np.asarray(
            [
                Quaternion_GeodesicErrorDeg(recorded_values[index], recomputed_values[index])
                for index in range(len(timestamps))
            ],
            dtype=np.float64,
        )
        unit = "deg"
        quantity = "attitude_geodesic_error"
    else:
        error = recorded_values - recomputed_values
        unit = recorded.unit
        quantity = f"{recorded.quantity}_error"
    finite = np.isfinite(error)
    if error.ndim > 1:
        finite = np.all(finite, axis=1)
        scalar_error = np.linalg.norm(error[finite], axis=1)
    else:
        scalar_error = error[finite]
    if scalar_error.size:
        statistics = ComparisonStatistics(
            sample_count=int(scalar_error.size),
            mean_error=float(np.mean(scalar_error)),
            mean_absolute_error=float(np.mean(np.abs(scalar_error))),
            root_mean_square_error=float(np.sqrt(np.mean(scalar_error**2))),
            maximum_absolute_error=float(np.max(np.abs(scalar_error))),
        )
    else:
        statistics = ComparisonStatistics(0, float("nan"), float("nan"), float("nan"), float("nan"))
    return SeriesComparison(timestamps, error, statistics, unit, quantity, mode)
