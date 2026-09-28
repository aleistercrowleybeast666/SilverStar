"""Matching synthetic .ssdecoder 1.2/log pair with dynamic IMU and barometer."""

import json
import math
import struct
from pathlib import Path

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_BuildFromCorrectedImu,
)
from silverstar_flp.plugins.registry import builtin_registry
from tests.parameter_fixtures import FirmwareSets_Build
from tests.sslog_synthetic import START_TIMESTAMP_US, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    _DescriptorPayload_Build,
    _Package_Write,
    _PackageFiles_Build,
)


def NavigationPair_Open(
    directory: Path, overrides=None, *, preflight_us=0, flight_samples=1001, omit_imu=False
):
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).parent / "fixtures/parameter_contracts"
    catalog = json.loads(
        (fixtures / "synthetic_navigation_catalog.json").read_text(encoding="utf8")
    )
    semantics = json.loads(
        (fixtures / "synthetic_navigation_semantics.json").read_text(encoding="utf8")
    )
    semantics["firmware_algorithm_parameters"] = [
        group for group in FirmwareSets_Build(overrides)
        if group["component"] in semantics["algorithms"]
    ]
    files, hashes = _PackageFiles_Build(catalog_document=catalog, semantics_document=semantics)
    package, _ = _Package_Write(directory / "SYNTHETIC_navigation.ssdecoder", files=files)
    records = {r["name"]: r for r in catalog["records"]}
    builder = SyntheticSslogBuilder()

    corrected = []

    def add(name, timestamp, values, flags=0):
        record = records[name]
        payload = bytearray()
        formats = {
            "f32": "f",
            "f64": "d",
            "u8": "B",
            "u16": "H",
            "u32": "I",
            "u64": "Q",
            "i32": "i",
        }
        for field in record["fields"]:
            count = field.get("count", 1)
            kind = field["type"]
            if kind == "pad":
                payload.extend(bytes(count))
                continue
            value = values.get(field["name"], 0 if count == 1 else [0] * count)
            if count == 1:
                value = [value]
            payload.extend(struct.pack("<" + formats[kind] * count, *value))
        builder.Record_Add(int(record["id"], 0), bytes(payload), timestamp, valid_flags=flags,
                           record_version=record['version'])
        if name == 'IMU_CORRECTED':
            corrected.append(DecodedRecord(int(record['id'], 0), name, record['version'],
                len(payload), len(corrected)+1, timestamp, flags, values, 0))

    start = START_TIMESTAMP_US + preflight_us
    if preflight_us:
        add("EVENT", START_TIMESTAMP_US - 4, {"event_id": 1})
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
    add(
        "CALIBRATION_RESULT",
        start - 2,
        {
            "source_id": 1,
            "virtual_imu_id": 1,
            "state": 4,
            "ready": 1,
            "accel_scale": [1] * 3,
            "gyro_scale": [1] * 3,
        },
    )
    kf = {p["id"]: p["value"] for p in semantics["firmware_algorithm_parameters"][1]["parameters"]}
    p0 = [kf[f"p0_{group}_{axis}"] for group in ("position", "velocity") for axis in "enu"]
    add(
        "SYSTEM_CONFIG",
        start - 1,
        {
            "configured_imu_rate_hz": 100,
            "mechanization_subsample_count": 2,
            "mechanization_min_sample_rate_hz": 50,
            "mechanization_max_sample_rate_hz": 200,
            "p0_diagonal": p0,
            "process_accel_std_mps2": [kf[f"process_accel_std_{axis}"] for axis in "enu"],
            "nis_profile": [
                kf[name]
                for name in (
                    "nis_1d_soft",
                    "nis_1d_hard",
                    "nis_2d_soft",
                    "nis_2d_hard",
                    "nis_3d_soft",
                    "nis_3d_hard",
                    "nis_max_r_scale",
                )
            ],
        },
    )
    add(
        "INITIAL_STATE",
        start,
        {"q_nb": [1, 0, 0, 0], "p0_diagonal": p0, "barometer_origin_std_m": 0.2},
    )
    add("EVENT", start, {"event_id": 3})
    operation = 0
    present = 0
    for index in range(flight_samples):
        timestamp = start + index * 10000
        t = index * 0.01
        if not omit_imu:
            add(
                "IMU_CORRECTED",
                timestamp,
                {
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index + 1,
                    "source_id": 1,
                    "virtual_imu_id": 1,
                    "valid_mask": 3,
                    "accel_b_mps2": [
                        0.4 * math.cos(0.9 * t),
                        0.3 * math.sin(0.7 * t),
                        9.78 + 2 * math.sin(1.2 * t),
                    ],
                    "gyro_b_radps": [0, 0, 0.04 * math.cos(t)],
                    "correction_valid": 1,
                },
                3,
            )
        if not omit_imu and index and index % 2 == 0:
            increments, _ = InertialIncrement_BuildFromCorrectedImu(
                tuple(corrected[-3:]), start_timestamp_us=start)
            increment = increments[0]
            sequence = index // 2
            add('INERTIAL_INCREMENT', timestamp, dict(
                interval_start_timestamp_us=increment.interval_start_timestamp_us,
                interval_end_timestamp_us=timestamp, sequence=sequence,
                source_sequence=index+1, dt_s=increment.dt_s,
                delta_theta_b_corrected=increment.delta_theta_b,
                delta_velocity_b_sculling_corrected=increment.delta_velocity_b,
                subsample_count=2))
            operation += 1
            present = timestamp
            add('ESTIMATOR_STEP', timestamp, dict(interval_end_timestamp_us=timestamp,
                estimator_present_timestamp_us=present, operation_sequence=operation,
                source_sequence=sequence, replay_epoch=1, attitude_result=1))
        if index and index % 5 == 0:
            altitude = 2 / 1.2 * t - 2 / 1.2**2 * math.sin(1.2 * t)
            add(
                "BARO_NATIVE",
                timestamp,
                {
                    "source_descriptor_id": 3,
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index,
                    "altitude_m": altitude,
                    "altitude_variance_m2": 16,
                    "healthy": 1,
                    "valid_mask": 1,
                },
                4,
            )
            operation += 1
            add(
                "BARO_MEASUREMENT",
                timestamp,
                {
                    "sample_timestamp_us": timestamp,
                    "receive_timestamp_us": timestamp,
                    "sequence": index,
                    "relative_altitude_m": altitude,
                    "measurement_timestamp_us": present,
                    "estimator_present_timestamp_us": present,
                    "operation_sequence": operation,
                    "replay_epoch": 1,
                    "measurement_timestamp_trusted": 0,
                    "variance_m2": max(16, kf["baro_std_m"] ** 2) + 0.04,
                    "valid_mask": 1,
                },
                4,
            )
    log = builder.File_Write(directory / "SYNTHETIC_navigation.BIN")
    return LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(directory / "cache")
    ).Open(LogOpenRequest(log_path=log, decoder_package_path=package))


def SyntheticOperations_Attach(dataset):
    from dataclasses import replace
    timeline = []
    for name, rank in (('ESTIMATOR_STEP', 0), ('GNSS_MEASUREMENT', 1), ('BARO_MEASUREMENT', 2)):
        timeline.extend((record.timestamp_us, rank, record) for record in dataset.Records_Get(name))
    timeline.sort(key=lambda item: item[:2])
    records = {name:list(items) for name, items in dataset.records.items()}
    for name in ('ESTIMATOR_STEP', 'GNSS_MEASUREMENT', 'BARO_MEASUREMENT'):
        records[name] = []
    operation, present = 0, 0
    for ordinal, (_, rank, record) in enumerate(timeline, 1):
        payload = dict(record.payload)
        if rank == 0:
            operation += 1
            present = record.timestamp_us
            payload['interval_end_timestamp_us'] = present
            payload['operation_sequence'] = operation
        elif rank == 1:
            payload['receive_operation_sequence'] = operation + 1
            payload['position_operation_sequence'] = operation + 2
            payload['velocity_operation_sequence'] = operation + 2
            operation += 2
            payload.update(receive_result=0, position_replay_result=0, velocity_replay_result=0,
                           position_measurement_timestamp_us=present,
                           velocity_measurement_timestamp_us=present,
                           valid_group_mask=(3 if payload.get('position_usable') else 0) |
                                            (12 if payload.get('velocity_valid_mask', 0) else 0))
        else:
            operation += 1
            payload.update(operation_sequence=operation, replay_result=0,
                           measurement_timestamp_us=present, measurement_timestamp_trusted=0)
        payload.update(estimator_present_timestamp_us=present, replay_epoch=1, replay_generation=0)
        records[record.record_name].append(replace(record, record_sequence=ordinal,
                                                   payload=payload))
    return replace(dataset, records=records)
