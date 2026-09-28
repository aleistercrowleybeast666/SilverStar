from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.math import Quaternion_RotateVector


@dataclass(frozen=True, slots=True)
class TriggerReplay:
    available: bool
    recorded_timestamp_us: int | None
    replayed_timestamp_us: int | None
    delta_ms: float | None
    reason: str
    matched_mask: int = 0
    fidelity: str = "UNAVAILABLE"
    diagnostics: Mapping[str, float | int | str] | None = None


@dataclass(frozen=True, slots=True)
class RecoveryReplayResult:
    deploy: TriggerReplay
    landing: TriggerReplay


def _RecordedEvent_Timestamp(dataset: FlightDataset, event_id: int) -> int | None:
    for record in dataset.Records_Get("EVENT"):
        if int(record.payload["event_id"]) == event_id:
            return record.timestamp_us
    return None


def _Timestamp_DeltaMs(first: int | None, second: int | None) -> float | None:
    if first is None or second is None:
        return None
    return (second - first) * 1.0e-3


def _Series_Preferred(
    dataset: FlightDataset,
    overrides: Mapping[str, TimeSeries] | None,
    override_id: str,
    recorded_ids: tuple[str, ...],
) -> TimeSeries | None:
    if overrides and override_id in overrides:
        return overrides[override_id]
    for channel_id in recorded_ids:
        series = dataset.Series_Get(channel_id)
        if series is not None:
            return series
    return None


def _BodyAxis_Vector(axis: int) -> np.ndarray:
    vectors = (
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    )
    if axis < 0 or axis >= len(vectors):
        raise ValueError("rocket_longitudinal_axis_invalid")
    return np.asarray(vectors[axis], dtype=np.float32)


def _Deploy_Replay(
    dataset: FlightDataset,
    config: Mapping[str, object],
    overrides: Mapping[str, TimeSeries] | None,
) -> TriggerReplay:
    recorded = _RecordedEvent_Timestamp(dataset, 0x29)
    start = dataset.start_timestamp_us
    velocity = _Series_Preferred(
        dataset,
        overrides,
        "navigation.velocity_enu",
        (
            "kf6.recorded.navigation.velocity_enu",
            "pure_ins.recorded.navigation.velocity_enu",
        ),
    )
    attitude = _Series_Preferred(
        dataset,
        overrides,
        "attitude.q_nb",
        ("kf6.recorded.attitude.q_nb", "pure_ins.recorded.attitude.q_nb"),
    )
    trigger_mask = int(config.get("deploy_trigger_mask", 0))
    if start is None or trigger_mask == 0:
        return TriggerReplay(False, recorded, None, None, "deploy_disabled_or_start_missing")
    if velocity is None and (trigger_mask & 0x02):
        return TriggerReplay(False, recorded, None, None, "velocity_input_missing")
    if attitude is None and (trigger_mask & 0x01):
        return TriggerReplay(False, recorded, None, None, "attitude_input_missing")

    timeline = velocity.timestamp_us if velocity is not None else attitude.timestamp_us
    body_axis = _BodyAxis_Vector(int(config.get("rocket_longitudinal_axis", 0)))
    initial_q = np.asarray(dataset.Records_Get("INITIAL_STATE")[0].payload["q_nb"])
    initial_axis = Quaternion_RotateVector(initial_q, body_axis)
    tilt_threshold_cos = math.cos(math.radians(float(config.get("tilt_threshold_deg", 0.0))))
    apogee_threshold = float(config.get("apogee_vz_threshold_mps", 0.0))
    delay_ms = int(config.get("deploy_delay_ms", 0))
    confirm_us = int(config.get("deploy_confirm_ms", 0)) * 1000
    confirming_since: int | None = None
    confirming_mask = 0
    matched_value = 0.0

    for timestamp_value in timeline:
        timestamp = int(timestamp_value)
        if timestamp < start:
            continue
        mission_ms = (timestamp - start) // 1000
        matched = 0
        if trigger_mask & 0x04 and mission_ms >= delay_ms:
            matched |= 0x04
            matched_value = float(mission_ms)
        if trigger_mask & 0x02 and velocity is not None:
            index = min(
                int(np.searchsorted(velocity.timestamp_us, timestamp, side="right")) - 1,
                velocity.count - 1,
            )
            if index >= 0 and velocity.valid[index]:
                vertical_velocity = float(velocity.values[index, 2])
                if vertical_velocity < apogee_threshold:
                    matched |= 0x02
                    matched_value = vertical_velocity
        if trigger_mask & 0x01 and attitude is not None:
            index = min(
                int(np.searchsorted(attitude.timestamp_us, timestamp, side="right")) - 1,
                attitude.count - 1,
            )
            if index >= 0 and attitude.valid[index]:
                current_axis = Quaternion_RotateVector(attitude.values[index], body_axis)
                reference_dot = (
                    float(np.dot(initial_axis, current_axis))
                    if int(config.get("tilt_reference", 0)) == 0
                    else float(current_axis[2])
                )
                if reference_dot < tilt_threshold_cos:
                    matched |= 0x01
                    matched_value = math.degrees(math.acos(max(-1.0, min(1.0, reference_dot))))
        if not matched:
            confirming_since = None
            confirming_mask = 0
            continue
        if matched & 0x04 or confirm_us == 0:
            replayed = timestamp
            return TriggerReplay(
                True,
                recorded,
                replayed,
                _Timestamp_DeltaMs(recorded, replayed),
                "condition_confirmed",
                matched,
                "EXACT",
                {"trigger_value": matched_value},
            )
        if confirming_since is None or not (confirming_mask & matched):
            confirming_since = timestamp
            confirming_mask = matched
            continue
        if timestamp - confirming_since >= confirm_us:
            matched &= confirming_mask
            replayed = timestamp
            return TriggerReplay(
                True,
                recorded,
                replayed,
                _Timestamp_DeltaMs(recorded, replayed),
                "condition_confirmed",
                matched,
                "EXACT",
                {"trigger_value": matched_value},
            )
    return TriggerReplay(True, recorded, None, None, "no_deploy_condition_reached", 0, "EXACT")


def _Regression_Get(timestamps: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    time = (timestamps.astype(np.float64) - float(timestamps[0])) * 1.0e-6
    if len(time) < 2 or time[-1] <= 0.0:
        return float("nan"), float("nan")
    centered = time - np.mean(time)
    denominator = float(np.sum(centered**2))
    slope = float(np.sum(centered * (values - np.mean(values))) / denominator)
    span = float(np.max(values) - np.min(values))
    return slope, span


def _Landing_BaroImu(dataset, config, recovery_start):
    from silverstar_flp.analysis.landing_window import LandingWindow_Replay
    return LandingWindow_Replay(dataset, config, recovery_start)


def _Landing_Stillness(
    dataset: FlightDataset,
    config: Mapping[str, object],
    recovery_start: int,
    *,
    impact_required: bool,
) -> tuple[int | None, str, dict[str, float | int]]:
    imu = [
        record
        for record in dataset.Records_Get("IMU_CORRECTED")
        if int(record.payload["sample_timestamp_us"]) >= recovery_start
        and bool(record.payload.get("correction_valid", 0))
    ]
    linear = dataset.Series_Get("kf6.recorded.navigation.linear_accel_enu")
    if linear is None:
        linear = dataset.Series_Get("pure_ins.recorded.navigation.linear_accel_enu")
    if not imu or linear is None:
        return None, "corrected_imu_or_linear_acceleration_missing", {}
    confirm_us = int(config.get("landing_confirm_ms", 0)) * 1000
    inhibit_us = int(config.get("impact_inhibit_ms", 0)) * 1000
    impact_threshold = float(config.get("impact_threshold_mps2", 0.0))
    gyro_threshold = float(config.get("still_gyro_threshold_radps", 0.0))
    accel_tolerance = float(config.get("still_accel_tolerance_mps2", 0.0))
    impact_seen = not impact_required
    confirming_since: int | None = None
    peak = 0.0
    for record in imu:
        timestamp = int(record.payload["sample_timestamp_us"])
        accel_norm = float(np.linalg.norm(record.payload["accel_b_mps2"]))
        peak = max(peak, accel_norm)
        if impact_required and not impact_seen:
            if timestamp - recovery_start >= inhibit_us and accel_norm > impact_threshold:
                impact_seen = True
            continue
        gyro_norm = float(np.linalg.norm(record.payload["gyro_b_radps"]))
        index = int(np.searchsorted(linear.timestamp_us, timestamp, side="right")) - 1
        if index < 0 or not linear.valid[index]:
            confirming_since = None
            continue
        linear_norm = float(np.linalg.norm(linear.values[index]))
        if gyro_norm < gyro_threshold and linear_norm < accel_tolerance:
            if confirming_since is None:
                confirming_since = timestamp
            elif timestamp - confirming_since >= confirm_us:
                return timestamp, "stillness_confirmed", {"impact_peak_mps2": peak}
        else:
            confirming_since = None
    return None, "no_stillness_confirmation", {"impact_peak_mps2": peak}


def _Landing_Replay(
    dataset: FlightDataset,
    config: Mapping[str, object],
    deploy: TriggerReplay,
) -> TriggerReplay:
    recorded = _RecordedEvent_Timestamp(dataset, 0x2A)
    if not bool(config.get("landing_enable", 0)):
        return TriggerReplay(False, recorded, None, None, "landing_detection_disabled")
    recovery_start = deploy.replayed_timestamp_us or deploy.recorded_timestamp_us
    if recovery_start is None:
        return TriggerReplay(False, recorded, None, None, "recovery_start_unavailable")
    mode = int(config.get("landing_mode", 0))
    if mode == 2:
        required = (
            "baro_max_span_m",
            "candidate_baro_min_samples",
            "candidate_imu_min_samples",
            "candidate_min_coverage_percent",
        )
        if any(key not in config for key in required):
            return TriggerReplay(False, recorded, None, None, "mission_config_v2_required")
        replayed, reason, diagnostics = _Landing_BaroImu(dataset, config, recovery_start)
    elif mode == 1:
        replayed, reason, diagnostics = _Landing_Stillness(
            dataset, config, recovery_start, impact_required=True
        )
    else:
        replayed, reason, diagnostics = _Landing_Stillness(
            dataset, config, recovery_start, impact_required=False
        )
    return TriggerReplay(
        True,
        recorded,
        replayed,
        _Timestamp_DeltaMs(recorded, replayed),
        reason,
        0,
        "APPROXIMATE" if mode == 2 else "EXACT",
        diagnostics,
    )


def RecoveryReplay_Run(
    dataset: FlightDataset,
    navigation_channels: Mapping[str, TimeSeries] | None = None,
) -> RecoveryReplayResult:
    mission_configs = dataset.Records_Get("MISSION_CONFIG")
    initial_states = dataset.Records_Get("INITIAL_STATE")
    if not mission_configs or not initial_states:
        unavailable = TriggerReplay(
            False, None, None, None, "mission_config_or_initial_state_missing"
        )
        return RecoveryReplayResult(unavailable, unavailable)
    config = mission_configs[0].payload
    deploy = _Deploy_Replay(dataset, config, navigation_channels)
    landing = _Landing_Replay(dataset, config, deploy)
    return RecoveryReplayResult(deploy, landing)
