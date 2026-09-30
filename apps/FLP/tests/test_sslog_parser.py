from __future__ import annotations

from pathlib import Path
from struct import pack

import pytest

from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.log_parsers.sslog0.records import RECORD_DEFINITIONS
from tests.sslog_synthetic import (
    START_TIMESTAMP_US,
    Event_Payload,
    SyntheticSslogBuilder,
)


def test_every_documented_payload_layout_decodes_at_exact_size() -> None:
    decoded_layouts = 0
    for definition in RECORD_DEFINITIONS.values():
        for payload_length in definition.payload_lengths:
            if definition.name == "MISSION_CONFIG":
                internal_version = 1 if payload_length == 52 else 2
                payload = bytes((internal_version,)) + bytes(payload_length - 1)
            else:
                payload = bytes(payload_length)
            definition.decoder(payload)
            decoded_layouts += 1
    assert len(RECORD_DEFINITIONS) == 28
    assert decoded_layouts == 29


def test_alignment_evidence_decodes_exact_wire_layout(tmp_path: Path) -> None:
    payload = pack(
        "<8B2H2I2Q3f",
        4, 3, 2, 0, 1, 0, 255, 0,
        0x5983, 0x000F, 7, 0xAABBCCDD,
        1_000_000, 1_020_000, 0.5, 0.02, 0.04,
    )
    assert len(payload) == 48
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x28, payload, START_TIMESTAMP_US, record_version=1)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_alignment_evidence.BIN")
    )
    record = dataset.Records_Get("ALIGNMENT_EVIDENCE")[0].payload
    assert record["alignment_algorithm"] == 4
    assert record["constraint_count"] == 3
    assert record["valid_pair_count"] == 2
    assert record["magnetometer_physical_device_id"] == 0x5983
    assert record["mag_calibration_generation"] == 7
    assert record["mag_calibration_set_hash"] == 0xAABBCCDD
    assert record["first_timestamp_us"] == 1_000_000
    assert record["last_timestamp_us"] == 1_020_000
    assert record["minimum_pair_sine"] == 0.5
    assert record["rms_mismatch_rad"] == pytest.approx(0.02)


def test_mission_snapshot_identity_decodes_exact_wire_layout(tmp_path: Path) -> None:
    payload = pack("<5IBBH", 41, 6, 9, 3, 0x11223344, 2, 1, 0)
    assert len(payload) == 24
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x29, payload, START_TIMESTAMP_US, record_version=1)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_snapshot_identity.BIN")
    )
    record = dataset.Records_Get("MISSION_SNAPSHOT_IDENTITY")[0].payload
    assert record["mission_id"] == 41
    assert record["commit_generation"] == 6
    assert record["snapshot_sequence"] == 9
    assert record["imu_calibration_generation"] == 3
    assert record["mag_calibration_set_hash"] == 0x11223344
    assert record["base_instance"] == 2
    assert record["ready"] == 1


def test_mag_calibration_identity_is_per_physical_device(tmp_path: Path) -> None:
    payload = pack("<HBBBBHII", 0x5983, 0, 1, 1, 0, 0, 7, 0xAABBCCDD)
    assert len(payload) == 16
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x2A, payload, START_TIMESTAMP_US, record_version=1)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_mag_cal_identity.BIN")
    )
    record = dataset.Records_Get("MAG_CALIBRATION_IDENTITY")[0].payload
    assert record["physical_device_id"] == 0x5983
    assert record["instance_id"] == 0
    assert record["saved"] == 1
    assert record["generation"] == 7
    assert record["calibration_set_hash"] == 0xAABBCCDD


def test_parser_decodes_known_records_and_skips_unknown_type(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x02, Event_Payload(0x01), START_TIMESTAMP_US)
    builder.Record_Add(0x7F, b"unknown-but-crc-valid", START_TIMESTAMP_US + 1)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 2)
    path = builder.File_Write(tmp_path / "SYNTHETIC_unknown_record.BIN")

    parser = Sslog0ParserPlugin()
    assert parser.probe(path) == 1.0
    dataset = parser.parse(path)

    assert dataset.diagnostics.header_valid
    assert dataset.diagnostics.record_count == 3
    assert dataset.diagnostics.decoded_record_count == 2
    assert dataset.diagnostics.unknown_record_type_count == 1
    assert [record.payload["event_name"] for record in dataset.Records_Get("EVENT")] == [
        "BOOT",
        "MISSION_START",
    ]


def test_parser_skips_unknown_common_record_version(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        0x02,
        Event_Payload(0x01),
        START_TIMESTAMP_US,
        record_version=9,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 1)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_unknown_version.BIN")
    )
    assert dataset.diagnostics.unknown_record_version_count == 1
    assert len(dataset.Records_Get("EVENT")) == 1


def test_record_crc_failure_recovers_at_next_flg1(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        0x02,
        Event_Payload(0x01),
        START_TIMESTAMP_US,
        corrupt_crc=True,
    )
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 10)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_crc_recovery.BIN")
    )
    assert dataset.diagnostics.record_crc_failures == 1
    assert dataset.diagnostics.recovered_after_crc == 1
    assert dataset.diagnostics.decoded_record_count == 1
    assert dataset.Records_Get("EVENT")[0].payload["event_name"] == "MISSION_START"


def test_sync_loss_recovers_without_interpreting_junk(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x02, Event_Payload(0x01), START_TIMESTAMP_US)
    first = builder.records[0]
    builder.records[0] = first + b"JUNK-NOT-A-RECORD"
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 10)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_sync_recovery.BIN")
    )
    assert dataset.diagnostics.recovered_after_sync_loss == 1
    assert dataset.diagnostics.decoded_record_count == 2


def test_truncated_tail_is_reported_and_previous_records_survive(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
    path = builder.File_Write(
        tmp_path / "SYNTHETIC_truncated_tail.BIN",
        trailing_bytes=b"FLG1\x00\x02\x0c",
    )
    dataset = Sslog0ParserPlugin().parse(path)
    assert dataset.diagnostics.truncated_tail
    assert dataset.diagnostics.trailing_bytes == 7
    assert dataset.diagnostics.decoded_record_count == 1
    assert len(dataset.diagnostics.damaged_spans) == 1
    assert dataset.diagnostics.damaged_spans[0].raw_hex == b"FLG1\x00\x02\x0c".hex().upper()


def test_sequence_gap_count_uses_logged_sequence_not_nominal_time(tmp_path: Path) -> None:
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x02, Event_Payload(0x01), START_TIMESTAMP_US, sequence=10)
    builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US + 1, sequence=13)
    dataset = Sslog0ParserPlugin().parse(
        builder.File_Write(tmp_path / "SYNTHETIC_sequence_gap.BIN")
    )
    assert dataset.diagnostics.sequence_gap_count == 1
    assert dataset.diagnostics.sequence_missing_count == 2


def test_short_file_header_is_a_stable_parser_error(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_short.BIN"
    path.write_bytes(b"SSLOG0")
    with pytest.raises(RuntimeError, match="truncated_file_header"):
        Sslog0ParserPlugin().parse(path)
