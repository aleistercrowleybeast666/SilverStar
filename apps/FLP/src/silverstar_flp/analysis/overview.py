from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.diagnostics import DataQualitySummary


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    timestamp_us: int
    name: str
    category: str
    arg0: int = 0
    arg1: int = 0


@dataclass(frozen=True, slots=True)
class CalibrationOverview:
    present: bool
    configured_modes: tuple[str, ...] = ()
    timestamp_us: int | None = None
    mode: int | None = None
    state: int | None = None
    ready: bool = False
    completed_face_mask: int = 0
    completed_faces: int = 0
    required_faces: int = 0
    samples: int = 0
    reject_count: int = 0
    retry_count: int = 0
    accel_bias_mps2: tuple[float, float, float] | None = None
    accel_scale: tuple[float, float, float] | None = None
    gyro_bias_radps: tuple[float, float, float] | None = None
    gyro_scale: tuple[float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class AlignmentOverview:
    present: bool
    timestamp_us: int | None = None
    mode: int | None = None
    state: int | None = None
    ready: bool = False
    q_nb: tuple[float, float, float, float] | None = None
    quaternion_record: str = ""
    known_yaw_deg: float | None = None
    magnetic_declination_deg: float | None = None
    sample_count: int | None = None
    selected_mask: int | None = None
    ready_mask: int | None = None
    config_result: int | None = None
    attitude_source: int | None = None
    used_sources: tuple[str, ...] = ()
    historical_mode: bool = False
    history_count: int = 0
    ready_history_count: int = 0
    result_timestamp_us: int | None = None
    initial_state_timestamp_us: int | None = None
    initial_state_authoritative: bool = False


@dataclass(frozen=True, slots=True)
class GnssOverview:
    native_configured: bool
    measurement_configured: bool
    native_sample_count: int
    measurement_sample_count: int
    latest_online: bool | None
    latest_fix_type: int | None
    position_usable_count: int
    velocity_usable_count: int


@dataclass(frozen=True, slots=True)
class DeployOverview:
    timestamp_us: int | None
    altitude_m: float | None
    altitude_source: str
    actual_reason_recorded: bool
    actual_trigger_mask: int
    enabled_trigger_mask: int
    trigger_value: float | None
    trigger_value_kind: str
    trigger_threshold: float | None


@dataclass(frozen=True, slots=True)
class FlightSummary:
    source_name: str
    mission_start_timestamp_us: int | None
    start_fallback: bool
    duration_s: float | None
    maximum_altitude_m: float | None
    maximum_speed_mps: float | None
    maximum_acceleration_mps2: float | None
    deploy: DeployOverview
    calibration: CalibrationOverview
    alignment: AlignmentOverview
    gnss: GnssOverview
    data_quality: DataQualitySummary
    timeline: tuple[TimelineEvent, ...]
    decoded_record_count: int
    crc_failure_count: int
    sequence_gap_count: int
    synthetic: bool


def _Navigation_Select(
    dataset: FlightDataset,
) -> tuple[str, TimeSeries | None, TimeSeries | None]:
    candidates = (
        (
            "KF_6",
            "kf6.recorded.navigation.position_enu",
            "kf6.recorded.navigation.velocity_enu",
        ),
        (
            "Pure INS",
            "pure_ins.recorded.navigation.position_enu",
            "pure_ins.recorded.navigation.velocity_enu",
        ),
    )
    selected_position: TimeSeries | None = None
    selected_velocity: TimeSeries | None = None
    available_names: list[str] = []
    for name, position_id, velocity_id in candidates:
        position = dataset.Series_Get(position_id)
        velocity = dataset.Series_Get(velocity_id)
        if position is not None or velocity is not None:
            available_names.append(name)
            if selected_position is None and position is not None:
                selected_position = position
            if selected_velocity is None and velocity is not None:
                selected_velocity = velocity
    if not available_names:
        return "N/A", None, None
    display_order = tuple(
        name for name in ("Pure INS", "KF_6") if name in available_names
    )
    return " / ".join(display_order), selected_position, selected_velocity


def _MissionMask(series: TimeSeries, start_timestamp_us: int | None) -> np.ndarray:
    mask = np.asarray(series.valid, dtype=np.bool_).copy()
    if start_timestamp_us is not None:
        mask &= series.timestamp_us >= np.uint64(start_timestamp_us)
    return mask


def _Maximum_VectorNorm(
    series: TimeSeries | None,
    start_timestamp_us: int | None,
) -> float | None:
    if series is None or series.count == 0:
        return None
    values = np.asarray(series.values, dtype=np.float64)
    valid = _MissionMask(series, start_timestamp_us)
    if values.ndim == 1:
        valid &= np.isfinite(values)
        return float(np.max(np.abs(values[valid]))) if np.any(valid) else None
    valid &= np.all(np.isfinite(values), axis=1)
    return float(np.max(np.linalg.norm(values[valid], axis=1))) if np.any(valid) else None


def _Record_ForMission(
    records: tuple[DecodedRecord, ...],
    start_timestamp_us: int | None,
) -> DecodedRecord | None:
    if not records:
        return None
    ordered = sorted(
        records,
        key=lambda item: (
            item.timestamp_us,
            item.record_sequence,
            item.file_offset,
        ),
    )
    if start_timestamp_us is None:
        return ordered[-1]
    before_start = [record for record in ordered if record.timestamp_us <= start_timestamp_us]
    return before_start[-1] if before_start else None


def _FloatTuple(payload: dict[str, Any] | Any, key: str, length: int) -> tuple[float, ...] | None:
    raw = payload.get(key)
    if raw is None:
        return None
    values = tuple(float(value) for value in raw)
    if len(values) != length or not all(math.isfinite(value) for value in values):
        return None
    return values


def _Calibration_Build(
    dataset: FlightDataset,
    start_timestamp_us: int | None,
) -> CalibrationOverview:
    if dataset.semantic_context is not None:
        semantic_context = dataset.semantic_context
        calibration = semantic_context.calibration
        configured = semantic_context.Modes_Get().get("calibration", ())
        configured_modes = tuple(
            str(value) for value in configured
        ) if isinstance(configured, (list, tuple)) else ()
        face_mask = calibration.completed_face_mask & 0x3F
        required_faces = 6 if calibration.mode == 2 else 1 if calibration.mode == 1 else 0
        return CalibrationOverview(
            present=True,
            configured_modes=configured_modes,
            timestamp_us=calibration.timestamp_us,
            mode=calibration.mode,
            state=calibration.state,
            ready=calibration.ready,
            completed_face_mask=face_mask,
            completed_faces=face_mask.bit_count(),
            required_faces=required_faces,
            samples=calibration.samples,
            reject_count=calibration.reject_count,
            retry_count=calibration.retry_count,
            accel_bias_mps2=calibration.accel_bias_mps2,
            accel_scale=calibration.accel_scale,
            gyro_bias_radps=calibration.gyro_bias_radps,
            gyro_scale=calibration.gyro_scale,
        )
    record = _Record_ForMission(dataset.Records_Get("CALIBRATION_RESULT"), start_timestamp_us)
    if record is None:
        return CalibrationOverview(False)
    payload = record.payload
    mode = int(payload["mode"])
    face_mask = int(payload["completed_face_mask"]) & 0x3F
    required_faces = 6 if mode == 2 else 1 if mode == 1 else 0
    return CalibrationOverview(
        present=True,
        timestamp_us=record.timestamp_us,
        mode=mode,
        state=int(payload["state"]),
        ready=bool(payload["ready"]),
        completed_face_mask=face_mask,
        completed_faces=face_mask.bit_count(),
        required_faces=required_faces,
        samples=int(payload["samples"]),
        reject_count=int(payload["reject_count"]),
        retry_count=int(payload["retry_count"]),
        accel_bias_mps2=_FloatTuple(payload, "accel_bias_mps2", 3),
        accel_scale=_FloatTuple(payload, "accel_scale", 3),
        gyro_bias_radps=_FloatTuple(payload, "gyro_bias_radps", 3),
        gyro_scale=_FloatTuple(payload, "gyro_scale", 3),
    )


def _AlignmentSources_Get(
    selected_mask: int | None,
    ready_mask: int | None,
    attitude_source: int | None,
) -> tuple[str, ...]:
    if selected_mask is None or ready_mask is None:
        return ()
    used_mask = selected_mask & ready_mask
    sources: list[str] = []
    if used_mask & (1 << 0):
        if attitude_source == 1:
            sources.append("hardware_attitude")
        elif attitude_source == 2:
            sources.extend(("imu", "known_yaw"))
        elif attitude_source == 3:
            sources.extend(("imu", "magnetometer"))
        else:
            sources.append("attitude")
    if used_mask & (1 << 1):
        sources.append("gnss")
    if used_mask & (1 << 2):
        sources.append("barometer")
    if used_mask & (1 << 3):
        sources.append("magnetometer")
    if used_mask & (1 << 4):
        sources.append("dual_gnss_heading")
    if used_mask & (1 << 5):
        sources.append("external_attitude")
    return tuple(dict.fromkeys(sources))


def _Alignment_Build(
    dataset: FlightDataset,
    start_timestamp_us: int | None,
) -> AlignmentOverview:
    history = tuple(
        record
        for record in dataset.Records_Get("ALIGNMENT_RESULT")
        if start_timestamp_us is None or record.timestamp_us <= start_timestamp_us
    )
    ready_history = tuple(
        record
        for record in history
        if bool(record.payload.get("ready", 0))
        and int(record.payload.get("state", -1)) == 3
        and _FloatTuple(record.payload, "q_nb", 4) is not None
    )
    result_record = (
        max(
            ready_history,
            key=lambda item: (
                item.timestamp_us,
                item.record_sequence,
                item.file_offset,
            ),
        )
        if ready_history
        else None
    )
    initial_record = _Record_ForMission(dataset.Records_Get("INITIAL_STATE"), start_timestamp_us)
    mission_record = _Record_ForMission(dataset.Records_Get("MISSION_CONFIG"), start_timestamp_us)
    if result_record is None and initial_record is None:
        return AlignmentOverview(False)
    result = result_record.payload if result_record is not None else {}
    initial = initial_record.payload if initial_record is not None else {}
    mission = mission_record.payload if mission_record is not None else {}
    mode_value = initial.get("alignment_algorithm", mission.get("alignment_algorithm"))
    mode = int(mode_value) if mode_value is not None else None
    q_nb = _FloatTuple(initial, "q_nb", 4)
    quaternion_record = "INITIAL_STATE" if q_nb is not None else ""
    if q_nb is None:
        q_nb = _FloatTuple(result, "q_nb", 4)
        quaternion_record = "ALIGNMENT_RESULT" if q_nb is not None else ""
    state = int(result["state"]) if "state" in result else (3 if initial_record else None)
    ready = bool(result.get("ready", initial_record is not None))
    selected_mask = int(result["selected_mask"]) if "selected_mask" in result else None
    ready_mask = int(result["ready_mask"]) if "ready_mask" in result else None
    attitude_source = (
        int(result["attitude_source"]) if "attitude_source" in result else None
    )
    known_yaw = (
        float(mission["known_yaw_deg"])
        if mode in (0, 3) and "known_yaw_deg" in mission
        else None
    )
    declination = (
        float(mission["magnetic_declination_deg"])
        if mode == 1 and "magnetic_declination_deg" in mission
        else None
    )
    return AlignmentOverview(
        present=True,
        timestamp_us=(
            initial_record.timestamp_us
            if initial_record is not None
            else result_record.timestamp_us
            if result_record is not None
            else None
        ),
        mode=mode,
        state=state,
        ready=ready,
        q_nb=q_nb,
        quaternion_record=quaternion_record,
        known_yaw_deg=known_yaw,
        magnetic_declination_deg=declination,
        sample_count=(
            int(initial["alignment_sample_count"])
            if "alignment_sample_count" in initial
            else None
        ),
        selected_mask=selected_mask,
        ready_mask=ready_mask,
        config_result=(int(result["config_result"]) if "config_result" in result else None),
        attitude_source=attitude_source,
        used_sources=_AlignmentSources_Get(
            selected_mask,
            ready_mask,
            attitude_source,
        ),
        historical_mode=mode in (0, 1, 2),
        history_count=len(history),
        ready_history_count=len(ready_history),
        result_timestamp_us=(
            result_record.timestamp_us
            if result_record is not None
            else None
        ),
        initial_state_timestamp_us=(
            initial_record.timestamp_us
            if initial_record is not None
            else None
        ),
        initial_state_authoritative=initial_record is not None,
    )


def _StreamConfigured_Check(dataset: FlightDataset, suffix: str) -> bool:
    semantic_context = dataset.semantic_context
    if semantic_context is None:
        return bool(dataset.Records_Get(suffix))
    expected = f"_{suffix}".upper()
    return any(
        bool(stream.get("enabled", True))
        and str(stream.get("record", "")).upper().endswith(expected)
        for stream in semantic_context.logging_streams
    )


def _Gnss_Build(dataset: FlightDataset) -> GnssOverview:
    native = dataset.Records_Get("GNSS_NATIVE")
    measurements = dataset.Records_Get("GNSS_MEASUREMENT")
    latest = (
        max(
            native,
            key=lambda item: (
                item.timestamp_us,
                item.record_sequence,
                item.file_offset,
            ),
        )
        if native
        else None
    )
    position_usable_count = sum(
        1
        for record in native
        if bool(record.payload.get("position_usable", 0))
        and (
            int(record.payload.get("latitude_e7", 0)) != 0
            or int(record.payload.get("longitude_e7", 0)) != 0
        )
    )
    velocity_usable_count = sum(
        1
        for record in native
        if int(record.payload.get("velocity_valid_mask", 0)) != 0
    )
    return GnssOverview(
        native_configured=_StreamConfigured_Check(dataset, "GNSS_NATIVE"),
        measurement_configured=_StreamConfigured_Check(
            dataset,
            "GNSS_MEASUREMENT",
        ),
        native_sample_count=len(native),
        measurement_sample_count=len(measurements),
        latest_online=(
            bool(latest.payload.get("online", 0))
            if latest is not None
            else None
        ),
        latest_fix_type=(
            int(latest.payload.get("fix_type", 0))
            if latest is not None
            else None
        ),
        position_usable_count=position_usable_count,
        velocity_usable_count=velocity_usable_count,
    )


def _Series_InterpolateAltitude(series: TimeSeries, timestamp_us: int) -> float | None:
    values = np.asarray(series.values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] < 3 or series.count == 0:
        return None
    altitude = values[:, 2]
    valid = series.valid & np.isfinite(altitude)
    timestamps = series.timestamp_us[valid].astype(np.float64)
    altitude = altitude[valid]
    if timestamps.size == 0 or timestamp_us < timestamps[0] or timestamp_us > timestamps[-1]:
        return None
    return float(np.interp(float(timestamp_us), timestamps, altitude))


def _Deploy_Build(
    dataset: FlightDataset,
    start_timestamp_us: int | None,
) -> DeployOverview:
    event_records = tuple(
        sorted(dataset.Records_Get("EVENT"), key=lambda item: item.timestamp_us)
    )
    deploy_event = next(
        (
            record
            for record in event_records
            if int(record.payload["event_id"]) == 0x29
            and (start_timestamp_us is None or record.timestamp_us >= start_timestamp_us)
        ),
        None,
    )
    detail_event = next(
        (
            record
            for record in event_records
            if int(record.payload["event_id"]) == 0x2B
            and (
                deploy_event is None
                or abs(record.timestamp_us - deploy_event.timestamp_us) <= 1_000
            )
        ),
        None,
    )
    timestamp_us = (
        deploy_event.timestamp_us
        if deploy_event is not None
        else detail_event.timestamp_us
        if detail_event is not None
        else None
    )
    altitude = None
    altitude_source = "N/A"
    if timestamp_us is not None:
        for source_name, channel_id in (
            ("KF_6", "kf6.recorded.navigation.position_enu"),
            ("Pure INS", "pure_ins.recorded.navigation.position_enu"),
        ):
            position = dataset.Series_Get(channel_id)
            if position is None:
                continue
            altitude = _Series_InterpolateAltitude(position, timestamp_us)
            if altitude is not None:
                altitude_source = source_name
                break
    mission_record = _Record_ForMission(dataset.Records_Get("MISSION_CONFIG"), start_timestamp_us)
    enabled_mask = (
        int(mission_record.payload["deploy_trigger_mask"])
        if mission_record is not None
        else int(deploy_event.payload["arg0"])
        if deploy_event is not None
        else 0
    )
    actual_mask = int(detail_event.payload["arg0"]) if detail_event is not None else 0
    trigger_value = (
        float(detail_event.payload["arg1_float"]) if detail_event is not None else None
    )
    trigger_kind = ""
    threshold = None
    config = mission_record.payload if mission_record is not None else {}
    if actual_mask & 0x02:
        trigger_kind = "vertical_velocity"
        threshold = (
            float(config["apogee_vz_threshold_mps"])
            if "apogee_vz_threshold_mps" in config
            else None
        )
    elif actual_mask & 0x01:
        trigger_kind = "tilt_angle"
        threshold = (
            float(config["tilt_threshold_deg"]) if "tilt_threshold_deg" in config else None
        )
    elif actual_mask & 0x04:
        trigger_kind = "mission_delay"
        threshold = float(config["deploy_delay_ms"]) if "deploy_delay_ms" in config else None
    return DeployOverview(
        timestamp_us=timestamp_us,
        altitude_m=altitude,
        altitude_source=altitude_source,
        actual_reason_recorded=detail_event is not None,
        actual_trigger_mask=actual_mask,
        enabled_trigger_mask=enabled_mask,
        trigger_value=trigger_value,
        trigger_value_kind=trigger_kind,
        trigger_threshold=threshold,
    )


def FlightSummary_Build(dataset: FlightDataset) -> FlightSummary:
    source_name, position, velocity = _Navigation_Select(dataset)
    start_timestamp_us = dataset.start_timestamp_us
    fallback_timestamp = dataset.diagnostics.first_timestamp_us
    effective_start = start_timestamp_us if start_timestamp_us is not None else fallback_timestamp
    maximum_altitude: float | None = None
    if position is not None and position.count and position.values.ndim == 2:
        altitude = np.asarray(position.values[:, 2], dtype=np.float64)
        valid = _MissionMask(position, effective_start) & np.isfinite(altitude)
        if np.any(valid):
            maximum_altitude = float(np.max(altitude[valid]))
    acceleration = dataset.Series_Get("pure_ins.recorded.navigation.linear_accel_enu")
    if acceleration is None:
        acceleration = dataset.Series_Get("imu.corrected.accel_b")
    mission_events = {0x03, 0x29, 0x2A, 0x2B, 0x2C}
    events = tuple(
        TimelineEvent(
            timestamp_us=record.timestamp_us,
            name=str(record.payload["event_name"]),
            category=(
                "mission" if int(record.payload["event_id"]) in mission_events else "system"
            ),
            arg0=int(record.payload["arg0"]),
            arg1=int(record.payload["arg1"]),
        )
        for record in sorted(dataset.Records_Get("EVENT"), key=lambda item: item.timestamp_us)
    )
    duration = dataset.mission_duration_s
    if duration is not None and (not math.isfinite(duration) or duration < 0.0):
        duration = None
    if dataset.data_quality is None:
        raise ValueError("dataset_data_quality_missing")
    return FlightSummary(
        source_name=source_name,
        mission_start_timestamp_us=start_timestamp_us,
        start_fallback=start_timestamp_us is None,
        duration_s=duration,
        maximum_altitude_m=maximum_altitude,
        maximum_speed_mps=_Maximum_VectorNorm(velocity, effective_start),
        maximum_acceleration_mps2=_Maximum_VectorNorm(acceleration, effective_start),
        deploy=_Deploy_Build(dataset, start_timestamp_us),
        calibration=_Calibration_Build(dataset, start_timestamp_us),
        alignment=_Alignment_Build(dataset, start_timestamp_us),
        gnss=_Gnss_Build(dataset),
        data_quality=dataset.data_quality,
        timeline=events,
        decoded_record_count=dataset.diagnostics.decoded_record_count,
        crc_failure_count=dataset.diagnostics.record_crc_failures,
        sequence_gap_count=dataset.diagnostics.sequence_gap_count,
        synthetic=bool(dataset.metadata.get("synthetic", False)),
    )
