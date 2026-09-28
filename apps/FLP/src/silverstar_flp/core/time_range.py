"""Display/export ranges; never changes recorded data or replay inputs."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

PRESET_SECONDS = (5, 10, 30, 60, 120)


@dataclass(frozen=True, slots=True)
class TimeRangeModel:
    mission_duration: float = 0.0
    start: float = 0.0
    end: float = 0.0
    preset: str = "Full"
    custom_duration: float = 30.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def State_Get(self) -> dict:
        return asdict(self)


class TimeRangeController:
    def __init__(self) -> None:
        self.model = TimeRangeModel()

    def Mission_Set(self, duration: float) -> TimeRangeModel:
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("time_range_invalid")
        self.model = TimeRangeModel(mission_duration=duration)
        return self.Duration_Set(min(30.0, duration))

    def Range_Set(self, start: float, end: float) -> TimeRangeModel:
        if not all(math.isfinite(value) for value in (start, end)):
            raise ValueError("time_range_invalid")
        limit = self.model.mission_duration
        start = min(limit, max(0.0, start))
        end = min(limit, max(start, end))
        duration = end - start
        preset = next((str(value) for value in PRESET_SECONDS
                       if math.isclose(duration, value, abs_tol=1e-6)), "Custom")
        if start == 0 and end == limit:
            preset = "Full"
        self.model = TimeRangeModel(limit, start, end, preset,
                                   duration if preset == "Custom" else self.model.custom_duration)
        return self.model

    def Duration_Set(self, duration: float) -> TimeRangeModel:
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("time_range_invalid")
        duration = min(duration, self.model.mission_duration)
        start = min(self.model.start, self.model.mission_duration - duration)
        return self.Range_Set(start, start + duration)

    def Window_Shift(self, direction: int) -> TimeRangeModel:
        if direction not in (-1, 1):
            raise ValueError("time_range_direction_invalid")
        duration = self.model.duration
        limit = self.model.mission_duration
        if duration >= limit:
            return self.Range_Set(0.0, limit)
        start = min(max(self.model.start + direction * duration, 0.0), limit - duration)
        return self.Range_Set(start, start + duration)

    def Preset_Set(self, preset: str) -> TimeRangeModel:
        if preset == "Full":
            return self.Range_Set(0.0, self.model.mission_duration)
        return self.Duration_Set(
            self.model.custom_duration if preset == "Custom" else float(preset)
        )

    def State_Restore(self, state: dict) -> TimeRangeModel:
        custom = float(state.get("custom_duration", 30.0))
        if not math.isfinite(custom) or custom < 0:
            raise ValueError("time_range_invalid")
        self.model = TimeRangeModel(self.model.mission_duration, custom_duration=custom)
        return self.Range_Set(float(state["start"]), float(state["end"]))


def TimePages_Get(duration: float, page_duration: float = 30.0,
                  *, start: float = 0.0) -> tuple[tuple[float, float], ...]:
    if (
        not all(math.isfinite(v) for v in (duration, page_duration, start))
        or duration < 0
        or page_duration <= 0
    ):
        raise ValueError("time_range_invalid")
    return tuple((start + i * page_duration, start + min(duration, (i + 1) * page_duration))
                 for i in range(max(1, math.ceil(duration / page_duration))))


def DisplayIndices_Get(timestamps, values, valid, budget: int = 6000) -> np.ndarray:
    """Min/max per axis, with every gap boundary retained (budget is a soft limit)."""
    count = len(timestamps)
    if count <= budget:
        return np.arange(count)
    matrix = np.asarray(values).reshape(count, -1)
    good = np.asarray(valid, dtype=bool) & np.all(np.isfinite(matrix), axis=1)
    differences = np.diff(np.asarray(timestamps, dtype=np.int64))
    positive = differences[differences > 0]
    gap = differences > (3 * np.median(positive) if positive.size else np.inf)
    boundaries = np.flatnonzero((good[1:] != good[:-1]) | gap)
    selected = {0, count - 1, *boundaries.tolist(), *(boundaries + 1).tolist()}
    buckets = max(1, budget // (2 * matrix.shape[1] + 2))
    for indices in np.array_split(np.flatnonzero(good), buckets):
        if not indices.size:
            continue
        selected.update((int(indices[0]), int(indices[-1])))
        for column in range(matrix.shape[1]):
            selected.add(int(indices[np.argmin(matrix[indices, column])]))
            selected.add(int(indices[np.argmax(matrix[indices, column])]))
    return np.asarray(sorted(selected), dtype=np.int64)


def PlotArrays_Get(time, values, *, breaks=(), budget=6000):
    """Display-only envelope with NaN separators, preserving the first point after a gap."""
    time = np.asarray(time, dtype=float)
    values = np.asarray(values, dtype=float)
    if time.size < 2:
        return time, values
    step = np.diff(time)
    positive = step[step > 0]
    gap = step > (3 * np.median(positive) if positive.size else np.inf)
    for timestamp in breaks:
        index = int(np.searchsorted(time, timestamp)) - 1
        if 0 <= index < gap.size:
            gap[index] = True
    positions = np.flatnonzero(gap) + 1
    if positions.size:
        inserted_time = (time[positions - 1] + time[positions]) / 2
        time = np.insert(time, positions, inserted_time)
        values = np.insert(values, positions, np.nan, axis=0)
    valid = np.isfinite(values) if values.ndim == 1 else np.all(np.isfinite(values), axis=1)
    # The envelope only needs relative spacing; microseconds preserve integer differences.
    indices = DisplayIndices_Get(np.rint(time * 1e6).astype(np.int64), values, valid, budget)
    return time[indices], values[indices]
