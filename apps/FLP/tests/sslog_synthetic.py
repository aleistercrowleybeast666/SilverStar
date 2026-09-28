from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

GRAVITY_MPS2 = 9.78
START_TIMESTAMP_US = 1_000_000


def Header_Build(*, build_id: bytes = b"SILV0008") -> bytes:
    header = bytearray(64)
    header[0:8] = b"SSLOG0\x00\x00"
    struct.pack_into("<H", header, 8, 0)
    struct.pack_into("<H", header, 10, 64)
    struct.pack_into("<H", header, 12, 24)
    struct.pack_into("<H", header, 14, 100)
    struct.pack_into("<H", header, 16, 50)
    header[18] = 1
    header[19:22] = bytes((3, 1, 2))
    header[22] = 1
    header[23] = 1
    struct.pack_into("<f", header, 24, GRAVITY_MPS2)
    header[28:36] = b"AIR-NCRC"
    header[36:44] = build_id
    struct.pack_into("<H", header, 44, 4)
    struct.pack_into("<H", header, 46, 2)
    header[48:52] = bytes((0, 1, 0, 8))
    struct.pack_into("<H", header, 52, 256)
    struct.pack_into("<I", header, 60, zlib.crc32(header[:60]) & 0xFFFFFFFF)
    return bytes(header)


def Event_Payload(event_id: int, arg0: int = 0, arg1: int = 0) -> bytes:
    return struct.pack("<B3xII", event_id, arg0, arg1)


def InitialState_Payload(
    *,
    alignment_algorithm: int = 1,
    q_nb: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    alignment_samples: int = 200,
) -> bytes:
    payload = bytearray()
    payload += struct.pack(
        "<BBBBHHHH",
        alignment_algorithm,
        1,
        1,
        3,
        alignment_samples,
        10,
        20,
        0,
    )
    payload += struct.pack("<4f", *q_nb)
    payload += struct.pack("<3f", 0.0, 0.0, GRAVITY_MPS2)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 20.0, 0.0, 40.0)
    payload += struct.pack("<iii", 31_0000000, 121_0000000, 100_000)
    payload += struct.pack("<3f", 1.0, 1.0, 2.0)
    payload += struct.pack("<3f", 0.0, 0.0, 0.0)
    payload += struct.pack("<3f", 0.5, 0.5, 0.5)
    payload += struct.pack("<ff", 120.0, 1.0)
    payload += struct.pack("<6f", 4.0, 4.0, 9.0, 0.25, 0.25, 0.25)
    assert len(payload) == 144
    return bytes(payload)


def SystemConfig_Payload(
    *,
    imu_corrected_decimation: int = 1,
    increment_decimation: int = 1,
    process_accel_std_mps2: tuple[float, float, float] = (1.5, 1.5, 2.0),
    configured_gnss_rate_hz: int = 10,
    configured_magnetometer_rate_hz: int = 50,
    configured_barometer_rate_hz: int = 50,
    nis_profile: tuple[float, float, float, float, float, float, float] = (
        6.635,
        10.828,
        9.210,
        13.816,
        11.345,
        16.266,
        10.0,
    ),
) -> bytes:
    payload = bytearray()
    payload += bytes((0, 1, 0, 8))
    payload += struct.pack("<I", 0)
    payload += bytes(range(1, 11))
    payload += bytes((1, 1, 1, 1))
    payload += struct.pack("<BB", 1, imu_corrected_decimation)
    payload += struct.pack("<6f", 4.0, 4.0, 9.0, 0.25, 0.25, 0.25)
    payload += struct.pack("<3f", *process_accel_std_mps2)
    payload += struct.pack("<5f", 1.0, 1.5, 2.5, 0.3, 5.0)
    payload += struct.pack("<7f", *nis_profile)
    payload += struct.pack("<II", 0xFFFFFFFF, 0x12345678)
    payload += struct.pack(
        "<10H",
        100,
        configured_gnss_rate_hz,
        configured_magnetometer_rate_hz,
        configured_barometer_rate_hz,
        50,
        2,
        50,
        50,
        500,
        0,
    )
    decimation = [1] * 10
    decimation[5] = increment_decimation
    payload += struct.pack("<10H", *decimation)
    payload += struct.pack("<4I", 100_000, 100_000, 100_000, 1_000_000)
    payload += struct.pack("<HBB", 4096, 16, 16)
    assert len(payload) == 176
    return bytes(payload)


def MissionConfig_Payload(
    *,
    alignment_algorithm: int = 1,
    deploy_mask: int = 4,
    deploy_delay_ms: int = 100,
    landing_enable: int = 0,
    known_yaw_deg: float = 0.0,
    magnetic_declination_deg: float = 0.0,
    apogee_vz_threshold_mps: float = -1.0,
) -> bytes:
    payload = bytearray()
    payload += struct.pack(
        "<8B",
        2,
        alignment_algorithm,
        0,
        deploy_mask,
        0,
        landing_enable,
        2,
        1,
    )
    payload += struct.pack(
        "<4f",
        known_yaw_deg,
        magnetic_declination_deg,
        45.0,
        apogee_vz_threshold_mps,
    )
    payload += struct.pack("<4I", 20, deploy_delay_ms, 500, 5)
    payload += struct.pack("<fIf", 0.5, 1000, 0.2)
    payload += struct.pack("<f4I3f2I", 1.0, 5, 50, 80, 500, 30.0, 0.1, 0.5, 1000, 200)
    assert len(payload) == 92
    return bytes(payload)


def ImuCorrected_Payload(timestamp_us: int, sequence: int) -> bytes:
    payload = struct.pack(
        "<QQIHHI3f3ffBBH",
        timestamp_us,
        timestamp_us + 100,
        sequence,
        1,
        1,
        3,
        0.0,
        0.0,
        GRAVITY_MPS2,
        0.0,
        0.0,
        0.0,
        25.0,
        1,
        1,
        0,
    )
    assert len(payload) == 60
    return payload


def InertialIncrement_Payload(start_us: int, end_us: int, sequence: int) -> bytes:
    dt_s = (end_us - start_us) * 1.0e-6
    payload = struct.pack(
        "<QQIf3f3fI",
        start_us,
        end_us,
        sequence,
        dt_s,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        GRAVITY_MPS2 * dt_s,
        0,
    )
    assert len(payload) == 52
    return payload


def PureIns_Payload(
    update_sequence: int,
    dt_s: float = 0.02,
    *,
    q_nb: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    velocity_enu_mps: tuple[float, float, float] = (0.0, 0.0, 0.0),
    position_enu_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    accel_enu_mps2: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bytes:
    payload = bytearray()
    payload += struct.pack("<I", update_sequence)
    payload += struct.pack("<4f", *q_nb)
    payload += struct.pack("<3f", *velocity_enu_mps)
    payload += struct.pack("<3f", *position_enu_m)
    payload += struct.pack("<3f", *accel_enu_mps2)
    payload += struct.pack("<fIBB2x", dt_s, 0, 1, 1)
    assert len(payload) == 68
    return payload


def CalibrationResult_Payload(
    *,
    mode: int = 2,
    state: int = 4,
    ready: int = 1,
    completed_face_mask: int = 0x3F,
    samples: int = 190,
    reject_count: int = 2,
    retry_count: int = 1,
) -> bytes:
    payload = bytearray(
        struct.pack(
            "<HHBBBBIIII",
            1,
            1,
            mode,
            state,
            ready,
            completed_face_mask,
            samples,
            reject_count,
            retry_count,
            17,
        )
    )
    payload += struct.pack("<3f", 0.11, -0.22, 0.33)
    payload += struct.pack("<3f", 1.01, 0.99, 1.02)
    payload += struct.pack("<3f", 0.001, -0.002, 0.003)
    payload += struct.pack("<3f", 1.001, 0.999, 1.002)
    assert len(payload) == 72
    return bytes(payload)


def AlignmentResult_Payload(
    *,
    state: int = 3,
    ready: int = 1,
    selected_mask: int = 0x07,
    ready_mask: int = 0x07,
    attitude_source: int = 2,
    q_nb: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
) -> bytes:
    payload = bytearray()
    payload += struct.pack(
        "<7I4B",
        0x07,
        selected_mask,
        0x01,
        ready_mask,
        0,
        0,
        23,
        state,
        0,
        ready,
        3,
    )
    payload += struct.pack("<Q4f", START_TIMESTAMP_US - 60_000, *q_nb)
    payload += struct.pack("<iii", 31_0000000, 121_0000000, 100_000)
    payload += struct.pack("<Iff", 10, 0.5, 0.8)
    payload += struct.pack("<Iff", 20, 101325.0, 120.0)
    payload += struct.pack("<4B", 3, 3, 3, attitude_source)
    assert len(payload) == 96
    return bytes(payload)


def Kf6State_Payload(
    *,
    position_enu_m: tuple[float, float, float],
    velocity_enu_mps: tuple[float, float, float],
    sequence: int,
    sample_timestamp_us: int,
) -> bytes:
    payload = bytearray()
    payload += struct.pack("<3f", *position_enu_m)
    payload += struct.pack("<3f", *velocity_enu_mps)
    payload += struct.pack("<6f", 1.0, 1.1, 1.2, 0.1, 0.2, 0.3)
    payload += struct.pack("<3f", *position_enu_m)
    payload += struct.pack("<3f", *velocity_enu_mps)
    payload += struct.pack("<4f", position_enu_m[2], 1.2, 2.3, 0.8)
    payload += struct.pack("<5I", 0x00020100, 0, 0, sequence, sequence)
    payload += struct.pack("<2Q", sample_timestamp_us - 2_000, sample_timestamp_us - 1_000)
    payload += struct.pack("<2I4B", 2_000, 1_000, 1, 1, 1, 1)
    assert len(payload) == 136
    return bytes(payload)


def Kf6Diagnostic_Payload(
    *,
    position_update_result: int = 0,
    velocity_update_result: int = 1,
    baro_update_result: int = 2,
) -> bytes:
    payload = bytearray()
    payload += struct.pack("<3f", 0.1, -0.2, 0.3)
    payload += struct.pack("<3f", 0.01, -0.02, 0.03)
    payload += struct.pack("<f", 0.4)
    payload += struct.pack("<3f", 4.0, 4.0, 9.0)
    payload += struct.pack("<3f", 0.25, 0.25, 0.5)
    payload += struct.pack("<f", 1.0)
    payload += struct.pack("<3f", 1.2, 2.3, 0.8)
    payload += struct.pack("<3f", 1.0, 2.0, 3.0)
    payload += struct.pack("<3f", 1.5, 1.5, 2.0)
    payload += struct.pack(
        "<5B7x",
        0x07,
        3,
        position_update_result,
        velocity_update_result,
        baro_update_result,
    )
    assert len(payload) == 104
    return bytes(payload)


def Kf6FullP_Payload(sample_index: int) -> bytes:
    values = tuple(
        float(sample_index * 100 + value_index + 1)
        for value_index in range(21)
    )
    payload = struct.pack("<21f", *values)
    assert len(payload) == 84
    return payload


def Float_U32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


@dataclass(slots=True)
class SyntheticSslogBuilder:
    """Builds explicitly synthetic SSLOG0 test bytes; never presented as flight data."""

    records: list[bytes] = field(default_factory=list)
    sequence: int = 0
    build_id: bytes = b"SILV0008"

    def Record_Add(
        self,
        record_type: int,
        payload: bytes,
        timestamp_us: int,
        *,
        valid_flags: int = 0,
        record_version: int = 0,
        corrupt_crc: bool = False,
        sequence: int | None = None,
    ) -> None:
        record_sequence = self.sequence if sequence is None else sequence
        header = struct.pack(
            "<IBBHIQI",
            0x31474C46,
            record_version,
            record_type,
            len(payload),
            record_sequence,
            timestamp_us,
            valid_flags,
        )
        crc = zlib.crc32(header + payload) & 0xFFFFFFFF
        if corrupt_crc:
            crc ^= 0xFFFFFFFF
        self.records.append(header + payload + struct.pack("<I", crc))
        self.sequence = (record_sequence + 1) & 0xFFFFFFFF

    def Bytes_Build(self, *, trailing_bytes: bytes = b"") -> bytes:
        return Header_Build(build_id=self.build_id) + b"".join(self.records) + trailing_bytes

    def File_Write(self, path: Path, *, trailing_bytes: bytes = b"") -> Path:
        path.write_bytes(self.Bytes_Build(trailing_bytes=trailing_bytes))
        return path


def StationaryFlight_Build(
    path: Path,
    *,
    include_corrected_imu: bool = True,
    include_recorded_increment: bool = True,
    update_count: int = 8,
) -> Path:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x19, MissionConfig_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x05, SystemConfig_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x0D, InitialState_Payload(), START_TIMESTAMP_US)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    if include_corrected_imu:
        for sample_index in range(update_count * 2 + 1):
            timestamp = START_TIMESTAMP_US + sample_index * 10_000
            builder.Record_Add(
                0x16,
                ImuCorrected_Payload(timestamp, sample_index + 1),
                timestamp,
                valid_flags=3,
            )
    if include_recorded_increment:
        for update_index in range(update_count):
            start = START_TIMESTAMP_US + update_index * 20_000
            end = start + 20_000
            builder.Record_Add(
                0x13,
                InertialIncrement_Payload(start, end, update_index + 1),
                end,
                valid_flags=3,
            )
            builder.Record_Add(
                0x07,
                PureIns_Payload(update_index + 1),
                end,
                valid_flags=3,
            )
    return builder.File_Write(path)


def AnalysisFlight_Build(
    path: Path,
    *,
    alignment_algorithm: int = 3,
    include_calibration: bool = True,
    include_alignment_result: bool = True,
    include_deploy_detail: bool = True,
    include_deploy_event: bool = True,
    include_kf6: bool = True,
    include_full_p: bool = False,
    include_landing_event: bool = True,
    update_count: int = 8,
    landing_after_update_count: int | None = None,
    process_accel_std_mps2: tuple[float, float, float] = (1.5, 1.5, 2.0),
    configured_gnss_rate_hz: int = 10,
    configured_magnetometer_rate_hz: int = 50,
    configured_barometer_rate_hz: int = 50,
    nis_profile: tuple[float, float, float, float, float, float, float] = (
        6.635,
        10.828,
        9.210,
        13.816,
        11.345,
        16.266,
        10.0,
    ),
) -> Path:
    """Synthetic analysis-rich flight with calibrated/aligned/deploy/KF6 records."""

    scheduled: list[tuple[int, int, bytes, int]] = []

    def add(
        timestamp_us: int,
        record_type: int,
        payload: bytes,
        valid_flags: int = 0,
    ) -> None:
        scheduled.append((timestamp_us, record_type, payload, valid_flags))

    add(
        START_TIMESTAMP_US - 400_000,
        0x02,
        Event_Payload(0x21),
    )
    if include_calibration:
        add(START_TIMESTAMP_US - 300_000, 0x17, CalibrationResult_Payload())
        add(START_TIMESTAMP_US - 299_900, 0x02, Event_Payload(0x23))
    add(START_TIMESTAMP_US - 200_000, 0x02, Event_Payload(0x26))
    if include_alignment_result:
        attitude_source = (
            3
            if alignment_algorithm == 1
            else 1
            if alignment_algorithm in (0, 2)
            else 2
        )
        source_mask = 0x0F if alignment_algorithm == 1 else 0x07
        add(
            START_TIMESTAMP_US - 100_000,
            0x18,
            AlignmentResult_Payload(
                selected_mask=source_mask,
                ready_mask=source_mask,
                attitude_source=attitude_source,
            ),
        )
        add(START_TIMESTAMP_US - 99_900, 0x02, Event_Payload(0x27))
    add(
        START_TIMESTAMP_US - 20_000,
        0x19,
        MissionConfig_Payload(
            alignment_algorithm=alignment_algorithm,
            deploy_mask=0x07,
            landing_enable=1,
            known_yaw_deg=12.5,
            magnetic_declination_deg=3.25,
            apogee_vz_threshold_mps=-2.0,
        ),
    )
    add(
        START_TIMESTAMP_US - 10_000,
        0x05,
        SystemConfig_Payload(
            process_accel_std_mps2=process_accel_std_mps2,
            nis_profile=nis_profile,
            configured_gnss_rate_hz=configured_gnss_rate_hz,
            configured_magnetometer_rate_hz=(
                configured_magnetometer_rate_hz
            ),
            configured_barometer_rate_hz=configured_barometer_rate_hz,
        ),
    )
    add(
        START_TIMESTAMP_US,
        0x0D,
        InitialState_Payload(
            alignment_algorithm=alignment_algorithm,
            alignment_samples=240,
        ),
    )
    add(START_TIMESTAMP_US, 0x02, Event_Payload(0x03))

    for sample_index in range(update_count * 2 + 1):
        timestamp = START_TIMESTAMP_US + sample_index * 10_000
        add(
            timestamp,
            0x16,
            ImuCorrected_Payload(timestamp, sample_index + 1),
            3,
        )
    deploy_timestamp = START_TIMESTAMP_US + 110_000
    for update_index in range(1, update_count + 1):
        start = START_TIMESTAMP_US + (update_index - 1) * 20_000
        end = start + 20_000
        add(
            end,
            0x13,
            InertialIncrement_Payload(start, end, update_index),
            3,
        )
        pure_position = (
            float(update_index),
            float(update_index * 2),
            float(update_index * 9),
        )
        kf_position = (
            float(update_index * 2),
            float(update_index * 3),
            float(update_index * 10),
        )
        velocity = (1.0, 2.0, -2.13 if update_index >= 5 else 3.0)
        add(
            end,
            0x07,
            PureIns_Payload(
                update_index,
                velocity_enu_mps=velocity,
                position_enu_m=pure_position,
                accel_enu_mps2=(0.1, 0.2, 0.3),
            ),
            3,
        )
        if include_kf6:
            add(
                end,
                0x04,
                Kf6State_Payload(
                    position_enu_m=kf_position,
                    velocity_enu_mps=velocity,
                    sequence=update_index,
                    sample_timestamp_us=end,
                ),
            )
            add(end + 100, 0x08, Kf6Diagnostic_Payload())
            if include_full_p:
                add(end, 0x09, Kf6FullP_Payload(update_index))
    if include_deploy_event:
        add(deploy_timestamp, 0x02, Event_Payload(0x29, arg0=0x07))
    if include_deploy_detail:
        add(
            deploy_timestamp + 100,
            0x02,
            Event_Payload(0x2B, arg0=0x02, arg1=Float_U32(-2.13)),
        )
    landing_update_count = (
        update_count
        if landing_after_update_count is None
        else landing_after_update_count
    )
    if not 0 <= landing_update_count <= update_count:
        raise ValueError("landing_after_update_count_out_of_range")
    if include_landing_event:
        add(
            START_TIMESTAMP_US + landing_update_count * 20_000 + 100,
            0x02,
            Event_Payload(0x2A),
        )

    builder = SyntheticSslogBuilder()
    for timestamp_us, record_type, payload, valid_flags in sorted(
        scheduled,
        key=lambda item: item[0],
    ):
        builder.Record_Add(
            record_type,
            payload,
            timestamp_us,
            valid_flags=valid_flags,
        )
    return builder.File_Write(path)
