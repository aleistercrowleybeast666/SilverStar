"""Forward-only delayed primary and independent complete-P output predictor.

Contract implementation only; the plugin resolver does not activate mode 2 yet.
No existing Recorded Configuration, source log or v2 wire contract is changed.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, replace
from enum import IntEnum

import numpy as np

from silverstar_flp.decoder_profiles.fusion_timing_records import (
    FusionExecutionResult,
    FusionSequenceTracker,
)
from silverstar_flp.plugins.algorithms.eskf15.filter import Covariance_Validate, EskfUpdateResult
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, Measurement


class HorizonResult(IntEnum):
    OK = 0
    QUEUED = 1
    WARMUP = 2
    INVALID = 3
    STALE = 4
    LATE = 5
    CAPACITY = 6
    DUPLICATE = 7
    EPOCH_MISMATCH = 8
    DISCONTINUITY = 9
    NUMERIC_ERROR = 10
    MODEL_MISMATCH = 11
    NOT_READY = 12
    BUSY = 13
    EMPTY = 14


@dataclass(frozen=True, slots=True)
class HorizonBody(BodyStep):
    original_dt_s: float | None = None

    def Interval_Apply(self, kernel, start_us, end_us):
        if (
            (self.quality_flags or 0) & 0x72
            or self.original_dt_s is not None
            and (
                not np.isfinite(self.original_dt_s)
                or not 0 < self.original_dt_s <= 0.02
                or abs((self.end_us - self.start_us) * 1e-6 - self.original_dt_s) > 2e-6
            )
        ):
            raise ValueError("horizon_stored_body_invalid")
        if start_us == self.start_us and end_us == self.end_us and self.original_dt_s is not None:
            noise = 4.0 if (self.quality_flags or 0) & 0x05 else 1.0
            kernel.Prediction_ApplyPair(
                self.gyro1,
                self.accel1,
                self.original_dt_s / 2,
                self.gyro2,
                self.accel2,
                self.original_dt_s / 2,
                process_noise_scale=noise,
            )
        else:
            BodyStep.Interval_Apply(self, kernel, start_us, end_us)


@dataclass(frozen=True, slots=True)
class HorizonMeasurement(Measurement):
    # Exact recorded binary32 R already includes quality/consistency factors.
    prepared_variance: np.ndarray | None = None


def _PreparedVariance_Get(event):
    prepared = getattr(event, "prepared_variance", None)
    return (
        np.asarray(prepared)
        if prepared is not None
        else np.asarray(event.variance) * event.quality_scale * event.consistency_scale
    )


def _Nominal_Validate(state):
    for name, size in (("p", 3), ("v", 3), ("q", 4), ("bg", 3), ("ba", 3)):
        value = np.asarray(getattr(state, name))
        if value.shape != (size,) or not np.isfinite(value).all():
            raise ValueError("horizon_nominal_invalid:" + name)
    if (
        abs(float(state.q @ state.q) - 1) > 0.002001
        or np.linalg.norm(state.bg) > 1
        or np.linalg.norm(state.ba) > 5
    ):
        raise ValueError("horizon_nominal_contract_invalid")
    Covariance_Validate(state.covariance)


def _Integer_Valid(value, maximum=0xFFFFFFFF):
    return type(value) is int and 0 <= value <= maximum


class DelayedHorizon:
    BODY_CAPACITY = 160
    EVENT_CAPACITY = 64
    MAX_WORK = 4 * BODY_CAPACITY + 3 * EVENT_CAPACITY

    def __init__(
        self,
        kernel,
        start_us,
        *,
        epoch,
        horizon_us,
        source=0,
        generation=1,
        soft=(6.635, 9.21),
        hard=(10.828, 13.816),
        max_r_scale=4.0,
        soft_enabled=True,
        hard_enabled=True,
        lever_arm=None,
    ):
        if (
            not _Integer_Valid(start_us, 0xFFFFFFFFFFFFFFFF)
            or not _Integer_Valid(epoch)
            or not _Integer_Valid(source)
            or not _Integer_Valid(generation)
            or type(horizon_us) is not int
            or not 10000 <= horizon_us <= 550000
        ):
            raise ValueError("horizon_configuration_invalid")
        _Nominal_Validate(kernel.state)
        self.kernel = kernel
        self.primary = kernel.state.State_Clone()
        self._last_output = kernel.state.State_Clone()
        self.output_acceleration = np.zeros(3)
        self.initial_us = self.primary_us = self.present_us = self.output_us = start_us
        self.epoch, self.source, self.generation = epoch, source, generation
        self.horizon_us = horizon_us
        self.soft, self.hard, self.max_r_scale = tuple(soft), tuple(hard), max_r_scale
        if (
            len(self.soft) != 2
            or len(self.hard) != 2
            or not np.isfinite([*self.soft, *self.hard, max_r_scale]).all()
            or any(not 0 < low < high for low, high in zip(self.soft, self.hard, strict=True))
            or max_r_scale < 1
            or type(soft_enabled) is not bool
            or type(hard_enabled) is not bool
        ):
            raise ValueError("horizon_gates_invalid")
        self.soft_enabled, self.hard_enabled = soft_enabled, hard_enabled
        self.lever_arm = np.zeros(3) if lever_arm is None else np.asarray(lever_arm).copy()
        if self.lever_arm.shape != (3,) or not np.isfinite(self.lever_arm).all():
            raise ValueError("horizon_lever_arm_invalid")
        self._policy = (
            self.soft,
            self.hard,
            max_r_scale,
            soft_enabled,
            hard_enabled,
            tuple(self.lever_arm),
        )
        self._model = (kernel.gravity, kernel.noise)
        self.steps = []
        self.measurements = []
        self.completions = []
        self._sequence = FusionSequenceTracker()
        self.endpoint_rate = None
        self.endpoint_us = start_us
        self.body_seen = self.faulted = False
        self.warmup = True
        self.last_work = self.maximum_work = self.late_count = self.capacity_count = 0

    def _Fault(self, reason):
        self.faulted = True
        return reason

    def _Ready(self):
        if self.faulted:
            return HorizonResult.NOT_READY
        if (
            not self.initial_us <= self.primary_us <= self.present_us
            or len(self.steps) > self.BODY_CAPACITY
            or len(self.measurements) > self.EVENT_CAPACITY
        ):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        try:
            _Nominal_Validate(self.primary)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        return HorizonResult.OK

    def Body_Receive(self, step):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if step.source != self.source or step.generation != self.generation:
            return self._Fault(HorizonResult.EPOCH_MISMATCH)
        dt = step.original_dt_s if isinstance(step, HorizonBody) else None
        if dt is None:
            dt = (step.end_us - step.start_us) * 1e-6
        raw = [np.asarray(getattr(step, name)) for name in ("gyro1", "gyro2", "accel1", "accel2")]
        if (
            not _Integer_Valid(step.start_us, 0xFFFFFFFFFFFFFFFF)
            or not _Integer_Valid(step.end_us, 0xFFFFFFFFFFFFFFFF)
            or step.start_us != self.present_us
            or step.end_us <= step.start_us
            or dt is None
            or not np.isfinite(dt)
            or not 0 < dt <= 0.02
            or abs((step.end_us - step.start_us) * 1e-6 - dt) > 2e-6
            or (step.quality_flags or 0) & 0x72
            or self.body_seen
            and (step.quality_flags or 0) & 0x08
            or any(value.shape != (3,) or not np.isfinite(value).all() for value in raw)
        ):
            return self._Fault(HorizonResult.DISCONTINUITY)
        if len(self.steps) == self.BODY_CAPACITY:
            self.capacity_count += 1
            return self._Fault(HorizonResult.CAPACITY)
        stored = HorizonBody(
            step.start_us,
            step.end_us,
            raw[0].copy(),
            raw[2].copy(),
            raw[1].copy(),
            raw[3].copy(),
            step.source,
            step.generation,
            step.quality_flags,
            float(dt),
        )
        self.steps.append(stored)
        self.present_us, self.body_seen = step.end_us, True
        return HorizonResult.OK

    def _Admission_Get(self, event):
        if (
            not _Integer_Valid(event.group)
            or event.group >= 5
            or not _Integer_Valid(event.source)
            or event.source >= 4
            or event.group == 4
            and event.source != 1
            or type(event.physically_valid) not in (bool, int)
            or event.physically_valid not in (0, 1)
            or not _Integer_Valid(event.timestamp_us, 0xFFFFFFFFFFFFFFFF)
            or event.timestamp_us == 0
            or not _Integer_Valid(event.receive_us, 0xFFFFFFFFFFFFFFFF)
            or event.receive_us == 0
            or not _Integer_Valid(event.source_sequence)
            or not event.timestamp_us <= event.receive_us <= self.present_us
        ):
            return HorizonResult.INVALID
        if (
            event.generation != self.generation
            or event.mission_epoch != self.epoch
            or event.timestamp_us < self.initial_us
            or event.receive_us < self.initial_us
        ):
            return HorizonResult.EPOCH_MISMATCH
        if (
            self.present_us - event.timestamp_us > 600000
            or self.present_us - event.receive_us > 500000
        ):
            return HorizonResult.STALE
        dimension = 2 if event.group in (0, 2) else 1
        z, r = np.asarray(event.value), np.asarray(event.variance)
        effective = _PreparedVariance_Get(event)
        if (
            z.shape != (dimension,)
            or r.shape != (dimension,)
            or not np.isfinite(z).all()
            or not np.isfinite([event.quality_scale, event.consistency_scale]).all()
            or event.quality_scale <= 0
            or event.consistency_scale <= 0
            or not (r > 0).all()
            or effective.shape != (dimension,)
            or not np.isfinite(effective).all()
            or not (effective > 0).all()
        ):
            return HorizonResult.INVALID
        return HorizonResult.OK

    def Measurement_Receive(self, event):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if not self.body_seen:
            return HorizonResult.NOT_READY
        ready = self._Admission_Get(event)
        if ready != HorizonResult.OK:
            return ready
        namespace, mask = ("baro" if event.group == 4 else "gnss"), 1 << event.group
        receipt = self._sequence.Check(namespace, event.source, event.source_sequence, mask)
        if receipt != FusionExecutionResult.COMPLETE:
            return {
                FusionExecutionResult.DUPLICATE: HorizonResult.DUPLICATE,
                FusionExecutionResult.DISCONTINUITY: HorizonResult.DISCONTINUITY,
            }.get(receipt, HorizonResult.INVALID)
        self._sequence.Commit(namespace, event.source, event.source_sequence, mask)
        if not event.physically_valid:
            return HorizonResult.INVALID
        if event.timestamp_us < self.primary_us:
            self.late_count += 1
            return HorizonResult.LATE
        if len(self.measurements) == self.EVENT_CAPACITY:
            self.capacity_count += 1
            return HorizonResult.CAPACITY
        owned = replace(event, value=event.value.copy(), variance=event.variance.copy())
        if isinstance(event, HorizonMeasurement) and event.prepared_variance is not None:
            owned = replace(owned, prepared_variance=event.prepared_variance.copy())
        self.measurements.append(owned)
        # Stable sort preserves actual receive order across uint32 sequence wrap.
        self.measurements.sort(key=lambda item: (item.timestamp_us, item.group))
        return HorizonResult.QUEUED

    def _Kernel_Create(self, state):
        candidate = copy(self.kernel)
        candidate.state = state.State_Clone()
        candidate.last_omega = np.zeros(3)
        return candidate

    def _Propagate(self, candidate, current_us, target_us):
        for step in self.steps:
            if current_us == target_us:
                break
            if step.end_us <= current_us:
                continue
            if current_us < step.start_us or target_us < current_us:
                raise ValueError("horizon_body_gap")
            target = min(target_us, step.end_us)
            if current_us == step.start_us and target == step.end_us:
                self.last_work += 1
            else:
                middle = step.start_us + (step.end_us - step.start_us) // 2
                self.last_work += int(current_us < middle and target > current_us)
                self.last_work += int(target > max(current_us, middle))
            if self.last_work > self.MAX_WORK:
                raise ValueError("horizon_work_limit")
            step.Interval_Apply(candidate, current_us, target)
            current_us = target
        if current_us != target_us:
            raise ValueError("horizon_body_gap")
        return current_us

    def _AngularRate_Get(self, timestamp_us):
        if timestamp_us == self.endpoint_us and self.endpoint_rate is not None:
            return self.endpoint_rate.copy()
        for step in self.steps:
            if step.start_us <= timestamp_us <= step.end_us:
                middle = step.start_us + (step.end_us - step.start_us) // 2
                return (step.gyro1 if timestamp_us <= middle else step.gyro2).copy()
        raise ValueError("horizon_angular_rate_missing")

    def _Measurement_Apply(self, candidate, event):
        candidate.last_omega = (
            self._AngularRate_Get(event.timestamp_us) if event.group != 4 else np.zeros(3)
        )
        axes = ((0, 1), (2,), (0, 1), (2,), (2,))[event.group]
        self.last_work += 1
        if self.last_work > self.MAX_WORK:
            raise ValueError("horizon_work_limit")
        return candidate.Measurement_Apply(
            "velocity" if event.group in (2, 3) else "position",
            axes,
            event.value,
            _PreparedVariance_Get(event),
            physically_valid=True,
            lever_arm=self.lever_arm if event.group != 4 else np.zeros(3),
            soft=self.soft[len(axes) - 1],
            hard=self.hard[len(axes) - 1],
            max_scale=self.max_r_scale,
            soft_enabled=self.soft_enabled,
            hard_enabled=self.hard_enabled,
        )

    def Advance(self):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if not self.body_seen:
            return HorizonResult.NOT_READY
        if (self.kernel.gravity, self.kernel.noise) != self._model or (
            self.soft,
            self.hard,
            self.max_r_scale,
            self.soft_enabled,
            self.hard_enabled,
            tuple(self.lever_arm),
        ) != self._policy:
            return self._Fault(HorizonResult.EPOCH_MISMATCH)
        target = max(self.initial_us, self.present_us - self.horizon_us)
        candidate = self._Kernel_Create(self.primary)
        completed, cursor = [], self.primary_us
        self.last_work = 0
        try:
            # Derive physical acceleration before deferred measurement changes.
            # The independent output state/P below is still rebuilt from primary.
            acceleration = self.output_acceleration.copy()
            if self.output_us != self.present_us:
                predicted = self._Kernel_Create(self._last_output)
                _Nominal_Validate(predicted.state)
                duration = sum(
                    step.original_dt_s for step in self.steps if step.end_us > self.output_us
                )
                if (
                    not np.isfinite(duration)
                    or duration <= 0
                    or any(step.start_us < self.output_us < step.end_us for step in self.steps)
                ):
                    raise ValueError("horizon_previous_output_boundary_invalid")
                self._Propagate(predicted, self.output_us, self.present_us)
                acceleration = (predicted.state.v - self._last_output.v) / duration
            if not np.isfinite(acceleration).all():
                raise ValueError("horizon_output_acceleration_invalid")
            for event in self.measurements:
                if event.timestamp_us > target:
                    break
                cursor = self._Propagate(candidate, cursor, event.timestamp_us)
                outcome = self._Measurement_Apply(candidate, event)
                if outcome.result == EskfUpdateResult.MODEL_MISMATCH:
                    return self._Fault(HorizonResult.MODEL_MISMATCH)
                if outcome.result == EskfUpdateResult.NUMERIC_ERROR:
                    return self._Fault(HorizonResult.NUMERIC_ERROR)
                completed.append((event, outcome))
            self._Propagate(candidate, cursor, target)
            _Nominal_Validate(candidate.state)
            output = self._Kernel_Create(candidate.state)
            self._Propagate(output, target, self.present_us)
            _Nominal_Validate(output.state)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        self.primary, self.primary_us = candidate.state, target
        self.output_us = self.present_us
        self.kernel.state, self.kernel.last_omega = output.state, output.last_omega
        self._last_output = output.state.State_Clone()
        self.output_acceleration = acceleration
        self.completions = completed
        if not completed:
            self.measurements = [
                event for event in self.measurements if event.timestamp_us > target
            ]
        while self.steps and self.steps[0].end_us <= target:
            removed = self.steps.pop(0)
            self.endpoint_us, self.endpoint_rate = removed.end_us, removed.gyro2.copy()
        self.warmup = self.present_us - self.initial_us < self.horizon_us
        self.maximum_work = max(self.maximum_work, self.last_work)
        return HorizonResult.WARMUP if self.warmup else HorizonResult.OK

    def Completion_Pop(self):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready, None
        if not self.completions:
            return HorizonResult.EMPTY, None
        event, outcome = self.completions[0]
        if not self.measurements or self.measurements[0] is not event:
            return self._Fault(HorizonResult.NUMERIC_ERROR), None
        self.completions.pop(0)
        self.measurements.pop(0)
        return HorizonResult.OK, (event, outcome)

    def Audit_Get(self):
        return dict(
            primary_us=self.primary_us,
            output_state_us=self.output_us,
            output_covariance_us=self.output_us,
            warmup=self.warmup,
            faulted=self.faulted,
            body_count=len(self.steps),
            event_count=len(self.measurements),
            completion_count=len(self.completions),
            last_work=self.last_work,
            maximum_work=self.maximum_work,
            late_count=self.late_count,
            capacity_count=self.capacity_count,
            history_replay_count=0,
        )
