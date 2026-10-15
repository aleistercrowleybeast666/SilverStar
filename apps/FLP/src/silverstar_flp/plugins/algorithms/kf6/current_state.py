"""Present-state KF6 transactions. No IMU history, checkpoints or rewind."""
from copy import deepcopy

import numpy as np

from silverstar_flp.decoder_profiles.fusion_timing_records import (
    CurrentAdmission_Get, FusionExecutionResult as Result, FusionSequenceTracker,
)
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6GnssEpoch
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    Filter_Clone, FixedLagReplay, ReplayEvent, ReplayResult, _Outcome_Invalid,
)


class CurrentState:
    def __init__(self, state, timestamp_us=0, epoch=1, *, calibration_generation=None):
        self.state, self.tracker = Filter_Clone(state), Filter_Clone(state)
        self.present = self.start = timestamp_us
        self.epoch, self.generation = epoch, calibration_generation
        self.predictions = self.replays = 0
        self.faulted = False
        self.last_outcome = _Outcome_Invalid()
        self._sequence = FusionSequenceTracker()
        fields = ('process_accel_std_mps2', 'nis_soft_threshold', 'nis_hard_threshold',
                  'nis_max_r_scale', 'nis_soft_enabled', 'nis_hard_enabled',
                  'require_effective_gain', 'algorithm_revision')
        self._model = {name: deepcopy(getattr(state, name)) for name in fields}
        self._audit = {}

    def _Result_Record(self, result, source=0, application=0):
        self._audit = dict(last_source_us=source, last_application_us=application,
                           last_execution_result=int(result))
        return result

    def Audit_Get(self):
        return {**self._audit, 'history_replay_count': 0, 'history_step_count': 0,
                'producer_watermarks': len(self._sequence)}

    def _ModelMatches(self):
        return all(np.array_equal(getattr(self.state, key), value)
                   for key, value in self._model.items())

    def Predict(self, timestamp_us, delta, dt):
        delta, dt = np.asarray(delta, dtype=np.float32), np.float32(dt)
        if self.faulted or delta.shape != (3,) or not np.isfinite(delta).all() or not np.isfinite(dt) or not 0 < dt <= .1:
            return self._Result_Record(Result.INVALID)
        if not self._ModelMatches():
            self.faulted = True
            return self._Result_Record(Result.EPOCH_MISMATCH)
        duration = int(float(dt) * 1_000_000 + .5)
        present = timestamp_us - duration if self.predictions == 0 and self.present == 0 else self.present
        if present < 0 or timestamp_us <= present or abs(timestamp_us - present - duration) > 1:
            self.faulted = True
            return self._Result_Record(Result.DISCONTINUITY)
        working = Filter_Clone(self.state)
        if not working.Kf6_Predict(delta, dt):
            self.faulted = True
            return self._Result_Record(Result.NUMERIC_ERROR)
        if self.predictions == 0 and self.present == 0:
            self.start = present
        self.state, self.present = working, timestamp_us
        self.predictions += 1
        return self._Result_Record(Result.COMPLETE)

    def _Identity_Check(self, payload, epoch, sequence, mask, baro):
        source, generation = payload.get('source_id'), payload.get('calibration_generation')
        if epoch != self.epoch or type(generation) is not int or generation != self.generation:
            return Result.EPOCH_MISMATCH
        if baro and source != 1:
            return Result.INVALID
        return self._sequence.Check('baro' if baro else 'gnss', source, sequence, mask)

    def Receive(self, payload):
        self.last_outcome = _Outcome_Invalid()
        timestamp = int(payload['receive_timestamp_us'])
        event = ReplayEvent(0, timestamp, int(payload['sequence']), 0, self.epoch, dict(payload),
            tuple(deepcopy(self.tracker._reacquire_groups)), int(payload['valid_group_mask']),
            self.tracker._previous_epoch.valid_group_mask if self.tracker._previous_epoch else 0)
        admission = CurrentAdmission_Get(timestamp, timestamp, self.present, self.start)
        if self.faulted:
            admission = Result.NOT_READY
        if admission == Result.COMPLETE:
            admission = self._Identity_Check(payload, int(payload.get('replay_epoch', self.epoch)), event.sequence, 0x80, False)
        if admission != Result.COMPLETE:
            event.payload['_current_receive_execution_result'] = int(admission)
            return self._Result_Record(admission), event
        mask = int(payload.get('_integrity_native_valid_group_mask', payload['valid_group_mask']))
        observation = Kf6GnssEpoch(timestamp,
            np.asarray(payload['position_enu_m'], dtype=np.float32),
            np.asarray(payload['velocity_enu_mps'], dtype=np.float32),
            np.sqrt(np.asarray(payload['position_variance_m2'], dtype=np.float32)),
            np.sqrt(np.asarray(payload['velocity_variance_m2ps2'], dtype=np.float32)), mask)
        self.tracker.Kf6_GnssEpochTrack(observation)
        self._sequence.Commit('gnss', payload['source_id'], event.sequence, 0x80)
        event.evidence = tuple(deepcopy(self.tracker._reacquire_groups))
        event.recovery_mask = self.tracker._previous_epoch.valid_group_mask
        return self._Result_Record(Result.COMPLETE), event

    def Insert(self, event):
        self.last_outcome = _Outcome_Invalid()
        source = event.measurement_us
        result = CurrentAdmission_Get(event.receive_us, event.receive_us, self.present, self.start)
        if self.faulted:
            result = Result.NOT_READY
        elif not self._ModelMatches():
            result = Result.EPOCH_MISMATCH
        elif event.kind not in (1, 2, 3, 4) or not FixedLagReplay._EventValid(event):
            result = Result.INVALID
        elif event.kind == 4 and not int(event.payload.get('valid_mask', 1)) & 1:
            result = Result.INVALID
        elif event.kind != 4 and event.payload.get('_current_receive_execution_result'):
            result = Result(event.payload['_current_receive_execution_result'])
        mask = 0x10 if event.kind == 4 else (3 if event.kind & 1 else 0) | (12 if event.kind & 2 else 0)
        if result == Result.COMPLETE:
            result = self._Identity_Check(event.payload, event.epoch, event.sequence, mask, event.kind == 4)
        if result != Result.COMPLETE:
            return self._Result_Record(result, source)
        self._sequence.Commit('baro' if event.kind == 4 else 'gnss',
                              event.payload['source_id'], event.sequence, mask)
        result = CurrentAdmission_Get(source, event.receive_us, self.present, self.start)
        if result != Result.COMPLETE:
            return self._Result_Record(result, source)
        working = Filter_Clone(self.state)
        status, outcome = FixedLagReplay._EventApply(working, event)
        if status != ReplayResult.OK:
            self.faulted = True
            return self._Result_Record(Result.NUMERIC_ERROR, source, self.present)
        self.state, self.last_outcome = working, outcome
        return self._Result_Record(Result.COMPLETE, source, self.present)
