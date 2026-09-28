"""FCCG fixed-lag contract: receive evidence once, historical x/P/internal state.

No clock mapping is performed here. Timestamps are the recorded resolved MCU times.
Checkpoints precede measurements at the same time, exactly as in the C engine.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from enum import IntEnum

import numpy as np

from silverstar_flp.core.math import (
    Quaternion_PropagateBodyIncrement,
    Quaternion_RotateVector,
)
from silverstar_flp.plugins.algorithms.kf6.filter import (
    Kf6Filter,
    Kf6GnssEpoch,
    Kf6GnssGroup,
    Kf6UpdateResult,
    _ReacquireGroupState,
)


class ReplayResult(IntEnum):
    OK = 0
    INVALID = 1
    HISTORY_MISS = 2
    OVERFLOW = 3
    EPOCH_MISMATCH = 4
    DISCONTINUITY = 5
    NUMERIC_ERROR = 6
    WORK_LIMIT = 7


def Filter_Clone(state):
    result = copy(state)
    for key, value in vars(state).items() if hasattr(state, '__dict__') else (
        (name, getattr(state, name)) for name in state.__dataclass_fields__
    ):
        if isinstance(value, np.ndarray):
            setattr(result, key, value.copy())
        elif isinstance(value, (dict, list)):
            # Distribution samples are reporting buffers, never estimator state.
            setattr(
                result,
                key,
                [[] for _ in range(4)] if key == "gnss_nis_samples" else deepcopy(value),
            )
    return result


@dataclass
class ReplayEvent:
    measurement_us: int
    receive_us: int
    sequence: int
    kind: int
    epoch: int
    payload: dict
    evidence: tuple = ()
    valid_mask: int = 0
    recovery_mask: int = 0

    def Order_Get(self):
        rank = 3 if self.kind == 8 else 0 if self.kind & 1 else 1 if self.kind & 2 else 2
        return self.measurement_us, rank, int(self.kind == 4), self.sequence


class FixedLagReplay:
    WINDOW_US = 600_000
    MAX_STEPS = 560

    def __init__(self, state, timestamp_us=0, epoch=1):
        self.state = Filter_Clone(state)
        self.tracker = Filter_Clone(state)
        self.epoch = epoch
        self.present = self.start = timestamp_us
        self.checkpoints = [(timestamp_us, Filter_Clone(state))]
        self.imu = []
        self.events = []
        self.predictions = self.replays = 0
        self.faulted = False
        self.last_outcome = {}

    def _ModelMatches(self):
        initial = self.checkpoints[0][1]
        return all(np.array_equal(getattr(initial, field), getattr(self.state, field))
                   for field in ('process_accel_std_mps2', 'nis_soft_threshold',
                                 'nis_hard_threshold', 'nis_max_r_scale',
                                 'require_effective_gain'))

    def _Prune(self):
        while len(self.checkpoints) > 1 and self.checkpoints[1][0] <= self.present - self.WINDOW_US:
            self.checkpoints.pop(0)
        oldest = self.checkpoints[0][0]
        self.imu = [item for item in self.imu if item[1] > oldest]
        self.events = [item for item in self.events if item.measurement_us >= oldest]

    def Predict(self, timestamp_us, delta, dt):
        dt = np.float32(dt)
        delta = np.asarray(delta, dtype=np.float32)
        if (
            self.faulted
            or not np.isfinite(dt)
            or not 0 < dt <= np.float32(0.1)
            or not np.isfinite(delta).all()
        ):
            return ReplayResult.INVALID
        if not self._ModelMatches():
            self.faulted = True
            return ReplayResult.EPOCH_MISMATCH
        duration = int(float(dt) * 1_000_000 + .5)
        if self.predictions == 0 and self.present == 0 and timestamp_us >= duration:
            self.present = self.start = timestamp_us - duration
            self.checkpoints[0] = (self.start, self.checkpoints[0][1])
        if timestamp_us <= self.present or abs(timestamp_us - self.present - duration) > 1:
            self.faulted = True
            return ReplayResult.DISCONTINUITY
        self._Prune()
        if len(self.imu) >= 144 or (
            (self.predictions + 1) % 18 == 0 and len(self.checkpoints) >= 8
        ):
            self.faulted = True
            return ReplayResult.OVERFLOW
        working = Filter_Clone(self.state)
        if not working.Kf6_Predict(delta, dt):
            self.faulted = True
            return ReplayResult.NUMERIC_ERROR
        self.imu.append((self.present, timestamp_us, delta.copy(), dt))
        self.present = timestamp_us
        self.predictions += 1
        self.state = working
        if self.predictions % 18 == 0:
            self.checkpoints.append((timestamp_us, Filter_Clone(working)))
            self._Prune()
        return ReplayResult.OK

    def Receive(self, payload):
        timestamp = int(payload['receive_timestamp_us'])
        if timestamp <= 0:
            return ReplayResult.INVALID, None
        if timestamp < self.start:
            return ReplayResult.HISTORY_MISS, None
        mask = int(payload.get('_integrity_native_valid_group_mask',
                               payload['valid_group_mask']))
        admitted = int(payload['valid_group_mask'])
        epoch = Kf6GnssEpoch(timestamp,
            np.asarray(payload['position_enu_m'], dtype=np.float32),
            np.asarray(payload['velocity_enu_mps'], dtype=np.float32),
            np.sqrt(np.asarray(payload['position_variance_m2'], dtype=np.float32)),
            np.sqrt(np.asarray(payload['velocity_variance_m2ps2'], dtype=np.float32)), mask)
        self.tracker.Kf6_GnssEpochTrack(epoch)
        event = ReplayEvent(0, timestamp, int(payload['sequence']), 0, self.epoch, dict(payload),
            tuple(deepcopy(self.tracker._reacquire_groups)), admitted,
            self.tracker._previous_epoch.valid_group_mask)
        return ReplayResult.OK, event

    @staticmethod
    def _EventApply(state, event):
        p = event.payload
        outcome = {'results': [3] * 4, 'baro': 3}
        if event.kind == 8:
            target = np.asarray(p['target_position_en'], dtype=np.float32)
            variance = np.asarray(p['target_variance_en'], dtype=np.float32)
            state.state[:2] = target
            state.covariance[:2, :] = 0.0
            state.covariance[:, :2] = 0.0
            state.covariance[0, 0] = max(float(variance[0]), 1.0e-3)
            state.covariance[1, 1] = max(float(variance[1]), 1.0e-3)
            return ReplayResult.OK, outcome
        groups = [g for g in range(4) if event.kind & (1 if g < 2 else 2)
                  and not (g == 1 and state.analysis_position_vertical_disabled)]
        if event.kind != 4:
            previous = state._previous_epoch
            valid = previous.valid_group_mask if previous else 0
            for g in groups:
                source = event.evidence[g]
                target = state._reacquire_groups[g]
                if target.generation != source.generation:
                    target = _ReacquireGroupState(
                        generation=source.generation, outage=source.outage
                    )
                    state._reacquire_groups[g] = target
                    state.reacquire_active_mask &= ~(1 << g)
                for key in (
                    "availability_timestamp_us",
                    "loss_latched",
                    "consistent_count",
                    "consistency_start_us",
                ):
                    setattr(target, key, getattr(source, key))
                if not event.recovery_mask & (1 << g):
                    target.reject_streak = target.accepted_streak = 0
                valid = (valid & ~(1 << g)) | (event.recovery_mask & (1 << g))
            empty = np.zeros(3, dtype=np.float32)
            state._previous_epoch = Kf6GnssEpoch(
                event.receive_us, empty, empty, empty, empty, valid
            )
            # All same-event updates precede recovery, matching C ordering.
            for g in groups:
                if event.valid_mask & (1 << g):
                    value = p['position_enu_m' if g < 2 else 'velocity_enu_mps']
                    variance = p['position_variance_m2' if g < 2 else 'velocity_variance_m2ps2']
                    outcome["results"][g] = int(
                        state.Kf6_GroupUpdate(Kf6GnssGroup(g), value, variance)
                    )
            outcome['position_innovation'] = state.last_position_innovation.copy()
            outcome['velocity_innovation'] = state.last_velocity_innovation.copy()
            for g in groups:
                if event.valid_mask & (1 << g):
                    value = p['position_enu_m' if g < 2 else 'velocity_enu_mps']
                    variance = p['position_variance_m2' if g < 2 else 'velocity_variance_m2ps2']
                    outcome['results'][g] = int(state.Kf6_GroupRecover(Kf6GnssGroup(g),
                        Kf6UpdateResult(outcome['results'][g]), value, variance, event.receive_us))
            state.last_position_nis = np.max(state.last_group_nis[:2])
            state.last_velocity_nis = np.max(state.last_group_nis[2:])
        else:
            outcome['baro'] = int(state.Kf6_UpdateBaro(p['relative_altitude_m'], p['variance_m2']))
        outcome['nis'] = state.last_group_nis.copy()
        outcome['baro_nis'] = state.last_baro_nis
        if 4 in outcome['results'] or outcome['baro'] == 4:
            return ReplayResult.NUMERIC_ERROR, outcome
        return ReplayResult.OK, outcome

    @staticmethod
    def _EventValid(event):
        if event.kind not in (1, 2, 3, 4, 8):
            return False
        payload = event.payload
        if event.kind == 8:
            target = np.asarray(payload.get('target_position_en', ()), dtype=np.float64)
            variance = np.asarray(payload.get('target_variance_en', ()), dtype=np.float64)
            return (target.shape == (2,) and variance.shape == (2,)
                    and np.all(np.isfinite(target)) and np.all(np.isfinite(variance))
                    and np.all(variance > 0))
        if event.kind == 4:
            return (np.isfinite(payload['relative_altitude_m'])
                    and np.isfinite(payload['variance_m2']) and payload['variance_m2'] > 0)
        for group in range(4):
            if not event.valid_mask & (1 << group) or not event.kind & (1 if group < 2 else 2):
                continue
            axes = (0, 1) if group % 2 == 0 else (2,)
            value = payload['position_enu_m' if group < 2 else 'velocity_enu_mps']
            variance = payload['position_variance_m2' if group < 2 else 'velocity_variance_m2ps2']
            if any(not np.isfinite(value[a]) or not np.isfinite(variance[a]) or variance[a] <= 0
                   for a in axes):
                return False
        return True

    def Insert(self, event):
        self.last_outcome = {}
        if (self.faulted or event.measurement_us > self.present or event.receive_us <= 0
                or not self._EventValid(event)):
            return ReplayResult.INVALID
        if event.epoch != self.epoch or not self._ModelMatches():
            return ReplayResult.EPOCH_MISMATCH
        if (
            self.present - event.measurement_us > self.WINDOW_US
            or event.measurement_us < max(self.start, self.checkpoints[0][0])
            or event.receive_us < self.start
        ):
            return ReplayResult.HISTORY_MISS
        relevant = sum((e.kind == 4) == (event.kind == 4) for e in self.events)
        if relevant >= (160 if event.kind == 4 else 48) or len(self.events) >= 208:
            return ReplayResult.OVERFLOW
        keys = [e.Order_Get() for e in self.events]
        index = bisect_left(keys, event.Order_Get())
        if index < len(keys) and keys[index] == event.Order_Get():
            return ReplayResult.INVALID
        self.events.insert(index, event)
        if event.measurement_us == self.present and index == len(self.events) - 1:
            working = Filter_Clone(self.state)
            result, self.last_outcome = self._EventApply(working, event)
        else:
            self.replays += 1
            checkpoint = max(
                i for i, (t, _) in enumerate(self.checkpoints) if t <= event.measurement_us
            )
            cursor, initial = self.checkpoints[checkpoint]
            working = Filter_Clone(initial)
            pending = [e for e in self.events if e.measurement_us >= cursor]
            next_checkpoint = checkpoint + 1
            steps = 0
            result = ReplayResult.OK
            for imu in [*self.imu, None]:
                end = imu[1] if imu else self.present
                if imu and end <= cursor:
                    continue
                while pending and (
                    pending[0].measurement_us < end
                    or (imu is None and pending[0].measurement_us == end)
                ):
                    current = pending.pop(0)
                    if current.measurement_us > cursor:
                        if imu is None:
                            result = ReplayResult.DISCONTINUITY
                            break
                        fraction = np.float32(current.measurement_us - cursor) / np.float32(
                            imu[1] - imu[0]
                        )
                        if not working.Kf6_Predict(imu[2] * fraction, imu[3] * fraction):
                            result = ReplayResult.NUMERIC_ERROR
                            break
                        cursor = current.measurement_us
                        steps += 1
                    result, outcome = self._EventApply(working, current)
                    steps += 1
                    if current is event:
                        self.last_outcome = outcome
                    if result != ReplayResult.OK:
                        break
                if result != ReplayResult.OK:
                    break
                if imu and end > cursor:
                    fraction = np.float32(end - cursor) / np.float32(imu[1] - imu[0])
                    if not working.Kf6_Predict(imu[2] * fraction, imu[3] * fraction):
                        result = ReplayResult.NUMERIC_ERROR
                        break
                    steps += 1
                    cursor = end
                    if (
                        next_checkpoint < len(self.checkpoints)
                        and self.checkpoints[next_checkpoint][0] == cursor
                    ):
                        self.checkpoints[next_checkpoint] = (cursor, Filter_Clone(working))
                        next_checkpoint += 1
                if steps > self.MAX_STEPS:
                    result = ReplayResult.WORK_LIMIT
                    break
        if result == ReplayResult.OK:
            self.state = working
        else:
            self.faulted = True
        return result


def Operations_Build(dataset):
    operations = []
    for kind, field in (
        ("predict", "operation_sequence"),
        ("receive", "receive_operation_sequence"),
        ("position", "position_operation_sequence"),
        ("velocity", "velocity_operation_sequence"),
        ("baro", "operation_sequence"),
    ):
        name = (
            "ESTIMATOR_STEP"
            if kind == "predict"
            else "BARO_MEASUREMENT"
            if kind == "baro"
            else "GNSS_MEASUREMENT"
        )
        for record in dataset.Records_Get(name):
            p = record.payload
            order = int(p[field])  # Missing timing is an error, never inferred.
            if order == 0:
                continue
            if kind == 'velocity' and order == int(p['position_operation_sequence']):
                continue
            operations.append((int(p['replay_epoch']), order, kind, record))
    operations.sort(key=lambda item: item[:2])
    identities = [item[:2] for item in operations]
    if len(set(identities)) != len(identities):
        raise ValueError('replay_operation_duplicate')
    return operations


def EpochState_Restore(dataset, epoch, template):
    """Only an explicit epoch-start x/P snapshot can authorize a reset.

    FCCG resets recovery/internal counters at epoch start. A decimated mid-epoch
    snapshot cannot reconstruct those counters and is deliberately rejected.
    """
    starts = [r for r in dataset.Records_Get('ESTIMATOR')
              if r.payload.get('replay_epoch') == epoch
              and r.payload.get('operation_sequence') == 0 and r.timestamp_us == 0]
    if len(starts) != 1:
        raise ValueError('replay_epoch_initial_state_missing')
    start = starts[0]
    covariance_records = [r for r in dataset.Records_Get('KF6_FULL_P')
                          if r.timestamp_us == 0 and r.record_sequence == start.record_sequence + 1]
    if len(covariance_records) != 1:
        raise ValueError('replay_epoch_covariance_missing')
    packed = np.asarray(
        covariance_records[0].payload["covariance_upper_triangle"], dtype=np.float32
    )
    if packed.shape != (21,) or not np.isfinite(packed).all():
        raise ValueError('replay_epoch_covariance_invalid')
    covariance = np.zeros((6, 6), dtype=np.float32)
    covariance[np.triu_indices(6)] = packed
    covariance += np.triu(covariance, 1).T
    np.linalg.cholesky(covariance)
    state = Kf6Filter.Kf6_Create(
        process_accel_std_mps2=template.process_accel_std_mps2,
        p0_diagonal=np.diag(covariance),
        initial_velocity_enu_mps=start.payload["velocity_enu_mps"],
        nis_soft_threshold=template.nis_soft_threshold,
        nis_hard_threshold=template.nis_hard_threshold,
        nis_max_r_scale=template.nis_max_r_scale,
        gnss_reacquire_outage_ms=template.gnss_reacquire_outage_ms,
    )
    state.state[:3] = start.payload['position_enu_m']
    state.covariance = covariance
    state.analysis_position_vertical_disabled = template.analysis_position_vertical_disabled
    state.outage_required = template.outage_required
    state.require_effective_gain = template.require_effective_gain
    q = np.asarray(start.payload['q_nb'], dtype=np.float32)
    if q.shape != (4,) or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1) > .01:
        raise ValueError('replay_epoch_attitude_invalid')
    if not np.isfinite(state.state).all():
        raise ValueError('replay_epoch_state_invalid')
    return FixedLagReplay(state, epoch=epoch), q.copy()


def Faithful_Run(dataset, filter_instance, initial_q, increments, parameters, context,
                 assistance=None):
    from silverstar_flp.plugins.algorithms.kf6.plugin import _ReplaySnapshot

    operations = [
        op
        for op in Operations_Build(dataset)
        if int(op[3].payload["estimator_present_timestamp_us"])
        <= increments[-1].interval_end_timestamp_us
    ]
    if not operations:
        raise ValueError('replay_operation_timing_missing')
    history = FixedLagReplay(filter_instance, epoch=operations[0][0])
    # Timestamp matching is exact identity, never measurement arrival inference.
    increments_by_end = {i.interval_end_timestamp_us: i for i in increments}
    by_sequence = {
        (
            int(r.payload["sequence"]),
            int(r.payload["interval_end_timestamp_us"]),
        ): increments_by_end[int(r.payload["interval_end_timestamp_us"])]
        for r in dataset.Records_Get("INERTIAL_INCREMENT")
        if int(r.payload["interval_end_timestamp_us"]) in increments_by_end
    }
    q = initial_q.copy()
    evidence = {}
    snapshots = []
    group_updates = []
    measurement_events = []
    analysis_events = []
    quality_evidence = {(r.payload['replay_epoch'], r.payload['source_sequence']): r.payload
                        for r in dataset.Records_Get('GNSS_RECOVERY')}
    reanchor_times = []
    mismatches = []
    previous_order = None
    last_prediction = None
    results = [3, 3, 3]
    group_result = np.full(4, 5, dtype=np.int32)
    attempt_mask = 0

    def snapshot_append():
        if last_prediction is None:
            return
        state = history.state
        snapshots.append(
            _ReplaySnapshot(
                timestamp_us=last_prediction,
                q_nb=q.copy(),
                state=state.state.copy(),
                covariance=state.covariance.copy(),
                position_innovation=state.last_position_innovation.copy(),
                velocity_innovation=state.last_velocity_innovation.copy(),
                baro_innovation=float(state.last_baro_innovation),
                position_nis=float(state.last_position_nis),
                velocity_nis=float(state.last_velocity_nis),
                group_nis=state.last_group_nis.copy(),
                group_result=group_result.copy(),
                baro_nis=float(state.last_baro_nis),
                position_result=results[0],
                velocity_result=results[1],
                baro_result=results[2],
                attempt_mask=attempt_mask,
                r_scale=np.ones(3, dtype=np.float32),
                position_measurement_variance=(
                    state.last_position_effective_variance.copy()
                ),
                velocity_measurement_variance=(
                    state.last_velocity_effective_variance.copy()
                ),
                baro_measurement_variance=float(state.last_baro_effective_variance),
            )
        )

    for index, (epoch, order, kind, record) in enumerate(operations):
        context.Cancel_RaiseIfRequested()
        if epoch != history.epoch:
            snapshot_append()
            history, q = EpochState_Restore(dataset, epoch, filter_instance)
            evidence.clear()
            last_prediction = previous_order = None
            results, attempt_mask = [3, 3, 3], 0
            group_result.fill(5)
        if previous_order is not None and order != previous_order + 1:
            mismatches.append(('operation_gap', previous_order, order))
        previous_order = order
        p = record.payload
        if kind == 'predict':
            snapshot_append()
            last_prediction = None
            results = [3, 3, 3]
            group_result.fill(5)
            attempt_mask = 0
            increment = by_sequence.get(
                (int(p["source_sequence"]), int(p["interval_end_timestamp_us"]))
            )
            if increment is None:
                raise ValueError('replay_increment_identity_missing')
            if int(p['attitude_result']) == 0:
                if int(p['replay_result']) != ReplayResult.INVALID:
                    mismatches.append(('attitude_result', order))
                if history.present != int(p['estimator_present_timestamp_us']):
                    mismatches.append(('present', order))
                continue
            dv = Quaternion_RotateVector(q, increment.delta_velocity_b)
            dv[2] -= np.float32(parameters['gravity_mps2']) * np.float32(increment.dt_s)
            q = Quaternion_PropagateBodyIncrement(q, increment.delta_theta_b)
            result = history.Predict(increment.interval_end_timestamp_us, dv, increment.dt_s)
            expected = int(p['replay_result'])
            if result == ReplayResult.OK:
                last_prediction = increment.interval_end_timestamp_us
        elif kind == 'receive':
            result, event = history.Receive(p)
            evidence[record.record_sequence] = event
            expected = int(p['receive_result'])
        else:
            if kind == 'baro':
                event = ReplayEvent(
                    int(p["measurement_timestamp_us"]),
                    int(p["receive_timestamp_us"]),
                    int(p["sequence"]),
                    4,
                    epoch,
                    dict(p),
                )
                expected = int(p['replay_result'])
                attempt_mask |= 4
            else:
                event = evidence.get(record.record_sequence)
                if event is None:
                    raise ValueError('replay_receive_evidence_missing')
                combined = int(p["position_operation_sequence"]) == int(
                    p["velocity_operation_sequence"]
                )
                event = replace(event, kind=3 if combined else 1 if kind == 'position' else 2,
                                measurement_us=int(p[kind + '_measurement_timestamp_us']))
                expected = int(p[kind + '_replay_result'])
                attempt_mask |= event.kind
            decision = None
            if assistance is not None and event.kind & 1:
                decision = assistance.decisions.get(int(p['sequence']))
                if decision is not None:
                    event_payload = dict(event.payload)
                    if decision.position_r_scale != 1.0:
                        variance = list(event_payload['position_variance_m2'])
                        variance[:2] = [float(value) * decision.position_r_scale
                                        for value in variance[:2]]
                        event_payload['position_variance_m2'] = tuple(variance)
                    event = replace(
                        event, payload=event_payload,
                        valid_mask=(event.valid_mask if decision.position_en_allowed
                                    else event.valid_mask & ~1),
                    )
            previous_reanchors = tuple(history.state.reanchor_counts)
            if (
                event.kind == 3
                and p["position_measurement_timestamp_us"] != p["velocity_measurement_timestamp_us"]
            ):
                # What-if may split a formerly simultaneous packet; historical ordering
                # is still by measurement time on the same receive operation.
                parts = [
                    replace(event, kind=k, measurement_us=int(p[field]))
                    for k, field in (
                        (1, "position_measurement_timestamp_us"),
                        (2, "velocity_measurement_timestamp_us"),
                    )
                ]
                parts.sort(key=lambda part: part.Order_Get())
                result = ReplayResult.OK
                combined_outcome = {}
                for part in parts:
                    result = history.Insert(part)
                    if history.last_outcome:
                        current = history.last_outcome
                        if not combined_outcome:
                            combined_outcome = deepcopy(current)
                        else:
                            groups = (0, 1) if part.kind == 1 else (2, 3)
                            for g in groups:
                                combined_outcome['results'][g] = current['results'][g]
                                combined_outcome['nis'][g] = current['nis'][g]
                            key = 'position_innovation' if part.kind == 1 else 'velocity_innovation'
                            combined_outcome[key] = current[key]
                    if result != ReplayResult.OK:
                        break
                history.last_outcome = combined_outcome
            else:
                result = history.Insert(event)
            outcome = history.last_outcome
            if (assistance is not None and decision is not None
                    and decision.reanchor_ready and result == ReplayResult.OK
                    and bool(event.valid_mask & 1)):
                target = np.asarray(p['position_enu_m'][:2], dtype=np.float64)
                distance = float(np.linalg.norm(target - history.state.state[:2]))
                if distance >= assistance.config.reanchor_min_distance_m:
                    reanchor_event = ReplayEvent(
                        history.present, history.present, int(p['sequence']), 8,
                        epoch,
                        {'target_position_en': tuple(target),
                         'target_variance_en': tuple(p['position_variance_m2'][:2])},
                    )
                    reanchor_result = history.Insert(reanchor_event)
                    if reanchor_result != ReplayResult.OK:
                        raise ValueError('integrity_reanchor_failed')
                    analysis_events.append({
                        'event': 'INTEGRITY_REANCHOR', 'timestamp_us': history.present,
                        'source_sequence': int(p['sequence']), 'distance_m': distance,
                    })
            if any(
                a > b
                for a, b in zip(history.state.reanchor_counts, previous_reanchors, strict=True)
            ):
                reanchor_times.append(history.present)
            if event.kind != 4 and outcome:
                for g in range(4):
                    if event.kind & (1 if g < 2 else 2):
                        group_result[g] = int(outcome['results'][g])
                for g, name in enumerate(("Pos EN", "Pos U", "Vel EN", "Vel U")):
                    if not event.kind & (1 if g < 2 else 2):
                        continue
                    evidence_group = event.evidence[g]
                    recovery = history.state._reacquire_groups[g]
                    axes = (0, 1) if g % 2 == 0 else (2,)
                    innovation = outcome['position_innovation' if g < 2 else 'velocity_innovation']
                    variance = p['position_variance_m2' if g < 2 else 'velocity_variance_m2ps2']
                    effective_source = (
                        history.state.last_position_effective_variance
                        if g < 2 else history.state.last_velocity_effective_variance
                    )
                    effective = np.asarray(
                        [float(effective_source[a]) for a in axes], dtype=np.float64
                    )
                    base = np.asarray([float(variance[a]) for a in axes], dtype=np.float64)
                    accepted = outcome["results"][g] in (0, 1)
                    resolved = int(p[
                        "position_measurement_timestamp_us"
                        if g < 2 else "velocity_measurement_timestamp_us"
                    ])
                    measurement_events.append(dict(
                        group=("position_en", "position_u", "velocity_en", "velocity_u")[g],
                        timestamp_us=history.present,
                        receive_timestamp_us=event.receive_us,
                        source_id=p.get("_quality_source_id"),
                        resolved_measurement_timestamp_us=resolved,
                        operation_sequence=order,
                        valid=bool(int(p["valid_group_mask"]) & (1 << g)),
                        result=int(outcome["results"][g]),
                        variance_scale=(
                            float(p.get("_quality_variance_scales", (1.0,) * 4)[g])
                            * (float(effective[0] / base[0])
                               if int(outcome["results"][g]) == 1 and base[0] > 0 else 1.0)
                        ),
                        input_variance=tuple(float(value) for value in base),
                        effective_variance=tuple(
                            float(value) for value in (
                                effective if accepted else np.full(base.shape, np.nan)
                            )
                        ),
                        receive_age=(history.present - event.receive_us) * .001,
                        fixed_lag_latency=(history.present - resolved) * .001,
                        r_scale=(float(effective[0] / base[0])
                                 if accepted and base[0] > 0 else np.nan),
                    ))
                    group_updates.append(
                        dict(
                            timestamp_us=history.present,
                            source="Recomputed",
                            source_id=p.get("_quality_source_id"),
                            group=name,
                            valid=bool(event.valid_mask & (1 << g))
                            and not (g == 1 and history.state.analysis_position_vertical_disabled),
                            result=outcome["results"][g],
                            innovation=tuple(float(innovation[a]) for a in axes),
                            nis=float(outcome["nis"][g]),
                            variance=tuple(float(variance[a]) for a in axes),
                            outage=evidence_group.outage,
                            consistency=evidence_group.consistent_count,
                            inflation=recovery.inflation_attempt_count,
                            factor=recovery.last_inflation_factor,
                            reanchor=history.state.reanchor_counts[g],
                            reason=int(history.state.reanchor_counts[g] != 0),
                            quality=quality_evidence.get((epoch, p["sequence"]), {}).get(
                                "quality_reject_mask", [None] * 4
                            )[g],
                        )
                    )

            if kind == 'baro':
                baro_result = outcome.get('baro', 3)
                base = float(p["variance_m2"])
                effective = float(history.state.last_baro_effective_variance)
                accepted = baro_result in (0, 1)
                measurement_events.append(dict(
                    group="baro", timestamp_us=history.present,
                    receive_timestamp_us=event.receive_us,
                    resolved_measurement_timestamp_us=event.measurement_us,
                    operation_sequence=order,
                    valid=bool(p.get("valid_mask", 1) & 1),
                    result=int(baro_result),
                    variance_scale=effective / base if int(baro_result) == 1 and base > 0 else 1.0,
                    input_variance=(base,),
                    effective_variance=(effective if accepted else float("nan"),),
                    receive_age=(history.present - event.receive_us) * .001,
                    fixed_lag_latency=(history.present - event.measurement_us) * .001,
                    r_scale=effective / base if accepted and base > 0 else np.nan,
                ))
                results[2] = baro_result
            elif outcome:
                for group in range(2):
                    if event.kind & (1 << group):
                        group_results = outcome['results'][group * 2:group * 2 + 2]
                        results[group] = min(group_results)
            final_group = kind == "baro" or order == max(
                int(p["position_operation_sequence"]), int(p["velocity_operation_sequence"]))
            if final_group and history.replays != int(p['replay_generation']):
                mismatches.append(
                    ("generation", order, history.replays, int(p["replay_generation"]))
                )
        if int(result) != expected:
            mismatches.append(('result', order, int(result), expected))
        if history.present != int(p['estimator_present_timestamp_us']):
            mismatches.append(
                ("present", order, history.present, int(p["estimator_present_timestamp_us"]))
            )
        if index % 128 == 0:
            context.Progress_Report(.1 + .82 * index / len(operations), 'replay.kf6')
    snapshot_append()
    # Reporting belongs to the actual application stream, outside historical
    # checkpoints. Never lose samples on clone or count replay-forward twice.
    history.state.gnss_nis_samples = [[] for _ in range(4)]
    history.state.gnss_result_counts = [[0]*5 for _ in range(4)]
    group_names = ('Pos EN', 'Pos U', 'Vel EN', 'Vel U')
    for row in group_updates:
        if not row['valid']:
            continue
        group = group_names.index(row['group'])
        history.state.gnss_result_counts[group][row['result']] += 1
        if np.isfinite(row['nis']):
            history.state.gnss_nis_samples[group].append(row['nis'])
    return tuple(snapshots), history.state, {'operation_count': len(operations),
        'replay_count': history.replays, 'execution_mismatches': mismatches,
        'measurement_timing_inferred': False, 'reanchor_counts': history.state.reanchor_counts,
        'gnss_group_updates': group_updates, 'measurement_events': measurement_events,
        'integrity_analysis_events': analysis_events,
        'reanchor_timestamps_us': reanchor_times}
