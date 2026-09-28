"""Bounded delayed replay retaining calibrated BODY input, not old ENU delta-v."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from silverstar_flp.plugins.algorithms.eskf15.filter import (
    Eskf15Filter,
    EskfMeasurementResult,
    EskfState,
    EskfUpdateResult,
)


@dataclass(frozen=True, slots=True)
class BodyStep:
    start_us: int
    end_us: int
    gyro1: np.ndarray
    accel1: np.ndarray
    gyro2: np.ndarray
    accel2: np.ndarray
    source: int = 0
    generation: int = 0
    quality_flags: int | None = None

    def Interval_Apply(self, kernel: Eskf15Filter, start_us: int, end_us: int) -> None:
        if end_us <= start_us:
            return
        if self.quality_flags is not None and self.quality_flags & 0x72:
            raise ValueError("eskf_body_quality_hard_reject")
        noise_scale = 4.0 if (self.quality_flags or 0) & 0x05 else 1.0
        midpoint = self.start_us + (self.end_us - self.start_us) // 2
        # Two piecewise-constant trapezoidal sub-sample means are the stored
        # immutable input. A split re-integrates each retained body segment.
        left = max(0.0, min(end_us, midpoint) - start_us) * 1e-6
        right = max(0.0, end_us - max(start_us, midpoint)) * 1e-6
        if start_us == self.start_us and end_us == self.end_us:
            kernel.Prediction_ApplyPair(
                self.gyro1,
                self.accel1,
                left,
                self.gyro2,
                self.accel2,
                right,
                process_noise_scale=noise_scale,
            )
        else:
            if left:
                kernel.Prediction_Apply(
                    self.gyro1, self.accel1, left, process_noise_scale=noise_scale
                )
            if right:
                kernel.Prediction_Apply(
                    self.gyro2, self.accel2, right, process_noise_scale=noise_scale
                )


@dataclass(frozen=True, slots=True)
class Measurement:
    key: tuple[int, int]
    timestamp_us: int
    receive_us: int
    group: int
    value: np.ndarray
    variance: np.ndarray
    physically_valid: bool
    quality_scale: float = 1.0
    consistency_scale: float = 1.0
    source: int = 0
    generation: int = 0


class DelayedReplay:
    def __init__(
        self,
        kernel: Eskf15Filter,
        start_us: int,
        *,
        horizon_us: int = 600_000,
        max_steps: int = 192,
        max_measurements: int = 208,
        max_replay_steps: int = 608,
        soft: tuple[float, float] = (6.635, 9.21),
        hard: tuple[float, float] = (10.828, 13.816),
        max_r_scale: float = 4.0,
        lever_arm: np.ndarray | None = None,
    ):
        self.kernel, self.present_us = kernel, start_us
        self.base_us, self.base = start_us, kernel.state.State_Clone()
        self.base_omega = kernel.last_omega.copy()
        self.horizon_us, self.max_steps = horizon_us, max_steps
        self.max_measurements, self.max_replay_steps = max_measurements, max_replay_steps
        self.soft, self.hard, self.max_r_scale = soft, hard, max_r_scale
        self.lever_arm = np.zeros(3) if lever_arm is None else np.asarray(lever_arm)
        self.steps: list[BodyStep] = []
        self.measurements: list[Measurement] = []
        self.checkpoints: dict[int, EskfState] = {}
        self.checkpoint_omega: dict[int, np.ndarray] = {}
        self.results: dict[tuple[int, int], EskfMeasurementResult] = {}
        self.seen: set[tuple[int, int]] = set()
        self.history_misses = self.overflows = self.replay_steps = self.maximum_replay_steps = 0
        self.maximum_history = 0
        self.source: int | None = None
        self.generation: int | None = None
        self.initial_start_us = start_us

    def Body_Receive(self, step: BodyStep) -> None:
        if (step.quality_flags or 0) & 0x08 and step.start_us != self.initial_start_us:
            raise ValueError("eskf_body_history_reset_requires_initialization")
        if step.start_us < self.present_us or step.end_us <= step.start_us:
            raise ValueError("eskf_body_time_invalid")
        if self.source is not None and (
            step.source != self.source or step.generation != self.generation
        ):
            raise ValueError("eskf_body_source_generation_changed_requires_initialization")
        if step.start_us != self.present_us:
            # Never bridge missing IMU silently. Caller must expose this failure.
            raise ValueError("eskf_body_history_gap")
        cutoff = step.end_us - self.horizon_us
        if sum(item.end_us > cutoff for item in self.steps) >= self.max_steps:
            self.overflows += 1
            raise ValueError("eskf_body_history_capacity")
        step.Interval_Apply(self.kernel, step.start_us, step.end_us)
        self.source, self.generation = step.source, step.generation
        self.present_us = step.end_us
        self.steps.append(step)
        self.checkpoints[step.end_us] = self.kernel.state.State_Clone()
        self.checkpoint_omega[step.end_us] = self.kernel.last_omega.copy()
        self.maximum_history = max(self.maximum_history, len(self.steps))
        cutoff = self.present_us - self.horizon_us
        while self.steps and self.steps[0].end_us <= cutoff:
            first = self.steps.pop(0)
            self.base_us = first.end_us
            self.base = self.checkpoints.pop(first.end_us)
            self.base_omega = self.checkpoint_omega.pop(first.end_us)
            self.measurements = [m for m in self.measurements if m.timestamp_us > self.base_us]
            keep = {m.key for m in self.measurements}
            self.results = {key: value for key, value in self.results.items() if key in keep}
            self.seen = keep
        if len(self.steps) > self.max_steps:
            self.overflows += 1
            raise ValueError("eskf_body_history_capacity")

    def _Measurement_Apply(self, measurement: Measurement) -> EskfMeasurementResult:
        for body in self.steps:
            if body.start_us <= measurement.timestamp_us <= body.end_us:
                second = (
                    measurement.timestamp_us - body.start_us > (body.end_us - body.start_us) // 2
                )
                self.kernel.last_omega = (body.gyro2 if second else body.gyro1).copy()
                break
        axes = ((0, 1), (2,), (0, 1), (2,), (2,))[measurement.group]
        kind = "velocity" if measurement.group in (2, 3) else "position"
        return self.kernel.Measurement_Apply(
            kind,
            axes,
            measurement.value,
            measurement.variance * measurement.quality_scale * measurement.consistency_scale,
            physically_valid=measurement.physically_valid,
            lever_arm=self.lever_arm if measurement.group != 4 else np.zeros(3),
            soft=self.soft[len(axes) - 1],
            hard=self.hard[len(axes) - 1],
            max_scale=self.max_r_scale,
        )

    def Measurement_Receive(self, measurement: Measurement) -> EskfMeasurementResult:
        if measurement.key in self.seen:
            raise ValueError("eskf_measurement_duplicate")
        self.seen.add(measurement.key)
        invalid = EskfMeasurementResult(
            EskfUpdateResult.HISTORY_MISS,
            np.full(measurement.value.shape, np.nan),
            np.nan,
            measurement.variance.copy(),
        )
        if (
            measurement.timestamp_us > self.present_us
            or measurement.receive_us > self.present_us
            or measurement.timestamp_us > measurement.receive_us
        ):
            return replace(invalid, result=EskfUpdateResult.TIMING_INVALID)
        if measurement.timestamp_us <= self.base_us:
            self.history_misses += 1
            return invalid
        if len(self.measurements) >= self.max_measurements:
            self.overflows += 1
            return replace(invalid, result=EskfUpdateResult.HISTORY_OVERFLOW)
        # Restore just before this insertion, retaining older accepted body and
        # observation transactions. Supervisor/counters live outside this loop.
        earlier = [t for t in self.checkpoints if t < measurement.timestamp_us]
        restore_us = max(earlier, default=self.base_us)
        before = self.kernel.state.State_Clone()
        before_omega = self.kernel.last_omega.copy()
        before_checkpoints = self.checkpoints.copy()
        before_checkpoint_omega = self.checkpoint_omega.copy()
        before_results = self.results.copy()
        self.kernel.state = self.checkpoints.get(restore_us, self.base).State_Clone()
        self.kernel.last_omega = self.checkpoint_omega.get(restore_us, self.base_omega).copy()
        self.measurements.append(measurement)
        operations = sorted(
            (m for m in self.measurements if m.timestamp_us > restore_us or m is measurement),
            key=lambda m: (m.timestamp_us, m.group, m.source, m.key),
        )
        index = count = 0
        try:
            for step in self.steps:
                if step.end_us <= restore_us:
                    continue
                cursor = step.start_us
                while index < len(operations) and operations[index].timestamp_us <= step.end_us:
                    item = operations[index]
                    step.Interval_Apply(self.kernel, cursor, item.timestamp_us)
                    cursor = item.timestamp_us
                    self.results[item.key] = self._Measurement_Apply(item)
                    index += 1
                    count += 1
                step.Interval_Apply(self.kernel, cursor, step.end_us)
                self.checkpoints[step.end_us] = self.kernel.state.State_Clone()
                self.checkpoint_omega[step.end_us] = self.kernel.last_omega.copy()
                count += 1
                if count > self.max_replay_steps:
                    raise ValueError("eskf_replay_step_limit")
            self.replay_steps += count
            self.maximum_replay_steps = max(self.maximum_replay_steps, count)
            return self.results[measurement.key]
        except Exception:
            self.kernel.state = before
            self.kernel.last_omega = before_omega
            self.checkpoints = before_checkpoints
            self.checkpoint_omega = before_checkpoint_omega
            self.results = before_results
            self.measurements.remove(measurement)
            raise
