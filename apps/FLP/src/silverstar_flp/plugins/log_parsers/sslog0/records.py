from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from silverstar_flp.core.dataset import ChannelDefinition


class PayloadDecodeError(ValueError):
    pass


class PayloadReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self._payload) - self.offset

    def _unpack(self, format_text: str) -> tuple[Any, ...]:
        size = struct.calcsize(format_text)
        if self.offset + size > len(self._payload):
            raise PayloadDecodeError(
                f"payload_underflow:offset={self.offset}:need={size}:size={len(self._payload)}"
            )
        values = struct.unpack_from("<" + format_text, self._payload, self.offset)
        self.offset += size
        return values

    def u8(self) -> int:
        return int(self._unpack("B")[0])

    def i8(self) -> int:
        return int(self._unpack("b")[0])

    def u16(self) -> int:
        return int(self._unpack("H")[0])

    def i16(self) -> int:
        return int(self._unpack("h")[0])

    def u32(self) -> int:
        return int(self._unpack("I")[0])

    def i32(self) -> int:
        return int(self._unpack("i")[0])

    def u64(self) -> int:
        return int(self._unpack("Q")[0])

    def f32(self) -> float:
        return float(self._unpack("f")[0])

    def bytes(self, count: int) -> bytes:
        if count < 0 or self.offset + count > len(self._payload):
            raise PayloadDecodeError("payload_underflow")
        value = self._payload[self.offset : self.offset + count]
        self.offset += count
        return value

    def skip(self, count: int) -> None:
        self.bytes(count)

    def array(self, kind: str, count: int) -> tuple[Any, ...]:
        return tuple(self._unpack(kind * count))

    def finish(self) -> None:
        if self.remaining != 0:
            raise PayloadDecodeError(f"payload_trailing_bytes:{self.remaining}")


PayloadDecoder = Callable[[bytes], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RecordDefinition:
    type_id: int
    name: str
    common_versions: tuple[int, ...]
    payload_lengths: tuple[int, ...]
    decoder: PayloadDecoder
    channels: tuple[ChannelDefinition, ...] = ()


EVENT_NAMES = {
    0x01: "BOOT",
    0x02: "ALIGNMENT_COMPLETE",
    0x03: "MISSION_START",
    0x04: "INS_RESET",
    0x05: "SAMPLE_GAP",
    0x06: "LOGGER_OVERFLOW",
    0x07: "SD_ERROR",
    0x08: "ALIGNMENT_CANDIDATE_READY",
    0x09: "ALIGNMENT_APPLIED",
    0x0A: "ALIGNMENT_REJECTED",
    0x0B: "IMU_ALGORITHM_MISMATCH",
    0x0C: "ATTITUDE_INIT_FAILED",
    0x0D: "ESTIMATOR_PREDICTION_OVERFLOW",
    0x0E: "SYSTEM_FAULT",
    0x0F: "SELF_TEST_COMPLETE",
    0x10: "GNSS_FIX_ACQUIRED",
    0x11: "GNSS_FIX_LOST",
    0x12: "ORIGIN_WINDOW_READY",
    0x13: "STARTUP_DEVICE_RESULT",
    0x14: "STARTUP_CONFIG_MASKS",
    0x15: "STARTUP_CONFIG_FAILURES",
    0x16: "STARTUP_DEVICE_DETAIL",
    0x17: "STARTUP_DEVICE_NAMES",
    0x18: "IMU_BIAS_WAIT",
    0x19: "IMU_BIAS_COMPLETE",
    0x1A: "BARO_FUSION_STATE",
    0x1B: "START_REJECTED",
    0x1C: "GNSS_CONFIG_TRANSACTION",
    0x1D: "GNSS_NAV_SAT_DIAGNOSTIC",
    0x1E: "GNSS_MON_RF_DIAGNOSTIC",
    0x1F: "GNSS_NAV_SAT_TRANSACTION_DETAIL",
    0x20: "GNSS_MON_RF_TRANSACTION_DETAIL",
    0x21: "CALIBRATION_START",
    0x22: "CALIBRATION_FACE_COMPLETE",
    0x23: "CALIBRATION_READY",
    0x24: "CALIBRATION_FAILED",
    0x25: "CALIBRATION_RESULT",
    0x26: "ALIGNMENT_START",
    0x27: "ALIGNMENT_READY",
    0x28: "ALIGNMENT_FAILED",
    0x29: "PARACHUTE_DEPLOY",
    0x2A: "LANDING",
    0x2B: "PARACHUTE_DEPLOY_DETAIL",
    0x2C: "LANDING_IMPACT",
    0x2D: "SENSOR_SOURCE_CHANGE",
    0x2E: "GNSS_POSITION_INTEGRITY_STATE_CHANGE",
    0x2F: "NAV_FUSION_STATE_CHANGE",
}


def _Payload_FloatBits(value: int) -> float:
    return float(struct.unpack("<f", struct.pack("<I", value & 0xFFFFFFFF))[0])


def _Payload_LegacySampleDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_sequence": reader.u32(),
        "dt_us": reader.u32(),
        "accel_raw": reader.array("h", 3),
        "gyro_raw": reader.array("h", 3),
        "mag_raw": reader.array("h", 3),
        "quaternion_raw_q15": reader.array("h", 4),
        "pressure_pa": reader.i32(),
        "height_cm": reader.i32(),
        "accel_b_mps2": reader.array("f", 3),
        "gyro_b_radps": reader.array("f", 3),
        "q_raw": reader.array("f", 4),
        "q_nb": reader.array("f", 4),
        "delta_theta_b": reader.array("f", 3),
        "delta_velocity_b_basic": reader.array("f", 3),
        "delta_velocity_b_rotation_corrected": reader.array("f", 3),
        "delta_velocity_b_sculling_corrected": reader.array("f", 3),
        "delta_velocity_n_corrected": reader.array("f", 3),
        "velocity_n_mps": reader.array("f", 3),
        "position_n_m": reader.array("f", 3),
        "alignment_valid": reader.u8(),
        "ins_valid": reader.u8(),
        "health_flags": reader.u32(),
        "imu_queue_overflow_count": reader.u32(),
        "logger_queue_overflow_count": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_EventDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    event_id = reader.u8()
    reader.skip(3)
    arg0 = reader.u32()
    arg1 = reader.u32()
    reader.finish()
    return {
        "event_id": event_id,
        "event_name": EVENT_NAMES.get(event_id, f"UNKNOWN_EVENT_0x{event_id:02X}"),
        "arg0": arg0,
        "arg1": arg1,
        "arg0_float": _Payload_FloatBits(arg0),
        "arg1_float": _Payload_FloatBits(arg1),
    }


def _Payload_StatsDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "imu_queue_overflow_count": reader.u32(),
        "logger_queue_overflow_count": reader.u32(),
        "ins_update_count": reader.u32(),
        "health_flags": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_Kf6StateDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "position_enu_m": reader.array("f", 3),
        "velocity_enu_mps": reader.array("f", 3),
        "covariance_diagonal": reader.array("f", 6),
        "gnss_position_enu_m": reader.array("f", 3),
        "gnss_velocity_enu_mps": reader.array("f", 3),
        "baro_relative_altitude_m": reader.f32(),
        "last_position_nis": reader.f32(),
        "last_velocity_nis": reader.f32(),
        "last_baro_nis": reader.f32(),
        "measurement_result_flags": reader.u32(),
        "health_flags": reader.u32(),
        "prediction_queue_overflow_count": reader.u32(),
        "gnss_sequence": reader.u32(),
        "baro_sequence": reader.u32(),
        "gnss_timestamp_us": reader.u64(),
        "baro_timestamp_us": reader.u64(),
        "gnss_measurement_age_us": reader.u32(),
        "baro_measurement_age_us": reader.u32(),
        "gnss_origin_valid": reader.u8(),
        "baro_origin_valid": reader.u8(),
        "initialized": reader.u8(),
        "mission_running": reader.u8(),
    }
    reader.finish()
    return result


def _Payload_SystemConfigDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "firmware_version": tuple(reader.bytes(4)),
        "profile_id": reader.u32(),
        "provider_ids": tuple(reader.bytes(10)),
        "algorithm_ids": tuple(reader.bytes(4)),
        "log_sink_id": reader.u8(),
        "imu_corrected_decimation": reader.u8(),
        "p0_diagonal": reader.array("f", 6),
        "process_accel_std_mps2": reader.array("f", 3),
        "measurement_profile": reader.array("f", 5),
        "nis_profile": reader.array("f", 7),
        "log_mask": reader.u32(),
        "device_config_digest": reader.u32(),
        "configured_imu_rate_hz": reader.u16(),
        "configured_gnss_rate_hz": reader.u16(),
        "configured_magnetometer_rate_hz": reader.u16(),
        "configured_barometer_rate_hz": reader.u16(),
        "configured_hardware_quaternion_rate_hz": reader.u16(),
        "mechanization_subsample_count": reader.u16(),
        "expected_ins_rate_hz": reader.u16(),
        "mechanization_min_sample_rate_hz": reader.u16(),
        "mechanization_max_sample_rate_hz": reader.u16(),
        "log_profile_id": reader.u16(),
        "log_decimation": reader.array("H", 10),
        "power_log_period_us": reader.u32(),
        "health_log_period_us": reader.u32(),
        "telemetry_log_period_us": reader.u32(),
        "sync_period_us": reader.u32(),
        "aggregation_buffer_size": reader.u16(),
        "normal_queue_depth": reader.u8(),
        "estimator_queue_depth": reader.u8(),
    }
    reader.finish()
    return result


def _Payload_RawSensorDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "imu_sample_timestamp_us": reader.u64(),
        "imu_receive_timestamp_us": reader.u64(),
        "imu_sequence": reader.u32(),
        "accel_raw": reader.array("i", 3),
        "gyro_raw": reader.array("i", 3),
        "accel_b_mps2": reader.array("f", 3),
        "gyro_b_radps": reader.array("f", 3),
        "imu_temperature_c": reader.f32(),
        "imu_valid_mask": reader.u32(),
        "mag_raw": reader.array("i", 3),
        "magnetic_field_b_ut": reader.array("f", 3),
        "mag_valid_mask": reader.u32(),
        "mag_calibration_valid": reader.u8(),
    }
    reader.skip(3)
    result.update(
        {
            "pressure_raw_pa": reader.i32(),
            "altitude_raw_cm": reader.i32(),
            "pressure_pa": reader.f32(),
            "altitude_m": reader.f32(),
            "barometer_valid_mask": reader.u32(),
        }
    )
    reader.skip(4)
    reader.finish()
    return result


def _Payload_PureInsDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "update_sequence": reader.u32(),
        "q_nb": reader.array("f", 4),
        "velocity_enu_mps": reader.array("f", 3),
        "position_enu_m": reader.array("f", 3),
        "accel_enu_mps2": reader.array("f", 3),
        "dt_s": reader.f32(),
        "health_flags": reader.u32(),
        "alignment_valid": reader.u8(),
        "ins_valid": reader.u8(),
    }
    reader.skip(2)
    reader.finish()
    return result


def _Payload_Kf6DiagnosticDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "position_innovation": reader.array("f", 3),
        "velocity_innovation": reader.array("f", 3),
        "baro_innovation": reader.f32(),
        "position_variance_r": reader.array("f", 3),
        "velocity_variance_r": reader.array("f", 3),
        "baro_variance_r": reader.f32(),
        "position_nis": reader.f32(),
        "velocity_nis": reader.f32(),
        "baro_nis": reader.f32(),
        "position_r_scale": reader.f32(),
        "velocity_r_scale": reader.f32(),
        "baro_r_scale": reader.f32(),
        "process_accel_std_mps2": reader.array("f", 3),
        "gnss_velocity_valid_mask": reader.u8(),
        "velocity_update_dimension": reader.u8(),
        "position_update_result": reader.u8(),
        "velocity_update_result": reader.u8(),
        "baro_update_result": reader.u8(),
    }
    reader.skip(7)
    reader.finish()
    result["update_results"] = (
        result["position_update_result"],
        result["velocity_update_result"],
        result["baro_update_result"],
    )
    result["measurement_r_scale"] = (
        result["position_r_scale"],
        result["velocity_r_scale"],
        result["baro_r_scale"],
    )
    return result


def _Payload_Kf6FullPDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {"covariance_upper_triangle": reader.array("f", 21)}
    reader.finish()
    return result


def _Payload_PowerDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "voltage_v": reader.f32(),
        "current_a": reader.f32(),
        "power_w": reader.f32(),
        "state_of_charge_percent": reader.f32(),
        "temperature_c": reader.f32(),
        "valid_mask": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_HealthDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "compiled_mask": reader.u32(),
        "enabled_mask": reader.u32(),
        "present_mask": reader.u32(),
        "healthy_mask": reader.u32(),
        "start_blocking_mask": reader.u32(),
        "warning_mask": reader.u32(),
        "sequence": reader.u32(),
        "ready": reader.u8(),
    }
    reader.skip(3)
    reader.finish()
    return result


def _Payload_TelemetryDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "last_transmit_timestamp_us": reader.u64(),
        "last_receive_timestamp_us": reader.u64(),
        "transmit_packet_count": reader.u32(),
        "receive_packet_count": reader.u32(),
        "transmit_error_count": reader.u32(),
        "receive_error_count": reader.u32(),
        "integrity_error_count": reader.u32(),
        "last_rssi_dbm": reader.i16(),
        "last_snr_q4": reader.i8(),
        "online": reader.u8(),
    }
    reader.skip(8)
    reader.finish()
    return result


def _Payload_InitialStateDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "alignment_algorithm": reader.u8(),
        "hardware_mode": reader.u8(),
        "mode_verified": reader.u8(),
        "origin_valid_flags": reader.u8(),
        "alignment_sample_count": reader.u16(),
        "gnss_sample_count": reader.u16(),
        "barometer_sample_count": reader.u16(),
        "reserved": reader.u16(),
        "q_nb": reader.array("f", 4),
        "acceleration_mean_b_mps2": reader.array("f", 3),
        "gyro_mean_b_radps": reader.array("f", 3),
        "magnetic_field_mean_b_ut": reader.array("f", 3),
        "gnss_origin_latitude_e7": reader.i32(),
        "gnss_origin_longitude_e7": reader.i32(),
        "gnss_origin_height_mm": reader.i32(),
        "gnss_origin_position_std_m": reader.array("f", 3),
        "initial_velocity_enu_mps": reader.array("f", 3),
        "initial_velocity_std_mps": reader.array("f", 3),
        "barometer_origin_altitude_m": reader.f32(),
        "barometer_origin_std_m": reader.f32(),
        "p0_diagonal": reader.array("f", 6),
    }
    reader.finish()
    return result


def _Payload_ImuNativeDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "accel_raw": reader.array("i", 3),
        "gyro_raw": reader.array("i", 3),
        "accel_b_mps2": reader.array("f", 3),
        "gyro_b_radps": reader.array("f", 3),
        "temperature_c": reader.f32(),
        "valid_mask": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_GnssNativeDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "latitude_e7": reader.i32(),
        "longitude_e7": reader.i32(),
        "ellipsoid_height_mm": reader.i32(),
        "msl_height_mm": reader.i32(),
        "velocity_enu_mps": reader.array("f", 3),
        "velocity_variance_m2ps2": reader.array("f", 3),
        "horizontal_accuracy_m": reader.f32(),
        "vertical_accuracy_m": reader.f32(),
        "speed_accuracy_mps": reader.f32(),
        "velocity_valid_mask": reader.u8(),
        "fix_type": reader.u8(),
        "position_usable": reader.u8(),
        "course_usable": reader.u8(),
        "online": reader.u8(),
    }
    reader.skip(3)
    reader.finish()
    return result


def _Payload_BaroNativeDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "pressure_raw_pa": reader.i32(),
        "altitude_raw_cm": reader.i32(),
        "pressure_pa": reader.f32(),
        "altitude_m": reader.f32(),
        "altitude_variance_m2": reader.f32(),
        "valid_mask": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_MagNativeDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "raw": reader.array("i", 3),
        "magnetic_field_b_ut": reader.array("f", 3),
        "temperature_c": reader.f32(),
        "valid_mask": reader.u32(),
        "calibration_valid": reader.u8(),
    }
    reader.skip(3)
    reader.finish()
    return result


def _Payload_HardwareQuaternionDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "quaternion_wxyz": reader.array("f", 4),
        "mode": reader.u8(),
        "mode_verified": reader.u8(),
        "algorithm_healthy": reader.u8(),
        "normalized": reader.u8(),
        "valid": reader.u8(),
    }
    reader.skip(3)
    reader.finish()
    return result


def _Payload_InertialIncrementDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "interval_start_timestamp_us": reader.u64(),
        "interval_end_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "dt_s": reader.f32(),
        "delta_theta_b_corrected": reader.array("f", 3),
        "delta_velocity_b_sculling_corrected": reader.array("f", 3),
        "health_flags": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_GnssMeasurementDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "position_enu_m": reader.array("f", 3),
        "velocity_enu_mps": reader.array("f", 3),
        "position_variance_m2": reader.array("f", 3),
        "velocity_variance_m2ps2": reader.array("f", 3),
        "velocity_valid_mask": reader.u8(),
        "position_usable": reader.u8(),
        "fusion_allowed": reader.u8(),
        "reserved": reader.u8(),
    }
    reader.finish()
    return result


def _Payload_BaroMeasurementDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "relative_altitude_m": reader.f32(),
        "variance_m2": reader.f32(),
        "valid_mask": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_ImuCorrectedDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "sample_timestamp_us": reader.u64(),
        "receive_timestamp_us": reader.u64(),
        "sequence": reader.u32(),
        "source_id": reader.u16(),
        "virtual_imu_id": reader.u16(),
        "valid_mask": reader.u32(),
        "accel_b_mps2": reader.array("f", 3),
        "gyro_b_radps": reader.array("f", 3),
        "temperature_c": reader.f32(),
        "calibration_mode": reader.u8(),
        "correction_valid": reader.u8(),
        "reserved": reader.u16(),
    }
    reader.finish()
    return result


def _Payload_CalibrationResultDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "source_id": reader.u16(),
        "virtual_imu_id": reader.u16(),
        "mode": reader.u8(),
        "state": reader.u8(),
        "ready": reader.u8(),
        "completed_face_mask": reader.u8(),
        "samples": reader.u32(),
        "reject_count": reader.u32(),
        "retry_count": reader.u32(),
        "start_sequence": reader.u32(),
        "accel_bias_mps2": reader.array("f", 3),
        "accel_scale": reader.array("f", 3),
        "gyro_bias_radps": reader.array("f", 3),
        "gyro_scale": reader.array("f", 3),
    }
    reader.finish()
    return result


def _Payload_AlignmentResultDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "capability_mask": reader.u32(),
        "selected_mask": reader.u32(),
        "required_mask": reader.u32(),
        "ready_mask": reader.u32(),
        "unavailable_mask": reader.u32(),
        "missing_adapter_mask": reader.u32(),
        "start_sequence": reader.u32(),
        "state": reader.u8(),
        "config_result": reader.u8(),
        "ready": reader.u8(),
        "source_count": reader.u8(),
        "attitude_timestamp_us": reader.u64(),
        "q_nb": reader.array("f", 4),
        "gnss_origin_lat_e7": reader.i32(),
        "gnss_origin_lon_e7": reader.i32(),
        "gnss_origin_height_mm": reader.i32(),
        "gnss_sample_count": reader.u32(),
        "gnss_horizontal_accuracy_m": reader.f32(),
        "gnss_vertical_accuracy_m": reader.f32(),
        "barometer_sample_count": reader.u32(),
        "barometer_origin_pressure_pa": reader.f32(),
        "barometer_origin_altitude_m": reader.f32(),
        "attitude_state": reader.u8(),
        "gnss_state": reader.u8(),
        "barometer_state": reader.u8(),
        "attitude_source": reader.u8(),
    }
    reader.finish()
    return result


def _Payload_AlignmentEvidenceDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "alignment_algorithm": reader.u8(),
        "constraint_count": reader.u8(),
        "valid_pair_count": reader.u8(),
        "yaw_authoritative": reader.u8(),
        "imu_source_instance": reader.u8(),
        "magnetometer_instance": reader.u8(),
        "external_source_instance": reader.u8(),
        "failure_reason": reader.u8(),
        "magnetometer_physical_device_id": reader.u16(),
        "flags": reader.u16(),
        "mag_calibration_generation": reader.u32(),
        "mag_calibration_set_hash": reader.u32(),
        "first_timestamp_us": reader.u64(),
        "last_timestamp_us": reader.u64(),
        "minimum_pair_sine": reader.f32(),
        "rms_mismatch_rad": reader.f32(),
        "max_mismatch_rad": reader.f32(),
    }
    reader.finish()
    return result


def _Payload_MissionSnapshotIdentityDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "mission_id": reader.u32(),
        "commit_generation": reader.u32(),
        "snapshot_sequence": reader.u32(),
        "imu_calibration_generation": reader.u32(),
        "mag_calibration_set_hash": reader.u32(),
        "base_instance": reader.u8(),
        "ready": reader.u8(),
        "reserved": reader.u16(),
    }
    reader.finish()
    return result


def _Payload_MagCalibrationIdentityDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    result = {
        "physical_device_id": reader.u16(),
        "instance_id": reader.u8(),
        "active": reader.u8(),
        "saved": reader.u8(),
        "load_error": reader.u8(),
        "reserved": reader.u16(),
        "generation": reader.u32(),
        "calibration_set_hash": reader.u32(),
    }
    reader.finish()
    return result


def _Payload_MissionConfigDecode(payload: bytes) -> dict[str, Any]:
    reader = PayloadReader(payload)
    internal_version = reader.u8()
    if internal_version not in (1, 2):
        raise PayloadDecodeError(f"unsupported_mission_config_version:{internal_version}")
    result = {
        "internal_record_version": internal_version,
        "alignment_algorithm": reader.u8(),
        "rocket_longitudinal_axis": reader.u8(),
        "deploy_trigger_mask": reader.u8(),
        "tilt_reference": reader.u8(),
        "landing_enable": reader.u8(),
        "landing_mode": reader.u8(),
        "impact_capable": reader.u8(),
        "known_yaw_deg": reader.f32(),
        "magnetic_declination_deg": reader.f32(),
        "tilt_threshold_deg": reader.f32(),
        "apogee_vz_threshold_mps": reader.f32(),
        "deploy_confirm_ms": reader.u32(),
        "deploy_delay_ms": reader.u32(),
        "baro_trigger_window_ms": reader.u32(),
        "baro_trigger_min_samples": reader.u32(),
        "baro_trigger_rate_mps": reader.f32(),
        "candidate_duration_ms": reader.u32(),
        "baro_confirm_rate_mps": reader.f32(),
    }
    if internal_version == 2:
        result.update(
            {
                "baro_max_span_m": reader.f32(),
                "candidate_baro_min_samples": reader.u32(),
                "candidate_imu_min_samples": reader.u32(),
                "candidate_min_coverage_percent": reader.u32(),
                "impact_inhibit_ms": reader.u32(),
                "impact_threshold_mps2": reader.f32(),
                "still_gyro_threshold_radps": reader.f32(),
                "still_accel_tolerance_mps2": reader.f32(),
                "landing_confirm_ms": reader.u32(),
                "landing_sample_max_age_ms": reader.u32(),
            }
        )
    reader.finish()
    return result


def _Channel(
    channel_id: str,
    field_name: str,
    unit: str,
    quantity: str,
    columns: tuple[str, ...] = (),
    timestamp_field: str | None = None,
    validity_field: str | None = None,
    validity_mask: int | None = None,
) -> ChannelDefinition:
    return ChannelDefinition(
        channel_id=channel_id,
        field_name=field_name,
        unit=unit,
        quantity=quantity,
        columns=columns,
        timestamp_field=timestamp_field,
        validity_field=validity_field,
        validity_mask=validity_mask,
    )


XYZ = ("X", "Y", "Z")
ENU = ("E", "N", "U")
WXYZ = ("W", "X", "Y", "Z")


RECORD_DEFINITIONS = {
    definition.type_id: definition
    for definition in (
        RecordDefinition(0x01, "LEGACY_SAMPLE", (0,), (196,), _Payload_LegacySampleDecode),
        RecordDefinition(0x02, "EVENT", (0,), (12,), _Payload_EventDecode),
        RecordDefinition(0x03, "STATS", (0,), (16,), _Payload_StatsDecode),
        RecordDefinition(
            0x04,
            "KF6_STATE",
            (0,),
            (136,),
            _Payload_Kf6StateDecode,
            (
                _Channel(
                    "kf6.recorded.navigation.position_enu", "position_enu_m", "m", "position", ENU
                ),
                _Channel(
                    "kf6.recorded.navigation.velocity_enu",
                    "velocity_enu_mps",
                    "m/s",
                    "velocity",
                    ENU,
                ),
                _Channel(
                    "kf6.recorded.covariance.diagonal",
                    "covariance_diagonal",
                    "mixed",
                    "covariance",
                    ("pE", "pN", "pU", "vE", "vN", "vU"),
                ),
                _Channel("kf6.recorded.nis.position", "last_position_nis", "1", "nis"),
                _Channel("kf6.recorded.nis.velocity", "last_velocity_nis", "1", "nis"),
                _Channel("kf6.recorded.nis.baro", "last_baro_nis", "1", "nis"),
                _Channel(
                    "kf6.recorded.measurement_result_flags",
                    "measurement_result_flags",
                    "bitmask",
                    "status",
                ),
                _Channel(
                    "kf6.recorded.measurement_age.gnss",
                    "gnss_measurement_age_us",
                    "us",
                    "time",
                ),
                _Channel(
                    "kf6.recorded.measurement_age.baro",
                    "baro_measurement_age_us",
                    "us",
                    "time",
                ),
                _Channel(
                    "kf6.recorded.measurement_sequence.gnss",
                    "gnss_sequence",
                    "1",
                    "sequence",
                ),
                _Channel(
                    "kf6.recorded.measurement_sequence.baro",
                    "baro_sequence",
                    "1",
                    "sequence",
                ),
            ),
        ),
        RecordDefinition(0x05, "SYSTEM_CONFIG", (0,), (176,), _Payload_SystemConfigDecode),
        RecordDefinition(0x06, "RAW_SENSOR", (0,), (132,), _Payload_RawSensorDecode),
        RecordDefinition(
            0x07,
            "PURE_INS",
            (0,),
            (68,),
            _Payload_PureInsDecode,
            (
                _Channel(
                    "pure_ins.recorded.attitude.q_nb",
                    "q_nb",
                    "1",
                    "quaternion",
                    WXYZ,
                    validity_field="ins_valid",
                ),
                _Channel(
                    "pure_ins.recorded.navigation.velocity_enu",
                    "velocity_enu_mps",
                    "m/s",
                    "velocity",
                    ENU,
                    validity_field="ins_valid",
                ),
                _Channel(
                    "pure_ins.recorded.navigation.position_enu",
                    "position_enu_m",
                    "m",
                    "position",
                    ENU,
                    validity_field="ins_valid",
                ),
                _Channel(
                    "pure_ins.recorded.navigation.linear_accel_enu",
                    "accel_enu_mps2",
                    "m/s^2",
                    "acceleration",
                    ENU,
                    validity_field="ins_valid",
                ),
            ),
        ),
        RecordDefinition(
            0x08,
            "KF6_DIAGNOSTIC",
            (0,),
            (104,),
            _Payload_Kf6DiagnosticDecode,
            (
                _Channel(
                    "kf6.recorded.innovation.position",
                    "position_innovation",
                    "m",
                    "innovation",
                    ENU,
                ),
                _Channel(
                    "kf6.recorded.innovation.velocity",
                    "velocity_innovation",
                    "m/s",
                    "innovation",
                    ENU,
                ),
                _Channel("kf6.recorded.innovation.baro", "baro_innovation", "m", "innovation"),
                _Channel(
                    "kf6.recorded.measurement_r.position",
                    "position_variance_r",
                    "m^2",
                    "variance",
                    ENU,
                ),
                _Channel(
                    "kf6.recorded.measurement_r.velocity",
                    "velocity_variance_r",
                    "m^2/s^2",
                    "variance",
                    ENU,
                ),
                _Channel(
                    "kf6.recorded.measurement_r.baro",
                    "baro_variance_r",
                    "m^2",
                    "variance",
                ),
                _Channel(
                    "kf6.recorded.measurement_r_scale",
                    "measurement_r_scale",
                    "1",
                    "scale",
                    ("GNSS position", "GNSS velocity", "Barometer"),
                ),
                _Channel(
                    "kf6.recorded.update_result",
                    "update_results",
                    "enum",
                    "update_result",
                    ("GNSS position", "GNSS velocity", "Barometer"),
                ),
                _Channel(
                    "kf6.recorded.velocity_valid_mask",
                    "gnss_velocity_valid_mask",
                    "bitmask",
                    "status",
                ),
                _Channel(
                    "kf6.recorded.velocity_update_dimension",
                    "velocity_update_dimension",
                    "1",
                    "dimension",
                ),
            ),
        ),
        RecordDefinition(
            0x09,
            "KF6_FULL_P",
            (0,),
            (84,),
            _Payload_Kf6FullPDecode,
            (
                _Channel(
                    "kf6.recorded.covariance.upper_triangle",
                    "covariance_upper_triangle",
                    "mixed",
                    "covariance",
                    tuple(f"P{i}" for i in range(21)),
                ),
            ),
        ),
        RecordDefinition(0x0A, "POWER", (0,), (44,), _Payload_PowerDecode),
        RecordDefinition(0x0B, "HEALTH", (0,), (40,), _Payload_HealthDecode),
        RecordDefinition(0x0C, "TELEMETRY_DIAG", (0,), (48,), _Payload_TelemetryDecode),
        RecordDefinition(
            0x0D,
            "INITIAL_STATE",
            (0,),
            (144,),
            _Payload_InitialStateDecode,
            (
                _Channel("initial_state.attitude.q_nb", "q_nb", "1", "quaternion", WXYZ),
                _Channel(
                    "initial_state.navigation.velocity_enu",
                    "initial_velocity_enu_mps",
                    "m/s",
                    "velocity",
                    ENU,
                ),
                _Channel(
                    "initial_state.kf6.p0_diagonal",
                    "p0_diagonal",
                    "mixed",
                    "covariance",
                    ("pE", "pN", "pU", "vE", "vN", "vU"),
                ),
            ),
        ),
        RecordDefinition(
            0x0E,
            "IMU_NATIVE",
            (0,),
            (76,),
            _Payload_ImuNativeDecode,
            (
                _Channel(
                    "imu.native.accel_b",
                    "accel_b_mps2",
                    "m/s^2",
                    "acceleration",
                    XYZ,
                    "sample_timestamp_us",
                    "valid_mask",
                    0x01,
                ),
                _Channel(
                    "imu.native.gyro_b",
                    "gyro_b_radps",
                    "rad/s",
                    "angular_rate",
                    XYZ,
                    "sample_timestamp_us",
                    "valid_mask",
                    0x02,
                ),
                _Channel(
                    "imu.native.temperature",
                    "temperature_c",
                    "degC",
                    "temperature",
                    (),
                    "sample_timestamp_us",
                    "valid_mask",
                ),
            ),
        ),
        RecordDefinition(
            0x0F,
            "GNSS_NATIVE",
            (0,),
            (80,),
            _Payload_GnssNativeDecode,
            (
                _Channel(
                    "gnss.native.velocity_enu",
                    "velocity_enu_mps",
                    "m/s",
                    "velocity",
                    ENU,
                    "sample_timestamp_us",
                    "velocity_valid_mask",
                    0x03,
                ),
                _Channel(
                    "gnss.native.velocity_variance",
                    "velocity_variance_m2ps2",
                    "m^2/s^2",
                    "variance",
                    ENU,
                    "sample_timestamp_us",
                    "velocity_valid_mask",
                    0x03,
                ),
            ),
        ),
        RecordDefinition(
            0x10,
            "BARO_NATIVE",
            (0,),
            (44,),
            _Payload_BaroNativeDecode,
            (
                _Channel(
                    "baro.native.pressure",
                    "pressure_pa",
                    "Pa",
                    "pressure",
                    (),
                    "sample_timestamp_us",
                    "valid_mask",
                ),
                _Channel(
                    "baro.native.altitude",
                    "altitude_m",
                    "m",
                    "altitude",
                    (),
                    "sample_timestamp_us",
                    "valid_mask",
                ),
            ),
        ),
        RecordDefinition(
            0x11,
            "MAG_NATIVE",
            (0,),
            (56,),
            _Payload_MagNativeDecode,
            (
                _Channel(
                    "mag.native.field_b",
                    "magnetic_field_b_ut",
                    "uT",
                    "magnetic_field",
                    XYZ,
                    "sample_timestamp_us",
                    "valid_mask",
                ),
            ),
        ),
        RecordDefinition(
            0x12,
            "HW_QUAT_NATIVE",
            (0,),
            (44,),
            _Payload_HardwareQuaternionDecode,
            (
                _Channel(
                    "hardware_attitude.reference.q_nb",
                    "quaternion_wxyz",
                    "1",
                    "quaternion",
                    WXYZ,
                    "sample_timestamp_us",
                    "valid",
                ),
            ),
        ),
        RecordDefinition(
            0x13,
            "INERTIAL_INCREMENT",
            (0,),
            (52,),
            _Payload_InertialIncrementDecode,
            (
                _Channel(
                    "inertial.increment.delta_theta_b",
                    "delta_theta_b_corrected",
                    "rad",
                    "angle",
                    XYZ,
                    "interval_end_timestamp_us",
                    "__common_valid_flags__",
                    0x03,
                ),
                _Channel(
                    "inertial.increment.delta_velocity_b",
                    "delta_velocity_b_sculling_corrected",
                    "m/s",
                    "velocity_increment",
                    XYZ,
                    "interval_end_timestamp_us",
                    "__common_valid_flags__",
                    0x03,
                ),
                _Channel(
                    "inertial.increment.dt",
                    "dt_s",
                    "s",
                    "time",
                    (),
                    "interval_end_timestamp_us",
                    "__common_valid_flags__",
                    0x03,
                ),
            ),
        ),
        RecordDefinition(
            0x14,
            "GNSS_MEASUREMENT",
            (0,),
            (72,),
            _Payload_GnssMeasurementDecode,
            (
                _Channel(
                    "gnss.measurement.position_enu",
                    "position_enu_m",
                    "m",
                    "position",
                    ENU,
                    "sample_timestamp_us",
                    "position_usable",
                ),
                _Channel(
                    "gnss.measurement.velocity_enu",
                    "velocity_enu_mps",
                    "m/s",
                    "velocity",
                    ENU,
                    "sample_timestamp_us",
                    "velocity_valid_mask",
                    0x03,
                ),
                _Channel(
                    "gnss.measurement.position_variance",
                    "position_variance_m2",
                    "m^2",
                    "variance",
                    ENU,
                    "sample_timestamp_us",
                    "position_usable",
                ),
                _Channel(
                    "gnss.measurement.velocity_variance",
                    "velocity_variance_m2ps2",
                    "m^2/s^2",
                    "variance",
                    ENU,
                    "sample_timestamp_us",
                    "velocity_valid_mask",
                    0x03,
                ),
            ),
        ),
        RecordDefinition(
            0x15,
            "BARO_MEASUREMENT",
            (0,),
            (32,),
            _Payload_BaroMeasurementDecode,
            (
                _Channel(
                    "baro.measurement.relative_altitude",
                    "relative_altitude_m",
                    "m",
                    "altitude",
                    (),
                    "sample_timestamp_us",
                    "valid_mask",
                ),
            ),
        ),
        RecordDefinition(
            0x16,
            "IMU_CORRECTED",
            (0,),
            (60,),
            _Payload_ImuCorrectedDecode,
            (
                _Channel(
                    "imu.corrected.accel_b",
                    "accel_b_mps2",
                    "m/s^2",
                    "acceleration",
                    XYZ,
                    "sample_timestamp_us",
                    "correction_valid",
                ),
                _Channel(
                    "imu.corrected.gyro_b",
                    "gyro_b_radps",
                    "rad/s",
                    "angular_rate",
                    XYZ,
                    "sample_timestamp_us",
                    "correction_valid",
                ),
                _Channel(
                    "imu.corrected.temperature",
                    "temperature_c",
                    "degC",
                    "temperature",
                    (),
                    "sample_timestamp_us",
                    "correction_valid",
                ),
            ),
        ),
        RecordDefinition(0x17, "CALIBRATION_RESULT", (0,), (72,), _Payload_CalibrationResultDecode),
        RecordDefinition(
            0x18,
            "ALIGNMENT_RESULT",
            (0,),
            (96,),
            _Payload_AlignmentResultDecode,
            (
                _Channel(
                    "alignment.result.q_nb",
                    "q_nb",
                    "1",
                    "quaternion",
                    WXYZ,
                    "attitude_timestamp_us",
                    "ready",
                ),
            ),
        ),
        RecordDefinition(0x19, "MISSION_CONFIG", (0,), (52, 92), _Payload_MissionConfigDecode),
        RecordDefinition(
            0x28, "ALIGNMENT_EVIDENCE", (1,), (48,),
            _Payload_AlignmentEvidenceDecode,
        ),
        RecordDefinition(
            0x29, "MISSION_SNAPSHOT_IDENTITY", (1,), (24,),
            _Payload_MissionSnapshotIdentityDecode,
        ),
        RecordDefinition(
            0x2A, "MAG_CALIBRATION_IDENTITY", (1,), (16,),
            _Payload_MagCalibrationIdentityDecode,
        ),
    )
}


RECORD_NAME_BY_ID = {type_id: definition.name for type_id, definition in RECORD_DEFINITIONS.items()}
