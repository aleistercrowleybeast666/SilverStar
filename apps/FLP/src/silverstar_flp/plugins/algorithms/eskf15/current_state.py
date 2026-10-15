"""Independent present-state ESKF executor with bounded producer watermarks."""
from copy import copy

import numpy as np

from silverstar_flp.decoder_profiles.fusion_timing_records import (
    CurrentAdmission_Get, FusionExecutionResult as Result, FusionSequenceTracker,
)
from silverstar_flp.plugins.algorithms.eskf15.filter import EskfMeasurementResult, EskfUpdateResult


class CurrentState:
    def __init__(self, kernel, start_us, *, epoch, soft=(6.635, 9.21),
                 hard=(10.828, 13.816), max_r_scale=4.0, soft_enabled=True,
                 hard_enabled=True, lever_arm=None):
        self.kernel, self.present_us, self.epoch = kernel, start_us, epoch
        self.initial_start_us = start_us
        self.soft, self.hard, self.max_r_scale = soft, hard, max_r_scale
        self.soft_enabled, self.hard_enabled = soft_enabled, hard_enabled
        self.lever_arm = np.zeros(3) if lever_arm is None else np.asarray(lever_arm).copy()
        self.source = self.generation = None
        self.history_misses = self.overflows = self.replay_steps = self.maximum_replay_steps = 0
        self.maximum_history = 0
        self._sequence = FusionSequenceTracker()
        self._model = (kernel.gravity, kernel.noise)
        self._audit = {}
        self._packet_identity = None
        self._packet_result = Result.NOT_READY
        self.faulted = False

    def Audit_Get(self):
        return {**self._audit, 'history_replay_count': 0, 'history_step_count': 0,
                'producer_watermarks': len(self._sequence)}

    def _Candidate_Create(self):
        candidate = copy(self.kernel)
        candidate.state = self.kernel.state.State_Clone()
        candidate.last_omega = self.kernel.last_omega.copy()
        return candidate

    def Body_Receive(self, step):
        if self.faulted:
            raise ValueError('eskf_current_faulted')
        if (self.kernel.gravity, self.kernel.noise) != self._model:
            self.faulted = True
            raise ValueError('eskf_current_model_changed')
        if step.end_us <= step.start_us or step.start_us != self.present_us:
            self.faulted = True
            raise ValueError('eskf_body_history_gap')
        if (step.quality_flags or 0) & 0x08 and step.start_us != self.initial_start_us:
            self.faulted = True
            raise ValueError('eskf_body_history_reset_requires_initialization')
        if self.source is not None and (step.source != self.source or step.generation != self.generation):
            self.faulted = True
            raise ValueError('eskf_body_source_generation_changed_requires_initialization')
        candidate = self._Candidate_Create()
        try:
            step.Interval_Apply(candidate, step.start_us, step.end_us)
            candidate.state.State_Validate()
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            self.faulted = True
            raise
        # Cache calibrated/raw gyro2. Measurement_Model subtracts the latest bg
        # for every group, including changes made by preceding group updates.
        self.kernel.state = candidate.state
        self.kernel.last_omega = np.asarray(step.gyro2).copy()
        self.present_us = step.end_us
        self.source, self.generation = step.source, step.generation

    def _Admission_Get(self, measurement):
        if self.faulted or self.generation is None:
            return Result.NOT_READY
        if (measurement.mission_epoch != self.epoch or measurement.generation != self.generation
                or (self.kernel.gravity, self.kernel.noise) != self._model):
            return Result.EPOCH_MISMATCH
        if measurement.group not in range(5):
            return Result.INVALID
        if measurement.group == 4 and measurement.source != 1:
            return Result.INVALID
        admission = CurrentAdmission_Get(measurement.receive_us, measurement.receive_us,
                                         self.present_us, self.initial_start_us)
        if admission != Result.COMPLETE:
            return admission
        namespace = 'baro' if measurement.group == 4 else 'gnss'
        if namespace == 'gnss':
            identity = (measurement.source, measurement.source_sequence,
                        measurement.mission_epoch, measurement.generation, self.present_us)
            if identity != self._packet_identity:
                self._packet_identity = identity
                self._packet_result = self._sequence.Check(namespace, measurement.source,
                                                           measurement.source_sequence, 0x80)
                if self._packet_result == Result.COMPLETE:
                    self._sequence.Commit(namespace, measurement.source, measurement.source_sequence, 0x80)
            if self._packet_result != Result.COMPLETE:
                return self._packet_result
        mask = 1 << measurement.group
        admission = self._sequence.Check(namespace, measurement.source, measurement.source_sequence, mask)
        if admission != Result.COMPLETE:
            return admission
        self._sequence.Commit(namespace, measurement.source, measurement.source_sequence, mask)
        admission = CurrentAdmission_Get(measurement.timestamp_us, measurement.receive_us,
                                         self.present_us, self.initial_start_us)
        if admission != Result.COMPLETE:
            return admission
        return Result.COMPLETE if measurement.physically_valid else Result.INVALID

    def Measurement_Receive(self, measurement):
        execution = self._Admission_Get(measurement)
        self._audit = dict(last_source_us=measurement.timestamp_us,
            last_application_us=0, last_execution_result=int(execution))
        if execution != Result.COMPLETE:
            return EskfMeasurementResult(
                16 + int(execution),
                np.full(measurement.value.shape, np.nan), np.nan, measurement.variance.copy())
        candidate = self._Candidate_Create()
        axes = ((0, 1), (2,), (0, 1), (2,), (2,))[measurement.group]
        self._audit['last_application_us'] = self.present_us
        result = candidate.Measurement_Apply(
            'velocity' if measurement.group in (2, 3) else 'position', axes,
            measurement.value, measurement.variance * measurement.quality_scale * measurement.consistency_scale,
            physically_valid=True, lever_arm=np.zeros(3) if measurement.group == 4 else self.lever_arm,
            soft=self.soft[len(axes)-1], hard=self.hard[len(axes)-1], max_scale=self.max_r_scale,
            soft_enabled=self.soft_enabled, hard_enabled=self.hard_enabled)
        if result.result in (EskfUpdateResult.NUMERIC_ERROR, EskfUpdateResult.MODEL_MISMATCH):
            self._audit['last_execution_result'] = int(Result.NUMERIC_ERROR)
            self.faulted = True
            return result
        candidate.state.State_Validate()
        self.kernel.state = candidate.state
        return result
