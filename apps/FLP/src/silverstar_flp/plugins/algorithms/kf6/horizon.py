"""Bounded delayed KF primary and independent complete state/P output.

Not selected by the plugin resolver until the separate mode2 decoder contract
and input evidence are admitted. Receipts and immutable recovery certificates
are distinct from source-time numerical application. No output feeds primary.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import IntEnum

import numpy as np

from silverstar_flp.decoder_profiles.fusion_timing_records import (
    FusionExecutionResult,
    FusionSequenceTracker,
)
from silverstar_flp.plugins.algorithms.kf6.filter import (
    Kf6GnssEpoch,
    Kf6GnssGroup,
    Kf6UpdateResult,
    _ReacquireGroupState,
)
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import Filter_Clone


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


def _Unsigned(value, bits=32):
    return type(value) is int and 0 <= value < 1 << bits


def _Model(state):
    return (
        tuple(state.process_accel_std_mps2),
        tuple(state.nis_soft_threshold),
        tuple(state.nis_hard_threshold),
        state.nis_max_r_scale,
        state.nis_soft_enabled,
        state.nis_hard_enabled,
        state.algorithm_revision,
        state.require_effective_gain,
        state.gnss_reacquire_outage_ms,
    )


def _State_Validate(state):
    p = np.asarray(state.covariance)
    if (
        np.asarray(state.state).shape != (6,)
        or not np.isfinite(state.state).all()
        or p.shape != (6, 6)
        or not np.isfinite(p).all()
        or not np.array_equal(p, p.T)
    ):
        raise ValueError("kf_horizon_state_invalid")
    lower = np.zeros((6, 6), dtype=np.float32)
    for row in range(6):
        for column in range(row + 1):
            value = np.float32(p[row, column])
            for k in range(column):
                value = np.float32(value - np.float32(lower[row, k] * lower[column, k]))
            if row == column:
                if not np.isfinite(value) or value <= 0:
                    raise ValueError("kf_horizon_covariance_not_positive")
                lower[row, column] = np.sqrt(value)
            else:
                lower[row, column] = value / lower[column, column]
            if not np.isfinite(lower[row, column]):
                raise ValueError("kf_horizon_covariance_factor_invalid")


@dataclass(frozen=True, slots=True)
class KfHorizonBody:
    start_us: int
    end_us: int
    delta_velocity: np.ndarray
    original_dt_s: float
    source: int
    generation: int


@dataclass(frozen=True, slots=True)
class KfHorizonEvidence:
    availability_us: int = 0
    consistency_start_us: int = 0
    generation: int = 0
    consistent_count: int = 0
    outage: int = 0
    loss_latched: int = 0
    recovery_valid: int = 0
    consistency_valid: int = 0


@dataclass(frozen=True, slots=True)
class KfHorizonEvent:
    timestamp_us: int
    receive_us: int
    source_sequence: int
    operation_sequence: int
    epoch: int
    source: int
    generation: int
    group: int
    value: np.ndarray
    prepared_variance: np.ndarray
    physically_valid: int = 1
    evidence: KfHorizonEvidence = KfHorizonEvidence()


@dataclass(frozen=True, slots=True)
class KfHorizonOutcome:
    result: Kf6UpdateResult
    nis: float
    innovation: np.ndarray
    effective_variance: np.ndarray
    robust_scale: float
    effective_update: bool


class DelayedKfHorizon:
    BODY_CAPACITY = 160
    EVENT_CAPACITY = 64
    MAX_WORK = 2 * BODY_CAPACITY + 3 * EVENT_CAPACITY

    def __init__(self, state, start_us, *, epoch, source, generation, horizon_us):
        if (
            not _Unsigned(start_us, 64)
            or start_us == 0
            or not _Unsigned(epoch)
            or not _Unsigned(source)
            or not _Unsigned(generation)
            or type(horizon_us) is not int
            or not 10000 <= horizon_us <= 550000
        ):
            raise ValueError("kf_horizon_configuration_invalid")
        _State_Validate(state)
        if (
            state.algorithm_revision != 2
            or not np.isfinite(state.process_accel_std_mps2).all()
            or np.any(state.process_accel_std_mps2 <= 0)
            or np.any(state.nis_soft_threshold <= 0)
            or not np.isfinite(state.nis_soft_threshold).all()
            or not np.isfinite(state.nis_hard_threshold).all()
            or np.any(state.nis_hard_threshold <= state.nis_soft_threshold)
            or not np.isfinite(state.nis_max_r_scale)
            or state.nis_max_r_scale < 1
        ):
            raise ValueError("kf_horizon_model_invalid")
        self.primary = Filter_Clone(state)
        self.output = Filter_Clone(state)
        self.trackers = [Filter_Clone(state) for _ in range(4)]
        self.initial_us = self.present_us = self.primary_us = self.output_us = start_us
        self.epoch, self.source, self.generation, self.horizon_us = (
            epoch,
            source,
            generation,
            horizon_us,
        )
        self._model = _Model(state)
        self.steps, self.measurements, self.completions = [], [], []
        self.applied_source = [0xFFFFFFFF] * 4
        self._receipts = FusionSequenceTracker()
        self._last_receive = [0] * 4
        self.output_acceleration = np.zeros(3, dtype=np.float32)
        self.last_work = self.maximum_work = self.late_count = self.capacity_count = 0
        self.failure_operation = None
        self.faulted = False
        self.warmup = True

    def _Fault(self, result):
        self.faulted = True
        return result

    def _Ready(self):
        if self.faulted:
            return HorizonResult.NOT_READY
        if (
            not self.initial_us <= self.primary_us <= self.output_us <= self.present_us
            or len(self.steps) > self.BODY_CAPACITY
            or len(self.measurements) > self.EVENT_CAPACITY
            or len(self.completions) > len(self.measurements)
        ):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        try:
            _State_Validate(self.primary)
            if _Model(self.primary) != self._model or _Model(self.trackers[0]) != self._model:
                raise ValueError("kf_horizon_model_corruption")
        except (ValueError, TypeError, AttributeError, FloatingPointError):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        return HorizonResult.OK

    def Body_Receive(self, body):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if (body.source, body.generation) != (self.source, self.generation):
            return self._Fault(HorizonResult.EPOCH_MISMATCH)
        delta = np.asarray(body.delta_velocity, dtype=np.float32)
        dt = np.float32(body.original_dt_s)
        if (
            not _Unsigned(body.start_us, 64)
            or not _Unsigned(body.end_us, 64)
            or body.start_us != self.present_us
            or body.end_us <= body.start_us
            or not np.isfinite(dt)
            or not 0 < dt <= np.float32(0.1)
            or abs(np.float32(body.end_us - body.start_us) * np.float32(1e-6) - dt)
            > np.float32(2e-6)
            or delta.shape != (3,)
            or not np.isfinite(delta).all()
        ):
            return self._Fault(HorizonResult.DISCONTINUITY)
        if len(self.steps) == self.BODY_CAPACITY:
            self.capacity_count += 1
            return self._Fault(HorizonResult.CAPACITY)
        owned = delta.copy()
        owned.setflags(write=False)
        self.steps.append(replace(body, delta_velocity=owned, original_dt_s=dt))
        self.present_us = body.end_us
        return HorizonResult.OK

    def Receive_Track(self, receive_epoch, *, sequence, source, generation):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready, ()
        if self.completions:
            return HorizonResult.BUSY, ()
        if (
            not _Unsigned(source)
            or source >= 4
            or not _Unsigned(receive_epoch.valid_group_mask)
            or receive_epoch.valid_group_mask > 15
        ):
            return HorizonResult.INVALID, ()
        if generation != self.generation or receive_epoch.timestamp_us < self.initial_us:
            return HorizonResult.EPOCH_MISMATCH, ()
        try:
            _State_Validate(self.trackers[source])
            if _Model(self.trackers[source]) != self._model:
                raise ValueError("kf_horizon_tracker_model_invalid")
        except (ValueError, TypeError, AttributeError, FloatingPointError):
            return self._Fault(HorizonResult.NUMERIC_ERROR), ()
        result = self._Receipt_Check("gnss", source, sequence, 128)
        if result != HorizonResult.OK:
            return result, ()
        if not self._last_receive[source] < receive_epoch.timestamp_us <= self.present_us:
            return HorizonResult.INVALID, ()
        if self.present_us - receive_epoch.timestamp_us > 500000:
            return HorizonResult.STALE, ()
        tracker = self.trackers[source]
        tracker.Kf6_GnssEpochTrack(receive_epoch)
        evidence = tuple(
            KfHorizonEvidence(
                g.availability_timestamp_us,
                g.consistency_start_us,
                g.generation,
                g.consistent_count,
                int(g.outage),
                int(g.loss_latched),
                int(bool(tracker._previous_epoch.valid_group_mask & (1 << i))),
                int(g.consistent_count > 0),
            )
            for i, g in enumerate(tracker._reacquire_groups)
        )
        self._receipts.Commit("gnss", source, sequence, 128)
        self._last_receive[source] = receive_epoch.timestamp_us
        return HorizonResult.OK, evidence

    def _Receipt_Check(self, namespace, source, sequence, mask):
        result = self._receipts.Check(namespace, source, sequence, mask)
        return {
            FusionExecutionResult.COMPLETE: HorizonResult.OK,
            FusionExecutionResult.DUPLICATE: HorizonResult.DUPLICATE,
            FusionExecutionResult.DISCONTINUITY: HorizonResult.DISCONTINUITY,
        }.get(result, HorizonResult.INVALID)

    def _Event_Validate(self, event):
        if (
            not _Unsigned(event.group)
            or event.group >= 5
            or not _Unsigned(event.source)
            or event.source >= 4
            or event.group == 4
            and event.source != 1
            or event.physically_valid not in (0, 1)
            or not _Unsigned(event.timestamp_us, 64)
            or not _Unsigned(event.receive_us, 64)
            or not 0 < event.timestamp_us <= event.receive_us <= self.present_us
            or not _Unsigned(event.operation_sequence)
        ):
            return HorizonResult.INVALID
        if (event.epoch, event.generation) != (
            self.epoch,
            self.generation,
        ) or event.timestamp_us < self.initial_us:
            return HorizonResult.EPOCH_MISMATCH
        if (
            self.present_us - event.timestamp_us > 600000
            or self.present_us - event.receive_us > 500000
        ):
            return HorizonResult.STALE
        e = event.evidence
        if (
            not all(_Unsigned(v, 64) for v in (e.availability_us, e.consistency_start_us))
            or not all(_Unsigned(v) for v in (e.generation, e.consistent_count))
            or any(
                v not in (0, 1)
                for v in (e.outage, e.loss_latched, e.recovery_valid, e.consistency_valid)
            )
        ):
            return HorizonResult.INVALID
        dimension = 2 if event.group in (0, 2) else 1
        try:
            with np.errstate(over="raise", invalid="raise"):
                value = np.asarray(event.value, dtype=np.float32)
                variance = np.asarray(event.prepared_variance, dtype=np.float32)
            if (
                value.shape != (2,)
                or variance.shape != (2,)
                or not np.isfinite(value[:dimension]).all()
                or not np.isfinite(variance[:dimension]).all()
                or np.any(variance[:dimension] <= 0)
            ):
                return HorizonResult.INVALID
        except (TypeError, ValueError, OverflowError, FloatingPointError):
            return HorizonResult.INVALID
        return HorizonResult.OK

    def Insert(self, event):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if not self.steps:
            return HorizonResult.NOT_READY
        result = self._Event_Validate(event)
        if result != HorizonResult.OK:
            return result
        namespace, mask = ("baro" if event.group == 4 else "gnss"), 1 << event.group
        result = self._Receipt_Check(namespace, event.source, event.source_sequence, mask)
        if result != HorizonResult.OK:
            return result
        self._receipts.Commit(namespace, event.source, event.source_sequence, mask)
        if not event.physically_valid:
            return HorizonResult.INVALID
        if event.timestamp_us < self.primary_us:
            self.late_count += 1
            return HorizonResult.LATE
        if len(self.measurements) == self.EVENT_CAPACITY:
            self.capacity_count += 1
            return HorizonResult.CAPACITY
        value = np.array(event.value, dtype=np.float32, copy=True)
        variance = np.array(event.prepared_variance, dtype=np.float32, copy=True)
        value.setflags(write=False)
        variance.setflags(write=False)
        self.measurements.append(replace(event, value=value, prepared_variance=variance))
        self.measurements.sort(key=lambda e: (e.timestamp_us, e.group))
        return HorizonResult.QUEUED

    def _Propagate(self, state, cursor, target):
        for step in self.steps:
            if cursor == target:
                break
            if step.end_us <= cursor:
                continue
            if cursor < step.start_us or target < cursor:
                raise ValueError("kf_horizon_body_gap")
            end = min(target, step.end_us)
            fraction = np.float32(end - cursor) / np.float32(step.end_us - step.start_us)
            dt = (
                step.original_dt_s
                if cursor == step.start_us and end == step.end_us
                else np.float32(end - cursor) * np.float32(1e-6)
            )
            self.last_work += 1
            if self.last_work > self.MAX_WORK or not state.Kf6_Predict(
                step.delta_velocity * fraction, dt, step.original_dt_s
            ):
                raise ValueError("kf_horizon_prediction_failed")
            cursor = end
        if cursor != target:
            raise ValueError("kf_horizon_body_gap")
        return cursor

    def _Evidence_Apply(self, state, sources, event):
        group, source = event.group, event.evidence
        target = state._reacquire_groups[group]
        if sources[group] != event.source or target.generation != source.generation:
            target = _ReacquireGroupState(generation=source.generation, outage=bool(source.outage))
            state._reacquire_groups[group] = target
            state.reacquire_active_mask &= ~(1 << group)
        sources[group] = event.source
        target.availability_timestamp_us = source.availability_us
        target.consistency_start_us = source.consistency_start_us
        target.loss_latched = bool(source.loss_latched)
        target.consistent_count = source.consistent_count
        if not source.recovery_valid:
            target.reject_streak = target.accepted_streak = 0
        valid = state._previous_epoch.valid_group_mask if state._previous_epoch else 0
        valid = (valid & ~(1 << group)) | (int(source.recovery_valid) << group)
        empty = np.zeros(3, dtype=np.float32)
        state._previous_epoch = Kf6GnssEpoch(event.receive_us, empty, empty, empty, empty, valid)

    def _Measurement_Apply(self, state, sources, event):
        self.last_work += 1
        if self.last_work > self.MAX_WORK:
            raise ValueError("kf_horizon_work_limit")
        innovation, effective = np.zeros(2, dtype=np.float32), np.zeros(2, dtype=np.float32)
        if event.group == 4:
            innovation[0] = event.value[0] - state.state[2]
            result = state.Kf6_UpdateBaro(event.value[0], event.prepared_variance[0])
            nis = state.last_baro_nis
            effective[0] = event.prepared_variance[0]
            if result == Kf6UpdateResult.SOFT_WEIGHTED:
                effective[0] *= min(state.nis_max_r_scale, nis / state.nis_soft_threshold[0])
        else:
            self._Evidence_Apply(state, sources, event)
            group = Kf6GnssGroup(event.group)
            axis, dimension = (2, 1) if event.group & 1 else (0, 2)
            value, variance = np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32)
            value[axis : axis + dimension] = event.value[:dimension]
            variance[axis : axis + dimension] = event.prepared_variance[:dimension]
            result = state.Kf6_GroupUpdate(group, value, variance)
            nis = state.last_group_nis[event.group]
            prefix = "last_position" if event.group < 2 else "last_velocity"
            innovation[:dimension] = getattr(state, prefix + "_innovation")[axis : axis + dimension]
            effective[:dimension] = getattr(state, prefix + "_effective_variance")[
                axis : axis + dimension
            ]
            result = state.Kf6_GroupRecover(group, result, value, variance, event.receive_us)
        if result == Kf6UpdateResult.NUMERIC_ERROR:
            raise ValueError("kf_horizon_measurement_failed")
        _State_Validate(state)
        return KfHorizonOutcome(
            result,
            float(nis),
            innovation,
            effective,
            float(effective[0] / event.prepared_variance[0]),
            result in (Kf6UpdateResult.ACCEPTED, Kf6UpdateResult.SOFT_WEIGHTED),
        )

    def Advance(self):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready
        if self.completions:
            return HorizonResult.BUSY
        if not self.steps:
            return HorizonResult.NOT_READY
        try:
            same_model = _Model(self.output) == self._model
        except (TypeError, ValueError, AttributeError):
            same_model = False
        if not same_model:
            return self._Fault(HorizonResult.EPOCH_MISMATCH)
        target = max(self.initial_us, self.present_us - self.horizon_us)
        candidate, sources = Filter_Clone(self.primary), list(self.applied_source)
        cursor, completed = self.primary_us, []
        self.last_work, self.failure_operation = 0, None
        try:
            acceleration = self.output_acceleration.copy()
            duration, delta = np.float32(0), np.zeros(3, dtype=np.float32)
            for step in self.steps:
                if step.end_us > self.output_us:
                    if step.start_us < self.output_us:
                        raise ValueError("kf_horizon_output_boundary_invalid")
                    duration = np.float32(duration + step.original_dt_s)
                    delta += step.delta_velocity
            if self.present_us != self.output_us:
                if not np.isfinite(duration) or duration <= 0:
                    raise ValueError("kf_horizon_acceleration_duration_invalid")
                acceleration = delta / duration
            if not np.isfinite(acceleration).all():
                raise ValueError("kf_horizon_acceleration_invalid")
            for event in self.measurements:
                if event.timestamp_us > target:
                    break
                self.failure_operation = event.operation_sequence
                if self._Event_Validate(event) != HorizonResult.OK:
                    raise ValueError("kf_horizon_stored_event_invalid")
                cursor = self._Propagate(candidate, cursor, event.timestamp_us)
                completed.append((event, self._Measurement_Apply(candidate, sources, event)))
            self.failure_operation = None
            self._Propagate(candidate, cursor, target)
            output = Filter_Clone(candidate)
            self._Propagate(output, target, self.present_us)
            _State_Validate(output)
        except (ValueError, TypeError, AttributeError, FloatingPointError, np.linalg.LinAlgError):
            return self._Fault(HorizonResult.NUMERIC_ERROR)
        self.primary, self.primary_us = candidate, target
        self.output, self.output_us = output, self.present_us
        self.applied_source, self.output_acceleration = sources, acceleration
        self.completions = completed
        self.warmup = self.present_us - self.initial_us < self.horizon_us
        self.maximum_work = max(self.maximum_work, self.last_work)
        self.steps = [step for step in self.steps if step.end_us > target]
        return HorizonResult.WARMUP if self.warmup else HorizonResult.OK

    def Completion_Pop(self):
        ready = self._Ready()
        if ready != HorizonResult.OK:
            return ready, None
        if not self.completions:
            return HorizonResult.EMPTY, None
        result = self.completions.pop(0)
        if not self.completions:
            count = 0
            while (
                count < len(self.measurements)
                and self.measurements[count].timestamp_us <= self.primary_us
            ):
                count += 1
            self.measurements = self.measurements[count:]
        return HorizonResult.OK, deepcopy(result)
