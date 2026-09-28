from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.core.math import (
    Quaternion_Normalize,
    Quaternion_PropagateBodyIncrement,
    Quaternion_RotateVector,
)


class MechanizationStepResult(StrEnum):
    OUTPUT = "output"
    BUFFERED = "buffered"
    INVALID_SAMPLE = "invalid_sample"
    SAMPLE_GAP = "sample_gap"


@dataclass(frozen=True, slots=True)
class InertialIncrement:
    interval_start_timestamp_us: int
    interval_end_timestamp_us: int
    ordering_sequence: int
    source_sequence: int
    dt_s: np.float32
    delta_theta_b: NDArray[np.float32]
    delta_velocity_b: NDArray[np.float32]
    health_flags: int = 0


@dataclass(frozen=True, slots=True)
class MechanizationOutput:
    timestamp_us: int
    ordering_sequence: int
    source_sequence: int
    dt_s: np.float32
    q_nb: NDArray[np.float32]
    velocity_enu_mps: NDArray[np.float32]
    position_enu_m: NDArray[np.float32]
    specific_force_enu_mps2: NDArray[np.float32]
    linear_accel_enu_mps2: NDArray[np.float32]
    delta_velocity_enu_mps: NDArray[np.float32]
    delta_theta_b: NDArray[np.float32]
    delta_velocity_b: NDArray[np.float32]
    health_flags: int


@dataclass(slots=True)
class CorrectedImuBuildDiagnostics:
    invalid_sample_count: int = 0
    sample_gap_count: int = 0
    buffered_sample_count: int = 0


def _Vector_Cross(first: NDArray[np.floating], second: NDArray[np.floating]) -> NDArray[np.float32]:
    a = np.asarray(first, dtype=np.float32)
    b = np.asarray(second, dtype=np.float32)
    return np.asarray(
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ),
        dtype=np.float32,
    )


def _SubInterval_Compute(
    previous: DecodedRecord, current: DecodedRecord
) -> tuple[NDArray[np.float32], NDArray[np.float32], np.float32]:
    previous_time = int(previous.payload["sample_timestamp_us"])
    current_time = int(current.payload["sample_timestamp_us"])
    dt = np.float32(max(0, current_time - previous_time) * 1.0e-6)
    gyro_previous = np.asarray(previous.payload["gyro_b_radps"], dtype=np.float32)
    gyro_current = np.asarray(current.payload["gyro_b_radps"], dtype=np.float32)
    accel_previous = np.asarray(previous.payload["accel_b_mps2"], dtype=np.float32)
    accel_current = np.asarray(current.payload["accel_b_mps2"], dtype=np.float32)
    half = np.float32(0.5)
    delta_theta = np.asarray(half * (gyro_previous + gyro_current) * dt, dtype=np.float32)
    delta_velocity = np.asarray(half * (accel_previous + accel_current) * dt, dtype=np.float32)
    return delta_theta, delta_velocity, dt


def InertialIncrement_BuildFromCorrectedImu(
    records: tuple[DecodedRecord, ...],
    *,
    start_timestamp_us: int,
    end_timestamp_us: int | None = None,
    minimum_sample_rate_hz: float = 50.0,
    maximum_sample_rate_hz: float = 500.0,
    tolerance_ratio: float = 0.35,
) -> tuple[tuple[InertialIncrement, ...], CorrectedImuBuildDiagnostics]:
    diagnostics = CorrectedImuBuildDiagnostics()
    history: list[DecodedRecord] = []
    increments: list[InertialIncrement] = []
    dt_min = np.float32((1.0 / maximum_sample_rate_hz) * (1.0 - tolerance_ratio))
    dt_max = np.float32((1.0 / minimum_sample_rate_hz) * (1.0 + tolerance_ratio))

    for record in sorted(records, key=lambda item: item.record_sequence):
        timestamp = int(record.payload["sample_timestamp_us"])
        if timestamp < start_timestamp_us:
            continue
        if end_timestamp_us is not None and timestamp > end_timestamp_us:
            continue
        valid_mask = int(record.payload.get("valid_mask", 0))
        correction_valid = bool(record.payload.get("correction_valid", 0))
        if (valid_mask & 0x03) != 0x03 or not correction_valid:
            diagnostics.invalid_sample_count += 1
            continue
        history.append(record)
        if len(history) < 3:
            diagnostics.buffered_sample_count += 1
            continue

        delta_theta_1, delta_velocity_1, dt_1 = _SubInterval_Compute(history[0], history[1])
        delta_theta_2, delta_velocity_2, dt_2 = _SubInterval_Compute(history[1], history[2])
        if dt_1 < dt_min or dt_1 > dt_max or dt_2 < dt_min or dt_2 > dt_max:
            diagnostics.sample_gap_count += 1
            history = [history[2]]
            continue

        coning = (
            delta_theta_1
            + delta_theta_2
            + np.float32(2.0 / 3.0) * _Vector_Cross(delta_theta_1, delta_theta_2)
        )
        delta_theta_sum = delta_theta_1 + delta_theta_2
        delta_velocity_sum = delta_velocity_1 + delta_velocity_2
        sculling = (
            delta_velocity_sum
            + np.float32(0.5) * _Vector_Cross(delta_theta_sum, delta_velocity_sum)
            + np.float32(2.0 / 3.0)
            * (
                _Vector_Cross(delta_theta_1, delta_velocity_2)
                + _Vector_Cross(delta_velocity_1, delta_theta_2)
            )
        )
        increments.append(
            InertialIncrement(
                interval_start_timestamp_us=int(history[0].payload["sample_timestamp_us"]),
                interval_end_timestamp_us=timestamp,
                ordering_sequence=record.record_sequence,
                source_sequence=int(record.payload.get("sequence", record.record_sequence)),
                dt_s=np.float32(dt_1 + dt_2),
                delta_theta_b=np.asarray(coning, dtype=np.float32),
                delta_velocity_b=np.asarray(sculling, dtype=np.float32),
            )
        )
        history = [history[2]]
    return tuple(increments), diagnostics


def InertialIncrement_ReadRecorded(
    records: tuple[DecodedRecord, ...],
    *,
    start_timestamp_us: int,
    end_timestamp_us: int | None = None,
) -> tuple[InertialIncrement, ...]:
    increments: list[InertialIncrement] = []
    for record in sorted(records, key=lambda item: item.record_sequence):
        payload = record.payload
        end_timestamp = int(payload["interval_end_timestamp_us"])
        dt = np.float32(payload["dt_s"])
        if end_timestamp < start_timestamp_us or not np.isfinite(dt) or dt <= 0.0:
            continue
        if end_timestamp_us is not None and end_timestamp > end_timestamp_us:
            continue
        increments.append(
            InertialIncrement(
                interval_start_timestamp_us=int(payload["interval_start_timestamp_us"]),
                interval_end_timestamp_us=end_timestamp,
                ordering_sequence=record.record_sequence,
                source_sequence=int(payload["sequence"]),
                dt_s=dt,
                delta_theta_b=np.asarray(payload["delta_theta_b_corrected"], dtype=np.float32),
                delta_velocity_b=np.asarray(
                    payload["delta_velocity_b_sculling_corrected"], dtype=np.float32
                ),
                health_flags=int(payload["health_flags"]),
            )
        )
    return tuple(increments)


def Mechanization_Run(
    increments: tuple[InertialIncrement, ...],
    *,
    initial_q_nb: NDArray[np.floating],
    gravity_mps2: float,
    initial_velocity_enu_mps: NDArray[np.floating] | None = None,
    initial_position_enu_m: NDArray[np.floating] | None = None,
) -> tuple[MechanizationOutput, ...]:
    q_nb = Quaternion_Normalize(initial_q_nb)
    velocity = np.zeros(3, dtype=np.float32)
    position = np.zeros(3, dtype=np.float32)
    if initial_velocity_enu_mps is not None:
        velocity = np.asarray(initial_velocity_enu_mps, dtype=np.float32).copy()
    if initial_position_enu_m is not None:
        position = np.asarray(initial_position_enu_m, dtype=np.float32).copy()
    gravity = np.float32(gravity_mps2)
    if not np.isfinite(gravity) or gravity <= 0.0:
        raise ValueError("gravity_invalid")

    outputs: list[MechanizationOutput] = []
    for increment in increments:
        dt = np.float32(increment.dt_s)
        if not np.isfinite(dt) or dt <= 0.0:
            continue
        q_start = q_nb.copy()
        rotated_delta_velocity = Quaternion_RotateVector(q_start, increment.delta_velocity_b)
        delta_velocity_enu = rotated_delta_velocity.copy()
        delta_velocity_enu[2] -= gravity * dt
        velocity_previous = velocity.copy()
        velocity = np.asarray(velocity_previous + delta_velocity_enu, dtype=np.float32)
        position = np.asarray(
            position + np.float32(0.5) * (velocity_previous + velocity) * dt,
            dtype=np.float32,
        )
        q_nb = Quaternion_PropagateBodyIncrement(q_start, increment.delta_theta_b)
        specific_force = np.asarray(rotated_delta_velocity / dt, dtype=np.float32)
        linear_accel = specific_force.copy()
        linear_accel[2] -= gravity
        outputs.append(
            MechanizationOutput(
                timestamp_us=increment.interval_end_timestamp_us,
                ordering_sequence=increment.ordering_sequence,
                source_sequence=increment.source_sequence,
                dt_s=dt,
                q_nb=q_nb.copy(),
                velocity_enu_mps=velocity.copy(),
                position_enu_m=position.copy(),
                specific_force_enu_mps2=specific_force,
                linear_accel_enu_mps2=linear_accel,
                delta_velocity_enu_mps=delta_velocity_enu,
                delta_theta_b=increment.delta_theta_b.copy(),
                delta_velocity_b=increment.delta_velocity_b.copy(),
                health_flags=increment.health_flags,
            )
        )
    return tuple(outputs)


def Mechanization_ConfigurationGet(dataset: Any) -> dict[str, Any]:
    records = dataset.Records_Get("SYSTEM_CONFIG")
    if not records:
        return {
            "minimum_sample_rate_hz": 50.0,
            "maximum_sample_rate_hz": 500.0,
            "subsample_count": int(dataset.header.get("mechanization_subsample_count", 2)),
            "imu_corrected_decimation": None,
            "inertial_increment_decimation": None,
        }
    start_timestamp = dataset.start_timestamp_us
    selected = (
        dataset.RecordAtOrBefore_Get("SYSTEM_CONFIG", start_timestamp)
        if start_timestamp is not None
        else None
    )
    if selected is None:
        selected = max(
            records,
            key=lambda item: (
                item.timestamp_us,
                item.record_sequence,
                item.file_offset,
            ),
        )
    payload = selected.payload
    decimation = tuple(payload.get("log_decimation", ()))
    corrected_decimation = payload.get("imu_corrected_decimation")
    increment_decimation = decimation[5] if len(decimation) > 5 else None
    semantic_context = dataset.semantic_context
    if semantic_context is not None:
        for stream in semantic_context.logging_streams:
            record_name = str(stream.get("record", "")).upper()
            value = stream.get("decimation_factor")
            if record_name.endswith("_IMU_CORRECTED") and value is not None:
                corrected_decimation = value
            elif record_name.endswith("_INERTIAL_INCREMENT") and value is not None:
                increment_decimation = value
    return {
        "minimum_sample_rate_hz": float(
            payload.get("mechanization_min_sample_rate_hz", 50.0)
        ),
        "maximum_sample_rate_hz": float(
            payload.get("mechanization_max_sample_rate_hz", 500.0)
        ),
        "subsample_count": int(
            payload.get(
                "mechanization_subsample_count",
                dataset.header.get("mechanization_subsample_count", 2),
            )
        ),
        "imu_corrected_decimation": (
            int(corrected_decimation)
            if corrected_decimation is not None
            else None
        ),
        "inertial_increment_decimation": (
            int(increment_decimation)
            if increment_decimation is not None
            else None
        ),
    }
