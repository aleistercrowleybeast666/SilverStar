"""Display copies of AIR position samples; recorded data is never rewritten.

The deliberately broad one-million-kilometre envelope rejects gross numeric
corruption, not flight dynamics. No speed/acceleration gate or smoothing is used.
Invalid rows remain as line breaks, including in animated interpolation.
"""
import math
from dataclasses import dataclass

import numpy as np

POSITION_DISPLAY_MAX_ABS_M = 1_000_000_000.0
AIR_TIME_RESOLUTION_S = 0.001


@dataclass(frozen=True)
class PositionDisplay:
    times_s: np.ndarray
    points_enu: np.ndarray
    valid: np.ndarray
    joins: np.ndarray
    gap_threshold_s: float


def PositionDisplay_Build(samples, gap_threshold_s=None) -> PositionDisplay:
    times = np.asarray([sample.time_s for sample in samples], dtype=float)
    points = np.asarray([sample.values[:3] for sample in samples], dtype=float).reshape(-1, 3)
    valid = (np.isfinite(times) & np.isfinite(points).all(axis=1)
             & (np.abs(points) <= POSITION_DISPLAY_MAX_ABS_M).all(axis=1))
    cadence = np.diff(times)
    if gap_threshold_s is None:
        # AIR stamps are integer milliseconds. Work in ticks so floating-point
        # subtraction cannot push an exact boundary into the next millisecond.
        ticks = np.rint(times * 1000)
        intervals = np.diff(ticks)
        positive = intervals[np.isfinite(intervals) & (intervals > 0)]
        threshold_ms = min(1000, math.ceil(2.5 * float(np.median(positive)))) if positive.size else 0
        threshold = threshold_ms * AIR_TIME_RESOLUTION_S
    else:
        threshold = float(gap_threshold_s)
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("horizontal_trajectory_gap_invalid")
    # A few ULPs accommodate subtraction of mission seconds. This is numerical
    # roundoff only, orders of magnitude below the AIR timestamp resolution.
    finite_times = times[np.isfinite(times)]
    scale = max(float(np.abs(finite_times).max()), 1.0) if finite_times.size else 1.0
    threshold += 4 * np.spacing(scale)
    joins = valid[:-1] & valid[1:] & (cadence > 0) & (cadence <= threshold)
    points[~valid] = np.nan
    for array in (times, points, valid, joins):
        array.setflags(write=False)
    return PositionDisplay(times, points, valid, joins, threshold)


def PositionDisplay_PointAt(display: PositionDisplay, time_s: float, *, hold_end=False):
    """Exact sample or a connected pair; no interpolation through rejected rows."""
    if not math.isfinite(time_s):
        return None
    times, points = display.times_s, display.points_enu
    exact = np.flatnonzero(times == time_s)
    if exact.size:
        index = exact[-1]
        return points[index].copy() if display.valid[index] else None
    pair = np.flatnonzero(display.joins & (times[:-1] < time_s) & (time_s < times[1:]))
    if pair.size == 1:
        i = pair[0]
        ratio = (time_s - times[i]) / (times[i + 1] - times[i])
        return points[i] + ratio * (points[i + 1] - points[i])
    if hold_end and len(times) and display.valid[-1] and time_s > times[-1]:
        return points[-1].copy()
    return None


def PositionDisplay_History(display: PositionDisplay, time_s: float, deploy_time_s=None):
    """Return two phase paths and a current point, preserving every split."""
    indices = np.flatnonzero(np.isfinite(display.times_s) & (display.times_s <= time_s))
    times, points = [], []
    previous = None
    deploy_point = (PositionDisplay_PointAt(display, deploy_time_s)
                    if deploy_time_s is not None else None)
    for i in indices:
        stamp = display.times_s[i]
        if previous is not None:
            if i != previous + 1 or not display.joins[previous]:
                times.append(stamp)
                points.append(np.full(3, np.nan))
            elif deploy_point is not None and display.times_s[previous] < deploy_time_s < stamp:
                times.append(deploy_time_s)
                points.append(deploy_point)
        times.append(stamp)
        points.append(display.points_enu[i])
        previous = i
    current = PositionDisplay_PointAt(display, time_s, hold_end=True)
    if current is not None and (not times or times[-1] < time_s):
        if deploy_point is not None and times and times[-1] < deploy_time_s < time_s:
            times.append(deploy_time_s)
            points.append(deploy_point)
        times.append(time_s)
        points.append(current)
    history = np.asarray(points, dtype=float).reshape(-1, 3)
    if deploy_time_s is None or not math.isfinite(deploy_time_s):
        return history, np.empty((0, 3)), current
    stamps = np.asarray(times)
    return history[stamps <= deploy_time_s], history[stamps >= deploy_time_s], current
