from __future__ import annotations

from pathlib import Path

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
    assert len(RECORD_DEFINITIONS) == 25
    assert decoded_layouts == 26


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
