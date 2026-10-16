"""Bind recorded body intervals to the owning admitted cycle and physical identity."""

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np

from silverstar_flp.core.math import (
    Quaternion_Normalize,
    Quaternion_PropagateBodyIncrement,
    Quaternion_RotateVector,
)
from silverstar_flp.plugins.algorithms.eskf15.horizon import HorizonBody
from silverstar_flp.plugins.algorithms.kf6.horizon import KfHorizonBody


def _Unsigned(value, bits=32):
    return type(value) is int and 0 <= value < 1 << bits


def _Contiguous_Validate(previous, sequence):
    if (
        not _Unsigned(sequence)
        or previous is not None
        and ((sequence - previous) & 0xFFFFFFFF) != 1
    ):
        raise ValueError("fusion_horizon_body_sequence_discontinuity")


def EskfHorizonBodies_Build(records, *, source, calibration_generation):
    if not all(_Unsigned(value) for value in (source, calibration_generation)):
        raise ValueError("fusion_horizon_body_configuration_invalid")
    bodies, previous = [], None
    for record in sorted(records, key=lambda row: row.file_offset):
        p = record.payload
        if (
            record.record_name != "ESKF15_BODY_INPUT"
            or record.record_type != 0x26
            or record.record_version != 1
            or not _Unsigned(p["source_id"])
            or not _Unsigned(p["calibration_generation"])
            or p["source_id"] != source
            or p["calibration_generation"] != calibration_generation
        ):
            raise ValueError("fusion_horizon_body_record_identity_mismatch")
        _Contiguous_Validate(previous, p["sequence"])
        previous = p["sequence"]
        begin, end, dt = p["interval_start_timestamp_us"], p["interval_end_timestamp_us"], p["dt_s"]
        if (
            not _Unsigned(begin, 64)
            or not _Unsigned(end, 64)
            or record.timestamp_us != end
            or end <= begin
            or not np.isfinite(dt)
            or not 0 < dt <= 0.02
            or abs((end - begin) * 1e-6 - dt) > 2e-6
            or not _Unsigned(p["quality_flags"])
        ):
            raise ValueError("fusion_horizon_body_interval_invalid")
        gyro = np.asarray(p["body_gyro_radps"], dtype=np.float64)
        accel = np.asarray(p["body_accel_mps2"], dtype=np.float64)
        if (
            gyro.shape != (6,)
            or accel.shape != (6,)
            or not np.isfinite(gyro).all()
            or not np.isfinite(accel).all()
        ):
            raise ValueError("fusion_horizon_body_vector_invalid")
        bodies.append(
            HorizonBody(
                begin,
                end,
                gyro[:3].copy(),
                accel[:3].copy(),
                gyro[3:].copy(),
                accel[3:].copy(),
                source,
                calibration_generation,
                p["quality_flags"],
                dt,
            )
        )
    if not bodies:
        raise ValueError("fusion_horizon_recorded_body_missing")
    return tuple(bodies)


@dataclass(frozen=True, slots=True)
class KfHorizonBodyEvidence:
    bodies: tuple
    quaternions: object


def KfHorizonBodies_Build(
    increments,
    steps,
    evidence,
    *,
    epoch,
    source,
    calibration_generation,
    initial_q_nb,
    gravity_mps2,
):
    if (
        not all(_Unsigned(value) for value in (epoch, source, calibration_generation))
        or not np.isfinite(gravity_mps2)
        or not 1 <= gravity_mps2 <= 20
    ):
        raise ValueError("fusion_horizon_body_configuration_invalid")
    by_key = {(row.source_sequence, row.interval_end_timestamp_us): row for row in increments}
    if len(by_key) != len(increments):
        raise ValueError("fusion_horizon_increment_identity_ambiguous")
    statuses = {row.timestamp_us: row.payload for row in evidence.statuses}
    if len(statuses) != len(evidence.statuses):
        raise ValueError("fusion_horizon_body_status_ambiguous")
    q = Quaternion_Normalize(np.asarray(initial_q_nb, dtype=np.float32))
    bodies, quaternions, previous = [], {}, None
    operations = [(row.file_offset, row.payload["operation_sequence"]) for row in evidence.requests]
    for record in sorted(steps, key=lambda row: row.file_offset):
        p = record.payload
        if (
            record.record_name != "ESTIMATOR_STEP"
            or record.record_type != 0x1E
            or record.record_version != 0
            or p["replay_epoch"] != epoch
            or p["attitude_result"] != 1
            or p["replay_result"] != 0
        ):
            raise ValueError("fusion_horizon_prediction_operation_invalid")
        end = p["interval_end_timestamp_us"]
        status = statuses.get(end)
        if (
            status is None
            or status["epoch"] != epoch
            or status["source_id"] != source
            or status["calibration_generation"] != calibration_generation
            or record.timestamp_us != end
            or p["estimator_present_timestamp_us"] != end
        ):
            raise ValueError("fusion_horizon_body_cycle_identity_mismatch")
        increment = by_key.get((p["source_sequence"], end))
        if increment is None:
            raise ValueError("fusion_horizon_increment_identity_missing")
        _Contiguous_Validate(previous, increment.source_sequence)
        previous = increment.source_sequence
        dt = np.float32(increment.dt_s)
        if (
            not np.isfinite(dt)
            or not 0 < dt <= np.float32(0.1)
            or abs((end - increment.interval_start_timestamp_us) * 1e-6 - float(dt)) > 2e-6
        ):
            raise ValueError("fusion_horizon_body_interval_invalid")
        delta = Quaternion_RotateVector(q, increment.delta_velocity_b)
        delta[2] -= np.float32(gravity_mps2) * dt
        q = Quaternion_PropagateBodyIncrement(q, increment.delta_theta_b)
        if not np.isfinite(delta).all() or not np.isfinite(q).all():
            raise ValueError("fusion_horizon_body_vector_invalid")
        bodies.append(
            KfHorizonBody(
                increment.interval_start_timestamp_us,
                end,
                delta.copy(),
                dt,
                source,
                calibration_generation,
            )
        )
        owned_q = q.copy()
        owned_q.setflags(write=False)
        quaternions[end] = owned_q
        operations.append((record.file_offset, p["operation_sequence"]))
    if not bodies or len(bodies) != len(increments):
        raise ValueError("fusion_horizon_body_operation_incomplete")
    if not operations or sorted(operations)[0][1] != 1:
        raise ValueError("fusion_horizon_epoch_operation_start_missing")
    previous = None
    for _, operation in sorted(operations):
        _Contiguous_Validate(previous, operation)
        previous = operation
    return KfHorizonBodyEvidence(tuple(bodies), MappingProxyType(quaternions))


def KfHorizon_RecordedInitialize(
    dataset,
    template,
    *,
    epoch,
    source,
    calibration_generation,
    start_us,
    horizon_us,
    p0_overrides=None,
):
    from silverstar_flp.plugins.algorithms.kf6.fixed_lag import EpochState_Restore
    from silverstar_flp.plugins.algorithms.kf6.horizon import DelayedKfHorizon

    def restore(state, recorded_epoch):
        if p0_overrides:
            names = [
                "p0_" + group + "_" + axis
                for group in ("position", "velocity")
                for axis in ("e", "n", "u")
            ]
            if set(p0_overrides) - set(names):
                raise ValueError("fusion_horizon_p0_override_unknown")
            covariance = state.covariance.copy()
            for name, value in p0_overrides.items():
                covariance[names.index(name), names.index(name)] = value
            state.covariance = covariance
        return DelayedKfHorizon(
            state,
            start_us,
            epoch=recorded_epoch,
            source=source,
            generation=calibration_generation,
            horizon_us=horizon_us,
        )

    return EpochState_Restore(dataset, epoch, template, executor_factory=restore)
