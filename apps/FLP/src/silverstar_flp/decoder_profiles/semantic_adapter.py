from __future__ import annotations

import math
import struct
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any

import numpy as np

from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.semantic_context import (
    CalibrationSnapshot,
    DatasetSemanticContext,
    DecoderPackageIdentity,
)
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage

_EVENT_NAMES = {
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

# These are semantic field-role bindings only. Binary offsets and sizes remain
# exclusively owned by the package record catalog.
_STABLE_ALIAS_SPECS = (
    ("sf6.recorded.navigation.position_enu", "SF6_STATE", "position_enu_m", None),
    ("sf6.recorded.navigation.velocity_enu", "SF6_STATE", "velocity_enu_mps", None),
    ("sf6.recorded.attitude.q_nb", "SF6_STATE", "q_nb", None),
    ("sf6.recorded.navigation_health", "SF6_STATE", "health", None),
    ("eskf15.recorded.navigation.position_enu", "ESKF15_STATE", "position_enu_m", None),
    ("eskf15.recorded.navigation.velocity_enu", "ESKF15_STATE", "velocity_enu_mps", None),
    ("eskf15.recorded.attitude.q_nb", "ESKF15_STATE", "q_nb", None),
    ("eskf15.recorded.gyro_bias", "ESKF15_STATE", "gyro_bias_radps", None),
    ("eskf15.recorded.accel_bias", "ESKF15_STATE", "accel_bias_mps2", None),
    ("eskf15.recorded.covariance.diagonal", "ESKF15_STATE", "p_diagonal", None),
    ("eskf15.recorded.navigation_health", "ESKF15_STATE", "health", None),
    ("kf6.recorded.attitude.q_nb", "ESTIMATOR", "q_nb", None),
    ("kf6.recorded.navigation.linear_accel_enu", "ESTIMATOR", "acceleration_enu_mps2", None),
    ("pure_ins.recorded.attitude.q_nb", "PURE_INS", "q_nb", None),
    (
        "pure_ins.recorded.navigation.velocity_enu",
        "PURE_INS",
        "velocity_enu_mps",
        None,
    ),
    (
        "pure_ins.recorded.navigation.position_enu",
        "PURE_INS",
        "position_enu_m",
        None,
    ),
    (
        "pure_ins.recorded.navigation.linear_accel_enu",
        "PURE_INS",
        "accel_enu_mps2",
        None,
    ),
    (
        "kf6.recorded.navigation.position_enu",
        "ESTIMATOR",
        "position_enu_m",
        None,
    ),
    (
        "kf6.recorded.navigation.velocity_enu",
        "ESTIMATOR",
        "velocity_enu_mps",
        None,
    ),
    (
        "kf6.recorded.covariance.diagonal",
        "ESTIMATOR",
        "covariance_diagonal",
        None,
    ),
    ("kf6.recorded.nis.position", "ESTIMATOR", "last_position_nis", None),
    ("kf6.recorded.nis.velocity", "ESTIMATOR", "last_velocity_nis", None),
    ("kf6.recorded.nis.baro", "ESTIMATOR", "last_baro_nis", None),
    (
        "kf6.recorded.measurement_result_flags",
        "ESTIMATOR",
        "measurement_result_flags",
        None,
    ),
    (
        "kf6.recorded.measurement_age.gnss",
        "ESTIMATOR",
        "gnss_measurement_age_us",
        None,
    ),
    (
        "kf6.recorded.measurement_age.baro",
        "ESTIMATOR",
        "baro_measurement_age_us",
        None,
    ),
    (
        "kf6.recorded.measurement_sequence.gnss",
        "ESTIMATOR",
        "gnss_sequence",
        None,
    ),
    (
        "kf6.recorded.measurement_sequence.baro",
        "ESTIMATOR",
        "baro_sequence",
        None,
    ),
    (
        "kf6.recorded.innovation.position",
        "KF6_DIAGNOSTIC",
        "position_innovation",
        None,
    ),
    (
        "kf6.recorded.innovation.velocity",
        "KF6_DIAGNOSTIC",
        "velocity_innovation",
        None,
    ),
    (
        "kf6.recorded.innovation.baro",
        "KF6_DIAGNOSTIC",
        "baro_innovation",
        None,
    ),
    (
        "kf6.recorded.measurement_r.position",
        "KF6_DIAGNOSTIC",
        "position_variance_r",
        None,
    ),
    (
        "kf6.recorded.measurement_r.velocity",
        "KF6_DIAGNOSTIC",
        "velocity_variance_r",
        None,
    ),
    (
        "kf6.recorded.measurement_r.baro",
        "KF6_DIAGNOSTIC",
        "baro_variance_r",
        None,
    ),
    (
        "kf6.recorded.velocity_valid_mask",
        "KF6_DIAGNOSTIC",
        "gnss_velocity_valid_mask",
        None,
    ),
    (
        "kf6.recorded.velocity_update_dimension",
        "KF6_DIAGNOSTIC",
        "velocity_update_dimension",
        None,
    ),
    (
        "kf6.recorded.covariance.upper_triangle",
        "KF6_FULL_P",
        "covariance_upper_triangle",
        None,
    ),
    ("initial_state.attitude.q_nb", "INITIAL_STATE", "q_nb", None),
    (
        "initial_state.navigation.velocity_enu",
        "INITIAL_STATE",
        "initial_velocity_enu_mps",
        None,
    ),
    (
        "initial_state.kf6.p0_diagonal",
        "INITIAL_STATE",
        "p0_diagonal",
        None,
    ),
    ("gnss.native.velocity_enu", "GNSS_NATIVE", "velocity_enu_mps", 2),
    (
        "gnss.native.velocity_variance",
        "GNSS_NATIVE",
        "velocity_variance_m2ps2",
        2,
    ),
    ("baro.native.pressure", "BARO_NATIVE", "pressure_pa", 3),
    ("baro.native.altitude", "BARO_NATIVE", "altitude_m", 3),
    ("mag.native.field_b", "MAG_NATIVE", "magnetic_field_b_uT", 13),
    (
        "inertial.increment.delta_theta_b",
        "INERTIAL_INCREMENT",
        "delta_theta_b_corrected",
        None,
    ),
    (
        "inertial.increment.delta_velocity_b",
        "INERTIAL_INCREMENT",
        "delta_velocity_b_sculling_corrected",
        None,
    ),
    ("inertial.increment.dt", "INERTIAL_INCREMENT", "dt_s", None),
    (
        "gnss.measurement.position_enu",
        "GNSS_MEASUREMENT",
        "position_enu_m",
        None,
    ),
    (
        "gnss.measurement.velocity_enu",
        "GNSS_MEASUREMENT",
        "velocity_enu_mps",
        None,
    ),
    (
        "gnss.measurement.position_variance",
        "GNSS_MEASUREMENT",
        "position_variance_m2",
        None,
    ),
    (
        "gnss.measurement.velocity_variance",
        "GNSS_MEASUREMENT",
        "velocity_variance_m2ps2",
        None,
    ),
    (
        "baro.measurement.relative_altitude",
        "BARO_MEASUREMENT",
        "relative_altitude_m",
        None,
    ),
    ("imu.corrected.accel_b", "IMU_CORRECTED", "accel_b_mps2", None),
    ("imu.corrected.gyro_b", "IMU_CORRECTED", "gyro_b_radps", None),
    ("imu.corrected.temperature", "IMU_CORRECTED", "temperature_c", None),
    ("alignment.result.q_nb", "ALIGNMENT_RESULT", "q_nb", None),
)

_CANONICAL_FIELD_SPECS = {
    "gnss.velocity": ("GNSS_NATIVE", "velocity_enu_mps"),
    "barometer.altitude": ("BARO_NATIVE", "altitude_m"),
}


def LoggingProtocol_Validate(package: DecoderProfilePackage) -> Mapping[str, Any]:
    raw = package.semantics.raw_metadata
    protocols = raw.get("protocols", package.manifest.get("protocols"))
    if not isinstance(protocols, Mapping):
        raise DecoderProfileError("decoder_logging_protocol_missing")
    logging_protocol = protocols.get("logging")
    if not isinstance(logging_protocol, Mapping):
        raise DecoderProfileError("decoder_logging_protocol_missing")
    profile = logging_protocol.get("profile")
    selected = package.manifest.get("selected_log_format_profile")
    if (
        profile != "flight_log.0_0"
        or selected != "flight_log.0_0"
        or profile != selected
    ):
        raise DecoderProfileError(
            "decoder_logging_protocol_incompatible",
            f"logging={profile}:selected={selected}",
        )
    for optional_name in ("telemetry", "maintenance"):
        optional = protocols.get(optional_name)
        if optional is not None and not isinstance(optional, Mapping):
            raise DecoderProfileError(
                "decoder_optional_protocol_invalid",
                optional_name,
            )
    return protocols


def _MappingSequence_Get(value: Any, *, name_field: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        result: list[Mapping[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                result.append(dict(item))
            elif isinstance(item, str):
                result.append({name_field: item})
            else:
                raise DecoderProfileError(
                    "decoder_semantic_collection_invalid",
                    name_field,
                )
        return tuple(result)
    if isinstance(value, Mapping):
        result: list[Mapping[str, Any]] = []
        for key, item in value.items():
            if not isinstance(item, Mapping):
                raise DecoderProfileError(
                    "decoder_semantic_collection_invalid",
                    name_field,
                )
            normalized = dict(item)
            normalized.setdefault(name_field, str(key))
            result.append(normalized)
        return tuple(result)
    raise DecoderProfileError("decoder_semantic_collection_invalid", name_field)


def _PayloadFloat_Get(value: Any) -> float:
    raw = int(value) & 0xFFFFFFFF
    return float(struct.unpack("<f", struct.pack("<I", raw))[0])


def _PackageEventSemantics_Get(
    package: DecoderProfilePackage,
) -> tuple[Mapping[int, str], Mapping[int, Mapping[str, Any]]]:
    names = dict(_EVENT_NAMES)
    semantics: dict[int, Mapping[str, Any]] = {}
    raw_catalog = package.semantics.raw_metadata.get("event_catalog")
    if not isinstance(raw_catalog, Mapping):
        return MappingProxyType(names), MappingProxyType(semantics)
    for catalog_key, raw_entry in raw_catalog.items():
        if not isinstance(raw_entry, Mapping):
            raise DecoderProfileError("decoder_event_catalog_invalid")
        raw_event_id = raw_entry.get("event_id")
        event_id: int | None = None
        symbol = ""
        if isinstance(raw_event_id, int) and not isinstance(raw_event_id, bool):
            event_id = raw_event_id
        elif isinstance(raw_event_id, str):
            symbol = raw_event_id.removeprefix("FLIGHT_LOG_EVENT_")
            try:
                event_id = int(raw_event_id, 0)
            except ValueError:
                event_id = next(
                    (
                        candidate_id
                        for candidate_id, candidate_name in names.items()
                        if candidate_name == symbol
                    ),
                    None,
                )
        if event_id is None or not 0 <= event_id <= 0xFFFF:
            continue
        raw_name = raw_entry.get("name")
        event_name = (
            raw_name
            if isinstance(raw_name, str) and raw_name
            else symbol or str(catalog_key).upper()
        )
        names[event_id] = event_name
        semantics[event_id] = MappingProxyType(dict(raw_entry))
    return MappingProxyType(names), MappingProxyType(semantics)


def _Events_Adapt(
    records: Mapping[str, tuple[DecodedRecord, ...]],
    package: DecoderProfilePackage,
) -> Mapping[str, tuple[DecodedRecord, ...]]:
    events = records.get("EVENT", ())
    if not events:
        return records
    event_names, event_semantics = _PackageEventSemantics_Get(package)
    adapted: list[DecodedRecord] = []
    for record in events:
        event_id = int(record.payload.get("event_id", 0))
        arg0 = int(record.payload.get("arg0", 0))
        arg1 = int(record.payload.get("arg1", 0))
        adapted.append(
            replace(
                record,
                payload={
                    **dict(record.payload),
                    "event_name": event_names.get(
                        event_id,
                        f"UNKNOWN_EVENT_0x{event_id:02X}",
                    ),
                    "event_semantics": event_semantics.get(
                        event_id,
                        MappingProxyType({}),
                    ),
                    "arg0_float": _PayloadFloat_Get(arg0),
                    "arg1_float": _PayloadFloat_Get(arg1),
                },
            )
        )
    result = dict(records)
    result["EVENT"] = tuple(adapted)
    return result


def _SeriesLookup_Get(
    series: Mapping[str, TimeSeries],
) -> Mapping[tuple[str, str], tuple[tuple[str, TimeSeries], ...]]:
    lookup: dict[tuple[str, str], list[tuple[str, TimeSeries]]] = {}
    for channel_id, item in series.items():
        record_name = str(item.metadata.get("record_name", item.source)).upper()
        field_name = item.metadata.get("field_name")
        if not isinstance(field_name, str):
            continue
        lookup.setdefault((record_name, field_name), []).append((channel_id, item))
    return {
        key: tuple(sorted(items, key=lambda pair: pair[0]))
        for key, items in lookup.items()
    }


def _Series_Select(
    lookup: Mapping[tuple[str, str], tuple[tuple[str, TimeSeries], ...]],
    record_name: str,
    field_name: str,
    descriptor_id: int | None,
) -> tuple[str, TimeSeries] | None:
    candidates = lookup.get((record_name, field_name), ())
    if descriptor_id is not None:
        descriptor_candidates = []
        for pair in candidates:
            raw_descriptor_id = pair[1].metadata.get(
                "descriptor_id",
                pair[1].metadata.get("source_descriptor_id"),
            )
            try:
                matches = int(raw_descriptor_id) == descriptor_id
            except (TypeError, ValueError):
                matches = False
            if matches:
                descriptor_candidates.append(pair)
        candidates = tuple(descriptor_candidates)
    if not candidates:
        return None
    if len(candidates) > 1:
        raw_candidates = tuple(
            pair
            for pair in candidates
            if not bool(pair[1].metadata.get("canonical", False))
        )
        if raw_candidates:
            candidates = raw_candidates
    if len(candidates) > 1:
        raise DecoderProfileError(
            "decoder_stable_role_ambiguous",
            f"{record_name}:{field_name}",
        )
    return candidates[0]


def _DerivedSeries_Get(
    records: tuple[DecodedRecord, ...],
    fields: tuple[str, ...],
    *,
    unit: str,
    quantity: str,
    columns: tuple[str, ...],
) -> TimeSeries | None:
    selected = [
        record
        for record in records
        if all(field in record.payload for field in fields)
    ]
    if not selected:
        return None
    selected.sort(key=lambda item: (item.timestamp_us, item.record_sequence))
    return TimeSeries(
        timestamp_us=np.asarray(
            [record.timestamp_us for record in selected],
            dtype=np.uint64,
        ),
        values=np.asarray(
            [
                [float(record.payload[field]) for field in fields]
                for record in selected
            ],
            dtype=np.float64,
        ),
        unit=unit,
        quantity=quantity,
        source="KF6_DIAGNOSTIC",
        valid=np.ones(len(selected), dtype=np.bool_),
        columns=columns,
        metadata={
            "record_name": "KF6_DIAGNOSTIC",
            "field_name": fields,
            "semantic_adapter_derived": True,
        },
    )


def _StableSeries_Adapt(
    dataset: FlightDataset,
    package: DecoderProfilePackage,
) -> tuple[Mapping[str, TimeSeries], Mapping[str, str]]:
    series = dict(dataset.series)
    lookup = _SeriesLookup_Get(dataset.series)
    aliases: dict[str, str] = {}
    for stable_id, record_name, field_name, descriptor_id in _STABLE_ALIAS_SPECS:
        selected = _Series_Select(
            lookup,
            record_name,
            field_name,
            descriptor_id,
        )
        if selected is None:
            continue
        raw_id, raw_series = selected
        series[stable_id] = raw_series
        aliases[stable_id] = raw_id

    diagnostic_records = dataset.Records_Get("KF6_DIAGNOSTIC")
    derived_specs = (
        (
            "kf6.recorded.measurement_r_scale",
            ("position_r_scale", "velocity_r_scale", "baro_r_scale"),
            "1",
            "scale",
        ),
        (
            "kf6.recorded.update_result",
            (
                "position_update_result",
                "velocity_update_result",
                "baro_update_result",
            ),
            "enum",
            "update_result",
        ),
    )
    columns = ("GNSS position", "GNSS velocity", "Barometer")
    for stable_id, fields, unit, quantity in derived_specs:
        derived = _DerivedSeries_Get(
            diagnostic_records,
            fields,
            unit=unit,
            quantity=quantity,
            columns=columns,
        )
        if derived is not None:
            series[stable_id] = derived
            aliases[stable_id] = stable_id

    # GNSS_MEASUREMENT owns four independent recorded update groups. Keep the
    # aggregate ESTIMATOR channels for Data Explorer compatibility only.
    measurements = tuple(
        sorted(
            (
                record for record in dataset.Records_Get("GNSS_MEASUREMENT")
                if "group_nis" in record.payload and "group_update_result" in record.payload
            ),
            key=lambda record: (record.timestamp_us, record.record_sequence),
        )
    )
    for group_index, group_name in enumerate(
        ("position_en", "position_u", "velocity_en", "velocity_u")
    ):
        selected = tuple(
            record for record in measurements
            if len(record.payload["group_nis"]) > group_index
            and len(record.payload["group_update_result"]) > group_index
        )
        if not selected:
            continue
        timestamps = np.asarray(
            [int(record.payload.get("estimator_present_timestamp_us", record.timestamp_us))
             for record in selected], dtype=np.uint64
        )
        group_valid = np.asarray(
            [bool(int(record.payload.get("valid_group_mask", 0)) & (1 << group_index))
             for record in selected], dtype=np.bool_
        )
        results = np.asarray(
            [int(record.payload["group_update_result"][group_index]) for record in selected],
            dtype=np.float64,
        )
        nis = np.asarray(
            [float(record.payload["group_nis"][group_index]) for record in selected],
            dtype=np.float64,
        )
        for suffix, values, valid, unit, quantity in (
            ("nis", nis, group_valid & np.isin(results, (0, 1, 2)), "1", "nis"),
            ("update_result", results, group_valid, "enum", "update_result"),
        ):
            channel = f"kf6.recorded.{suffix}.{group_name}"
            series[channel] = TimeSeries(
                timestamp_us=timestamps, values=values, unit=unit,
                quantity=quantity, source="GNSS_MEASUREMENT",
                valid=valid & np.isfinite(values),
                metadata={"record_name": "GNSS_MEASUREMENT",
                          "field_name": f"group_{suffix}", "group_index": group_index},
            )
            aliases[channel] = channel
        field = "position_innovation_m" if group_index < 2 else "velocity_innovation_mps"
        axes = (0, 1) if group_index % 2 == 0 else (2,)
        values = np.asarray(
            [[float(record.payload[field][axis]) for axis in axes] for record in selected],
            dtype=np.float64,
        )
        channel = f"kf6.recorded.innovation.{group_name}"
        series[channel] = TimeSeries(
            timestamp_us=timestamps, values=values, unit="m" if group_index < 2 else "m/s",
            quantity="innovation", source="GNSS_MEASUREMENT",
            valid=group_valid & np.all(np.isfinite(values), axis=1),
            columns=("E", "N") if len(axes) == 2 else ("U",),
            metadata={"record_name": "GNSS_MEASUREMENT",
                      "field_name": field, "group_index": group_index},
        )
        aliases[channel] = channel

    for canonical in package.semantics.canonical_channels:
        channel_id = canonical.get("channel_id")
        capability = canonical.get("capability")
        endpoint_ids = canonical.get("endpoint_descriptor_ids")
        if (
            not isinstance(channel_id, str)
            or not isinstance(capability, str)
            or not isinstance(endpoint_ids, list)
        ):
            raise DecoderProfileError("canonical_route_invalid")
        if len(endpoint_ids) != 1 or not isinstance(endpoint_ids[0], int):
            raise DecoderProfileError(
                "canonical_route_ambiguous",
                channel_id,
            )
        descriptor_id = endpoint_ids[0]
        field_spec = _CANONICAL_FIELD_SPECS.get(capability)
        if field_spec is not None:
            selected = _Series_Select(
                lookup,
                field_spec[0],
                field_spec[1],
                descriptor_id,
            )
            if selected is not None:
                raw_id, raw_series = selected
                series[channel_id] = raw_series
                aliases[channel_id] = raw_id
            continue
        if capability == "gnss.position":
            records = tuple(
                record
                for record in dataset.Records_Get("GNSS_NATIVE")
                if int(record.payload.get("source_descriptor_id", -1))
                == descriptor_id
                and all(
                    field in record.payload
                    for field in (
                        "latitude_e7",
                        "longitude_e7",
                        "ellipsoid_height_mm",
                    )
                )
            )
            if records:
                ordered = sorted(
                    records,
                    key=lambda item: (item.timestamp_us, item.record_sequence),
                )
                series[channel_id] = TimeSeries(
                    timestamp_us=np.asarray(
                        [
                            int(
                                record.payload.get(
                                    "sample_timestamp_us",
                                    record.timestamp_us,
                                )
                            )
                            for record in ordered
                        ],
                        dtype=np.uint64,
                    ),
                    values=np.asarray(
                        [
                            (
                                record.payload["latitude_e7"],
                                record.payload["longitude_e7"],
                                record.payload["ellipsoid_height_mm"],
                            )
                            for record in ordered
                        ],
                        dtype=np.float64,
                    ),
                    unit="e7,e7,mm",
                    quantity="geodetic_position",
                    source="GNSS_NATIVE",
                    valid=np.asarray(
                        [
                            bool(record.payload.get("position_usable", True))
                            and (
                                int(record.payload["latitude_e7"]) != 0
                                or int(record.payload["longitude_e7"]) != 0
                            )
                            for record in ordered
                        ],
                        dtype=np.bool_,
                    ),
                    columns=("latitude_e7", "longitude_e7", "height_mm"),
                    metadata={
                        "record_name": "GNSS_NATIVE",
                        "field_name": (
                            "latitude_e7",
                            "longitude_e7",
                            "ellipsoid_height_mm",
                        ),
                        "descriptor_id": descriptor_id,
                        "canonical": True,
                        "semantic_adapter_derived": True,
                    },
                )
                aliases[channel_id] = channel_id
    return series, aliases


def _Vector3_Get(payload: Mapping[str, Any], field_name: str) -> tuple[float, float, float]:
    raw = payload.get(field_name)
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise DecoderProfileError(
            "calibration_result_vector_invalid",
            field_name,
        )
    values = tuple(float(value) for value in raw)
    if not all(math.isfinite(value) for value in values):
        raise DecoderProfileError(
            "calibration_result_vector_invalid",
            field_name,
        )
    return values


def _CalibrationBoundary_Get(dataset: FlightDataset) -> tuple[int, str]:
    mission_starts = [
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload.get("event_id", 0)) == 0x03
    ]
    if mission_starts:
        return min(mission_starts), "mission_start"
    initial_states = dataset.Records_Get("INITIAL_STATE")
    if initial_states:
        return min(record.timestamp_us for record in initial_states), "initial_state"
    eskf_initial = dataset.Records_Get("ESKF15_INITIAL_STATE")
    if eskf_initial:
        return min(record.timestamp_us for record in eskf_initial), "eskf15_initial_state"
    corrected = dataset.Records_Get("IMU_CORRECTED")
    if corrected:
        return min(
            int(record.payload.get("sample_timestamp_us", record.timestamp_us))
            for record in corrected
        ), "first_corrected_imu"
    raise DecoderProfileError("calibration_selection_boundary_missing")


def _CalibrationSnapshot_Get(
    dataset: FlightDataset,
    package: DecoderProfilePackage,
) -> CalibrationSnapshot:
    boundary, boundary_kind = _CalibrationBoundary_Get(dataset)
    eligible = [
        record
        for record in dataset.Records_Get("CALIBRATION_RESULT")
        if record.timestamp_us <= boundary
    ]
    if not eligible:
        raise DecoderProfileError("calibration_result_before_boundary_missing")
    latest_error: DecoderProfileError | None = None
    for record in sorted(
        eligible,
        key=lambda item: (
            item.timestamp_us,
            item.record_sequence,
            item.file_offset,
        ),
        reverse=True,
    ):
        try:
            return _CalibrationSnapshot_FromRecord(
                dataset,
                package,
                record,
                boundary,
                boundary_kind,
            )
        except DecoderProfileError as exc:
            if latest_error is None:
                latest_error = exc
    if latest_error is not None:
        raise latest_error
    raise DecoderProfileError("calibration_result_before_boundary_missing")


def _CalibrationSnapshot_FromRecord(
    dataset: FlightDataset,
    package: DecoderProfilePackage,
    record: DecodedRecord,
    boundary: int,
    boundary_kind: str,
) -> CalibrationSnapshot:
    payload = record.payload
    required_scalar_fields = (
        "source_id",
        "virtual_imu_id",
        "mode",
        "state",
        "ready",
        "completed_face_mask",
        "samples",
        "reject_count",
        "retry_count",
        "start_sequence",
    )
    if any(field not in payload for field in required_scalar_fields):
        raise DecoderProfileError("calibration_result_field_missing")
    mode = int(payload["mode"])
    raw_modes = package.semantics.raw_metadata.get("modes", {})
    calibration_modes = (
        raw_modes.get("calibration", [])
        if isinstance(raw_modes, Mapping)
        else []
    )
    if not isinstance(calibration_modes, list) or not all(
        isinstance(item, str) for item in calibration_modes
    ):
        raise DecoderProfileError("calibration_modes_invalid")
    allowed_modes = {0}
    for name in calibration_modes:
        normalized = name.replace("_", "").casefold()
        if normalized == "oneface":
            allowed_modes.add(1)
        elif normalized == "sixface":
            allowed_modes.add(2)
        else:
            raise DecoderProfileError("calibration_mode_unsupported", name)
    if mode not in allowed_modes:
        raise DecoderProfileError("calibration_mode_not_declared", str(mode))

    state = int(payload["state"])
    ready = bool(int(payload["ready"]))
    if not ready or state != 4:
        raise DecoderProfileError("calibration_result_not_ready")
    face_mask = int(payload["completed_face_mask"]) & 0xFF
    samples = int(payload["samples"])
    reject_count = int(payload["reject_count"])
    retry_count = int(payload["retry_count"])
    start_sequence = int(payload["start_sequence"])
    counters = (samples, reject_count, retry_count)
    if any(value < 0 for value in counters):
        raise DecoderProfileError("calibration_result_counter_invalid")
    if start_sequence < 0:
        raise DecoderProfileError("calibration_result_counter_invalid")
    accel_bias = _Vector3_Get(payload, "accel_bias_mps2")
    accel_scale = _Vector3_Get(payload, "accel_scale")
    gyro_bias = _Vector3_Get(payload, "gyro_bias_radps")
    gyro_scale = _Vector3_Get(payload, "gyro_scale")
    if any(value <= 0.0 for value in (*accel_scale, *gyro_scale)):
        raise DecoderProfileError("calibration_result_scale_invalid")
    if mode == 0:
        if (
            face_mask != 0
            or any(counters)
            or any(abs(value) > 1.0e-7 for value in (*accel_bias, *gyro_bias))
            or any(abs(value - 1.0) > 1.0e-7 for value in (*accel_scale, *gyro_scale))
        ):
            raise DecoderProfileError("calibration_none_identity_invalid")
    elif mode == 1:
        if face_mask == 0 or samples <= 0:
            raise DecoderProfileError("calibration_one_face_incomplete")
    elif mode == 2 and ((face_mask & 0x3F) != 0x3F or samples <= 0):
        raise DecoderProfileError("calibration_six_face_incomplete")

    corrected = tuple(
        item
        for item in dataset.Records_Get("IMU_CORRECTED")
        if item.timestamp_us >= record.timestamp_us
    )
    correction_valid = all(
        bool(int(item.payload.get("correction_valid", 0)))
        and int(item.payload.get("calibration_mode", mode)) == mode
        for item in corrected
    )
    if corrected and not correction_valid:
        raise DecoderProfileError("calibration_corrected_imu_inconsistent")
    return CalibrationSnapshot(
        timestamp_us=record.timestamp_us,
        selection_boundary_us=boundary,
        selection_boundary_kind=boundary_kind,
        source_id=int(payload["source_id"]),
        virtual_imu_id=int(payload["virtual_imu_id"]),
        mode=mode,
        state=state,
        ready=ready,
        completed_face_mask=face_mask,
        samples=samples,
        reject_count=reject_count,
        retry_count=retry_count,
        start_sequence=start_sequence,
        accel_bias_mps2=accel_bias,
        accel_scale=accel_scale,
        gyro_bias_radps=gyro_bias,
        gyro_scale=gyro_scale,
        corrected_sample_count=len(corrected),
        correction_valid=correction_valid,
    )


def _Context_Build(
    package: DecoderProfilePackage,
    aliases: Mapping[str, str],
    calibration: CalibrationSnapshot,
) -> DatasetSemanticContext:
    raw = package.semantics.raw_metadata
    manifest = package.manifest
    package_schema = manifest["package_schema"]
    protocols = LoggingProtocol_Validate(package)
    return DatasetSemanticContext(
        package_identity=DecoderPackageIdentity(
            package_sha256=package.package_sha256,
            generation_profile_sha256=package.generation_profile_sha256,
            generation_profile_hash_128=package.generation_profile_hash_128,
            record_catalog_sha256=package.catalog.sha256,
            project_semantics_sha256=package.semantics.sha256,
            package_schema_id=str(package_schema["id"]),
            package_schema_major=package.package_schema_major,
            package_schema_minor=package.package_schema_minor,
            declared_container_id=package.declared_container_plugin_id,
            container_version_range=package.required_container_version_range,
            project_name=package.semantics.project_name,
            firmware_version=package.semantics.firmware_version,
            firmware_commit=str(manifest.get("firmware_commit", "")),
        ),
        firmware_algorithm_ids=package.semantics.firmware_algorithm_ids,
        protocols=protocols,
        hardware=raw.get("hardware", manifest.get("hardware", {})),
        modes=raw.get("modes", {}),
        strategies=raw.get("strategies", {}),
        devices=_MappingSequence_Get(raw.get("devices"), name_field="device_id"),
        device_descriptors=_MappingSequence_Get(
            raw.get("device_descriptors"),
            name_field="descriptor_id",
        ),
        capability_endpoints=_MappingSequence_Get(
            raw.get("capability_endpoints"),
            name_field="descriptor_id",
        ),
        capability_routes=_MappingSequence_Get(
            raw.get("capability_routes"),
            name_field="route_id",
        ),
        canonical_channels=_MappingSequence_Get(
            raw.get("canonical_channels"),
            name_field="channel_id",
        ),
        record_views=_MappingSequence_Get(
            raw.get("record_views"),
            name_field="record",
        ),
        event_catalog=(
            raw.get("event_catalog")
            if isinstance(raw.get("event_catalog"), Mapping)
            else {}
        ),
        logging_streams=_MappingSequence_Get(
            raw.get("logging_streams"),
            name_field="record",
        ),
        components=_MappingSequence_Get(
            raw.get("components"),
            name_field="component_id",
        ),
        component_locks=_MappingSequence_Get(
            raw.get("component_locks"),
            name_field="component_id",
        ),
        raw_channel_id_templates=package.semantics.raw_channel_id_templates,
        stable_aliases=aliases,
        calibration=calibration,
        raw_metadata=raw,
    )


class SilverStarSslog0SemanticAdapter:
    def __init__(self, package: DecoderProfilePackage) -> None:
        self.package = package
        LoggingProtocol_Validate(package)

    def Apply(self, dataset: FlightDataset) -> FlightDataset:
        adapted_records = _Events_Adapt(dataset.records, self.package)
        with_events = replace(dataset, records=adapted_records, data_quality=None)
        adapted_series, aliases = _StableSeries_Adapt(
            with_events,
            self.package,
        )
        calibration = _CalibrationSnapshot_Get(with_events, self.package)
        context = _Context_Build(self.package, aliases, calibration)
        from silverstar_flp.analysis.measurement_diagnostics import (
            RecordedMeasurementChannels_Build,
        )

        firmware = context.FirmwareParameters_Get("silverstar.algorithm.estimator.kf6") or {}
        numeric_parameters = {
            name: float(item["value"])
            for name, item in firmware.items()
            if isinstance(item, Mapping) and isinstance(item.get("value"), (int, float))
        }
        measurement_channels = RecordedMeasurementChannels_Build(
            with_events.records, numeric_parameters
        )
        from silverstar_flp.decoder_profiles.eskf15_records import Eskf15Records_Adapt

        eskf_channels, eskf_diagnostics = Eskf15Records_Adapt(with_events.records)
        measurement_channels = {**measurement_channels, **eskf_channels}
        adapted_series = {**adapted_series, **measurement_channels}
        aliases = {**aliases, **{name: name for name in measurement_channels}}
        context = _Context_Build(self.package, aliases, calibration)
        metadata = {
            **dict(with_events.metadata),
            "semantic_adapter_id": "silverstar.sslog0.semantic_adapter/1.1",
            "stable_alias_count": len(aliases),
            "calibration_mode": calibration.mode_name,
            "calibration_ready": calibration.ready,
            "eskf15_covariance_diagnostics": eskf_diagnostics,
        }
        return replace(
            with_events,
            series=adapted_series,
            metadata=metadata,
            semantic_context=context,
        )


Sslog0SemanticAdapter = SilverStarSslog0SemanticAdapter
