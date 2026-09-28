from __future__ import annotations

from dataclasses import dataclass
from math import atan, radians, sin, tan

import numpy as np

from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.mission import MissionReplayBounds

Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TrajectoryBounds:
    min_enu: Vector3
    max_enu: Vector3
    center_enu: Vector3
    span_enu: Vector3
    max_span: float
    bounding_radius: float
    origin_enu: Vector3
    sample_count: int


def _Vector3_Get(values: np.ndarray) -> Vector3:
    vector = np.asarray(values, dtype=np.float64)
    return float(vector[0]), float(vector[1]), float(vector[2])


def TrajectoryGapThreshold_Get(series: TimeSeries) -> float:
    """Cadence is channel-local; global record sequence gaps are irrelevant here."""
    intervals = np.diff(series.timestamp_us.astype(np.float64))
    positive = intervals[intervals > 0]
    median = float(np.median(positive)) if positive.size else 0.0
    tolerance = float(series.metadata.get("trajectory_gap_tolerance_us", 0.0))
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("trajectory_gap_tolerance_invalid")
    return max(2.5 * median, tolerance)


def TimeSeriesGapSummary_Get(
    series: TimeSeries,
    start_timestamp_us: int | None = None,
    end_timestamp_us: int | None = None,
) -> dict[str, float | int]:
    threshold = TrajectoryGapThreshold_Get(series)
    times = series.timestamp_us
    mask = np.ones(times.size, dtype=np.bool_)
    if start_timestamp_us is not None:
        mask &= times >= start_timestamp_us
    if end_timestamp_us is not None:
        mask &= times <= end_timestamp_us
    selected = times[mask].astype(np.float64)
    values = np.asarray(series.values)[mask]
    finite = np.isfinite(values)
    if values.ndim > 1:
        finite = np.all(finite, axis=1)
    return {
        "gap_threshold_us": threshold,
        "timestamp_gap_segments": int(np.count_nonzero(np.diff(selected) > threshold)),
        "invalid_samples": int(np.count_nonzero(~(series.valid[mask] & finite))),
    }


@dataclass(frozen=True, slots=True)
class TrajectoryPhaseSegment:
    phase: int
    timestamp_us: np.ndarray
    values: np.ndarray


def TrajectoryPhaseSegments_Build(
    series: TimeSeries,
    phase_timestamps_us: tuple[int, ...] = (),
    *,
    start_timestamp_us: int | None = None,
    end_timestamp_us: int | None = None,
) -> tuple[TrajectoryPhaseSegment, ...]:
    """Create display geometry only. Invalid samples and true gaps split every phase."""
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("trajectory_channel_must_be_enu")
    events = sorted(set(phase_timestamps_us))
    threshold = TrajectoryGapThreshold_Get(series)
    times = series.timestamp_us
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    segments: list[TrajectoryPhaseSegment] = []
    run_times: list[int] = []
    run_values: list[np.ndarray] = []
    phase = 0

    def flush() -> None:
        if not run_times:
            return
        t = np.asarray(run_times, dtype=np.uint64)
        v = np.asarray(run_values, dtype=np.float64)
        mask = np.ones(t.size, dtype=np.bool_)
        if start_timestamp_us is not None:
            mask &= t >= start_timestamp_us
        if end_timestamp_us is not None:
            mask &= t <= end_timestamp_us
        if mask.any():
            t, v = t[mask], v[mask]
            t.setflags(write=False)
            v.setflags(write=False)
            segments.append(TrajectoryPhaseSegment(phase, t, v))
        run_times.clear()
        run_values.clear()

    previous: int | None = None
    for i in range(series.count):
        if not valid[i]:
            flush()
            previous = None
            continue
        timestamp = int(times[i])
        reanchored = previous is not None and any(
            int(times[previous]) < event <= timestamp
            for event in series.metadata.get("discontinuity_timestamps_us", ()))
        if (
            previous is None
            or reanchored
            or not (0 < timestamp - int(times[previous]) <= threshold)
        ):
            flush()
            phase = int(np.searchsorted(events, timestamp, side="right"))
            run_times.append(timestamp)
            run_values.append(values[i])
        else:
            lower = int(times[previous])
            for event in events:
                if lower < event <= timestamp:
                    ratio = (event - lower) / (timestamp - lower)
                    point = values[previous] + ratio * (values[i] - values[previous])
                    run_times.append(event)
                    run_values.append(point)
                    flush()
                    phase = int(np.searchsorted(events, event, side="right"))
                    run_times.append(event)
                    run_values.append(point)
            if not run_times or run_times[-1] != timestamp:
                run_times.append(timestamp)
                run_values.append(values[i])
        previous = i
    flush()
    return tuple(segments)


def TrajectoryPhaseValues_Get(
    segments: tuple[TrajectoryPhaseSegment, ...],
    phase: int,
    *,
    timestamp_us: int | None = None,
    origin: np.ndarray | None = None,
    max_points_per_segment: int | None = None,
) -> np.ndarray:
    """NaN separators retain real breaks for Matplotlib and GL line strips."""
    parts: list[np.ndarray] = []
    for segment in segments:
        if segment.phase != phase:
            continue
        end = (
            segment.timestamp_us.size
            if timestamp_us is None
            else int(np.searchsorted(segment.timestamp_us, timestamp_us, side="right"))
        )
        points = segment.values[:end]
        if not points.size:
            continue
        if max_points_per_segment and points.shape[0] > max_points_per_segment:
            indices = np.linspace(0, points.shape[0] - 1, max_points_per_segment).astype(int)
            points = points[indices]
        if parts:
            parts.append(np.full((1, 3), np.nan))
        parts.append(points)
    result = np.concatenate(parts) if parts else np.empty((0, 3))
    return result if origin is None else result - origin


def TrajectoryPosition_At(series: TimeSeries, timestamp_us: int) -> np.ndarray | None:
    values = np.asarray(series.values, dtype=np.float64)
    if series.count == 0 or values.ndim != 2 or values.shape[1] != 3:
        return None
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    upper = int(np.searchsorted(series.timestamp_us, timestamp_us, side="left"))
    if upper < series.count and int(series.timestamp_us[upper]) == timestamp_us:
        return values[upper].copy() if valid[upper] else None
    if upper == 0 or upper == series.count or not (valid[upper - 1] and valid[upper]):
        return None
    lower = upper - 1
    span = int(series.timestamp_us[upper]) - int(series.timestamp_us[lower])
    if not 0 < span <= TrajectoryGapThreshold_Get(series):
        return None
    ratio = (timestamp_us - int(series.timestamp_us[lower])) / span
    return values[lower] + ratio * (values[upper] - values[lower])


def TrajectoryPosition_NearEvent(
    series: TimeSeries,
    timestamp_us: int,
) -> np.ndarray | None:
    interpolated = TrajectoryPosition_At(series, timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        return None
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    timestamps = series.timestamp_us[valid].astype(np.int64)
    points = values[valid]
    if timestamps.size == 0:
        return None
    if int(timestamps[0]) <= timestamp_us <= int(timestamps[-1]):
        return None
    intervals = np.diff(timestamps)
    positive_intervals = intervals[intervals > 0]
    typical_interval = float(np.median(positive_intervals)) if positive_intervals.size else 0.0
    tolerance_us = max(int(typical_interval * 5.0), 100_000)
    index = int(np.argmin(np.abs(timestamps - timestamp_us)))
    if abs(int(timestamps[index]) - timestamp_us) > tolerance_us:
        return None
    return points[index].copy()


def TrajectoryOrigin_Get(series: TimeSeries, start_timestamp_us: int) -> np.ndarray:
    interpolated = TrajectoryPosition_At(series, start_timestamp_us)
    if interpolated is not None:
        return interpolated
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        return np.zeros(3, dtype=np.float64)
    valid = series.valid & np.all(np.isfinite(values), axis=1)
    post_start = np.flatnonzero(
        valid & (series.timestamp_us >= np.uint64(max(start_timestamp_us, 0)))
    )
    if post_start.size:
        return values[post_start[0]].copy()
    available = np.flatnonzero(valid)
    if available.size:
        return values[available[0]].copy()
    return np.zeros(3, dtype=np.float64)


def TrajectoryBounds_Calculate(
    series: TimeSeries,
    mission_bounds: MissionReplayBounds,
) -> TrajectoryBounds:
    origin = TrajectoryOrigin_Get(series, mission_bounds.start_timestamp_us)
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        zero = (0.0, 0.0, 0.0)
        return TrajectoryBounds(
            min_enu=zero,
            max_enu=zero,
            center_enu=zero,
            span_enu=zero,
            max_span=0.0,
            bounding_radius=0.0,
            origin_enu=_Vector3_Get(origin),
            sample_count=0,
        )
    valid = (
        series.valid
        & np.all(np.isfinite(values), axis=1)
        & (series.timestamp_us >= np.uint64(max(mission_bounds.start_timestamp_us, 0)))
        & (series.timestamp_us <= np.uint64(max(mission_bounds.end_timestamp_us, 0)))
    )
    displayed = values[valid] - origin
    if displayed.size == 0:
        zero = (0.0, 0.0, 0.0)
        return TrajectoryBounds(
            min_enu=zero,
            max_enu=zero,
            center_enu=zero,
            span_enu=zero,
            max_span=0.0,
            bounding_radius=0.0,
            origin_enu=_Vector3_Get(origin),
            sample_count=0,
        )
    minimum = np.min(displayed, axis=0)
    maximum = np.max(displayed, axis=0)
    center = (minimum + maximum) * 0.5
    span = maximum - minimum
    radius = float(np.max(np.linalg.norm(displayed - center, axis=1)))
    return TrajectoryBounds(
        min_enu=_Vector3_Get(minimum),
        max_enu=_Vector3_Get(maximum),
        center_enu=_Vector3_Get(center),
        span_enu=_Vector3_Get(span),
        max_span=float(np.max(span)),
        bounding_radius=radius,
        origin_enu=_Vector3_Get(origin),
        sample_count=int(displayed.shape[0]),
    )


def TrajectoryCameraDistance_Get(
    bounds: TrajectoryBounds,
    *,
    horizontal_fov_deg: float,
    aspect_ratio: float,
    margin_ratio: float = 1.15,
    minimum_distance: float = 8.0,
) -> float:
    fov = float(horizontal_fov_deg)
    aspect = float(aspect_ratio)
    margin = float(margin_ratio)
    if not np.isfinite(fov) or fov <= 1.0 or fov >= 179.0:
        raise ValueError("trajectory_camera_fov_invalid")
    if not np.isfinite(aspect) or aspect <= 0.0:
        raise ValueError("trajectory_camera_aspect_invalid")
    if not np.isfinite(margin) or margin < 1.0:
        raise ValueError("trajectory_camera_margin_invalid")
    horizontal_half_angle = radians(fov * 0.5)
    vertical_half_angle = atan(tan(horizontal_half_angle) / aspect)
    limiting_half_angle = min(horizontal_half_angle, vertical_half_angle)
    radius = max(float(bounds.bounding_radius), 0.0)
    fitted = 0.0 if radius == 0.0 else radius / sin(limiting_half_angle) * margin
    return max(float(minimum_distance), fitted)
