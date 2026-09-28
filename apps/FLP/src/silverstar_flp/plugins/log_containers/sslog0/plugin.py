from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO

from silverstar_flp.core.diagnostics import DiagnosticSeverity
from silverstar_flp.plugins.api.log_container import (
    ContainerError,
    LogContainerMetadata,
    LogContainerPlugin,
    ParseOptions,
    ProbeResult,
    RawRecordFrame,
)

FILE_HEADER_SIZE = 64
RECORD_HEADER_SIZE = 24
RECORD_CRC_SIZE = 4
FILE_MAGIC = b"SSLOG0\x00\x00"
SYNC_VALUE = 0x31474C46
SYNC_BYTES = b"FLG1"
COMMON_HEADER_STRUCT = struct.Struct("<IBBHIQI")
_MAXIMUM_PLAUSIBLE_TIMESTAMP_US = 1_000_000_000_000_000_000


@dataclass(frozen=True, slots=True)
class _RecordCandidate:
    offset: int
    record_version: int
    record_type: int
    payload_length: int
    record_sequence: int
    timestamp_us: int
    valid_flags: int
    total_size: int
    expected_crc: int | None = None
    actual_crc: int | None = None


class Sslog0ContainerPlugin(LogContainerPlugin):
    metadata = LogContainerMetadata(
        plugin_id="silverstar.flight_log.container.0_0",
        container_format_id="SSLOG0",
        version="0.0",
        api_version=1,
        display_name="SilverStar Flight Log Container 0.0",
        builtin=True,
    )

    def probe(self, source: BinaryIO) -> ProbeResult:
        original_offset = source.tell()
        try:
            source.seek(0)
            prefix = source.read(12)
        finally:
            source.seek(original_offset)
        if prefix[:8] != FILE_MAGIC:
            return ProbeResult(0.0, self.metadata.container_format_id)
        profile = struct.unpack_from("<H", prefix, 8)[0] if len(prefix) >= 10 else -1
        return ProbeResult(
            1.0 if profile == 0 else 0.8,
            self.metadata.container_format_id,
            {"profile_id": profile},
        )

    def header_read(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Mapping[str, Any]:
        source.seek(0)
        header_bytes = source.read(FILE_HEADER_SIZE)
        if len(header_bytes) < FILE_HEADER_SIZE:
            raise ContainerError("truncated_file_header", f"size={len(header_bytes)}")
        options.context.Progress_Report(0.01, "parser.header")
        header = self.Header_ParseBytes(header_bytes, options)
        if header["magic_bytes"] != FILE_MAGIC:
            raise ContainerError("invalid_sslog_magic")
        if header["profile_id"] != 0:
            raise ContainerError("unsupported_profile", str(header["profile_id"]))
        expected_sizes = (
            ("file_header_size", FILE_HEADER_SIZE),
            ("record_header_size", RECORD_HEADER_SIZE),
            ("record_crc_size", RECORD_CRC_SIZE),
        )
        for field_name, expected in expected_sizes:
            if header[field_name] != expected:
                raise ContainerError(f"unsupported_{field_name}", str(header[field_name]))
        return header

    def iter_frames(
        self,
        source: BinaryIO,
        options: ParseOptions,
    ) -> Iterator[RawRecordFrame]:
        diagnostics = options.diagnostics
        source.seek(0)
        data = source.read()
        file_size = len(data)
        offset = FILE_HEADER_SIZE
        previous_sequence: int | None = None
        previous_timestamp_us: int | None = None
        previous_offset: int | None = None

        while offset < file_size:
            options.context.Cancel_RaiseIfRequested()
            remaining = file_size - offset
            status, candidate = self._RecordCandidate_Parse(
                data,
                offset,
                options.maximum_payload_length,
            )
            if status == "valid" and candidate is not None:
                pass
            elif status == "truncated_header":
                self._TruncatedTail_Report(
                    options,
                    data,
                    offset,
                    remaining,
                    "truncated_record_header",
                )
                break
            else:
                if status == "crc_failure" and candidate is not None:
                    diagnostics.record_crc_failures += 1
                    diagnostics.Diagnostic_Add(
                        "record_crc_failure",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=candidate.record_sequence,
                        record_type=candidate.record_type,
                        record_version=candidate.record_version,
                        payload_length=candidate.payload_length,
                        timestamp_us=candidate.timestamp_us,
                        expected_crc=candidate.expected_crc,
                        actual_crc=candidate.actual_crc,
                    )
                elif status in {
                    "length_limit",
                    "truncated_payload",
                    "timestamp_invalid",
                }:
                    diagnostics.record_length_failures += 1
                    details: dict[str, Any] = {
                        "remaining": remaining,
                        "maximum_payload_length": options.maximum_payload_length,
                    }
                    sequence = None
                    if candidate is not None:
                        sequence = candidate.record_sequence
                        details.update(
                            {
                                "record_type": candidate.record_type,
                                "record_version": candidate.record_version,
                                "payload_length": candidate.payload_length,
                                "timestamp_us": candidate.timestamp_us,
                            }
                        )
                    diagnostics.Diagnostic_Add(
                        f"record_{status}",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=sequence,
                        **details,
                    )

                recovered, candidate_count = self._ResyncCandidate_Find(
                    data,
                    offset,
                    options,
                )
                if recovered is None:
                    diagnostics.resync_failure_count += 1
                    diagnostics.Diagnostic_Add(
                        "record_resync_limit_reached",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=(
                            candidate.record_sequence
                            if candidate is not None
                            else None
                        ),
                        reason=status,
                        scanned_bytes=min(
                            options.maximum_resync_scan_bytes,
                            max(0, file_size - offset - 1),
                        ),
                        candidate_count=candidate_count,
                        maximum_candidates=options.maximum_resync_candidates,
                    )
                    tail_code = (
                        "truncated_record_payload"
                        if status == "truncated_payload"
                        else "sync_not_found_within_resync_limit"
                    )
                    self._TruncatedTail_Report(
                        options,
                        data,
                        offset,
                        remaining,
                        tail_code,
                        candidate,
                    )
                    break

                recovered_offset = recovered.offset
                raw_end = min(
                    recovered_offset,
                    offset + max(0, options.damaged_span_preview_bytes),
                )
                diagnostics.DamagedSpan_Add(
                    start_offset=offset,
                    end_offset=recovered_offset,
                    reason=status,
                    raw_bytes=bytes(data[offset:raw_end]),
                    record_sequence=(
                        candidate.record_sequence
                        if candidate is not None
                        else None
                    ),
                    record_type=(
                        candidate.record_type
                        if candidate is not None
                        else None
                    ),
                    record_version=(
                        candidate.record_version
                        if candidate is not None
                        else None
                    ),
                    timestamp_us=(
                        candidate.timestamp_us
                        if candidate is not None
                        else None
                    ),
                )
                diagnostics.resync_count += 1
                if status == "crc_failure":
                    diagnostics.recovered_after_crc += 1
                else:
                    diagnostics.recovered_after_sync_loss += 1
                diagnostics.Diagnostic_Add(
                    "record_resynchronized",
                    DiagnosticSeverity.WARNING,
                    offset=offset,
                    record_sequence=(
                        candidate.record_sequence
                        if candidate is not None
                        else None
                    ),
                    reason=status,
                    recovered_offset=recovered_offset,
                    skipped_bytes=recovered_offset - offset,
                    candidate_count=candidate_count,
                    raw_hex=bytes(data[offset:raw_end]).hex().upper(),
                    raw_preview_truncated=raw_end < recovered_offset,
                )
                offset = recovered_offset
                continue

            record_version = candidate.record_version
            record_type = candidate.record_type
            payload_length = candidate.payload_length
            record_sequence = candidate.record_sequence
            timestamp_us = candidate.timestamp_us
            valid_flags = candidate.valid_flags
            total_size = candidate.total_size
            crc_offset = offset + RECORD_HEADER_SIZE + payload_length
            expected_crc = candidate.expected_crc
            actual_crc = candidate.actual_crc
            if expected_crc != actual_crc:
                # The candidate parser owns CRC validation; keep this defensive
                # branch so corrupt payload bytes can never be yielded.
                raise ContainerError(
                    "record_crc_validation_state_invalid",
                    f"offset={offset}",
                )

            diagnostics.record_count += 1
            diagnostics.first_timestamp_us = (
                timestamp_us
                if diagnostics.first_timestamp_us is None
                else min(diagnostics.first_timestamp_us, timestamp_us)
            )
            diagnostics.last_timestamp_us = (
                timestamp_us
                if diagnostics.last_timestamp_us is None
                else max(diagnostics.last_timestamp_us, timestamp_us)
            )
            if previous_sequence is not None:
                expected_sequence = (previous_sequence + 1) & 0xFFFFFFFF
                if record_sequence != expected_sequence:
                    diagnostics.sequence_gap_count += 1
                    missing = (
                        (record_sequence - expected_sequence) & 0xFFFFFFFF
                        if record_sequence != previous_sequence
                        else 1
                    )
                    if missing > 1_000_000_000:
                        missing = 1
                    diagnostics.sequence_missing_count += int(missing)
                    diagnostics.Diagnostic_Add(
                        "record_sequence_gap",
                        DiagnosticSeverity.WARNING,
                        offset=offset,
                        record_sequence=record_sequence,
                        previous_sequence=previous_sequence,
                        expected_sequence=expected_sequence,
                        actual_sequence=record_sequence,
                        missing_count=int(missing),
                        gap_size=int(missing),
                        previous_timestamp_us=previous_timestamp_us,
                        previous_offset=previous_offset,
                        timestamp_us=timestamp_us,
                    )
            previous_sequence = record_sequence
            previous_timestamp_us = timestamp_us
            previous_offset = offset

            payload_offset = offset + RECORD_HEADER_SIZE
            yield RawRecordFrame(
                record_type=record_type,
                record_version=record_version,
                payload_length=payload_length,
                sequence=record_sequence,
                timestamp_us=timestamp_us,
                valid_flags=valid_flags,
                payload_bytes=bytes(data[payload_offset:crc_offset]),
                source_offset=offset,
                crc_valid=True,
            )
            offset += total_size
            if diagnostics.record_count % 256 == 0:
                options.context.Progress_Report(
                    0.02 + (0.80 * offset / max(file_size, 1)),
                    "parser.records",
                )

    @staticmethod
    def _RecordCandidate_Parse(
        data: bytes,
        offset: int,
        maximum_payload_length: int,
    ) -> tuple[str, _RecordCandidate | None]:
        remaining = len(data) - offset
        if remaining < RECORD_HEADER_SIZE:
            return "truncated_header", None
        if data[offset : offset + 4] != SYNC_BYTES:
            return "sync_loss", None
        (
            sync,
            record_version,
            record_type,
            payload_length,
            record_sequence,
            timestamp_us,
            valid_flags,
        ) = COMMON_HEADER_STRUCT.unpack_from(data, offset)
        if sync != SYNC_VALUE:
            return "sync_loss", None
        total_size = RECORD_HEADER_SIZE + payload_length + RECORD_CRC_SIZE
        candidate = _RecordCandidate(
            offset=offset,
            record_version=record_version,
            record_type=record_type,
            payload_length=payload_length,
            record_sequence=record_sequence,
            timestamp_us=timestamp_us,
            valid_flags=valid_flags,
            total_size=total_size,
        )
        if timestamp_us > _MAXIMUM_PLAUSIBLE_TIMESTAMP_US:
            return "timestamp_invalid", candidate
        if payload_length > maximum_payload_length:
            return "length_limit", candidate
        if total_size > remaining:
            return "truncated_payload", candidate
        crc_offset = offset + RECORD_HEADER_SIZE + payload_length
        expected_crc = struct.unpack_from("<I", data, crc_offset)[0]
        actual_crc = zlib.crc32(data[offset:crc_offset]) & 0xFFFFFFFF
        candidate = _RecordCandidate(
            offset=candidate.offset,
            record_version=candidate.record_version,
            record_type=candidate.record_type,
            payload_length=candidate.payload_length,
            record_sequence=candidate.record_sequence,
            timestamp_us=candidate.timestamp_us,
            valid_flags=candidate.valid_flags,
            total_size=candidate.total_size,
            expected_crc=expected_crc,
            actual_crc=actual_crc,
        )
        if expected_crc != actual_crc:
            return "crc_failure", candidate
        return "valid", candidate

    def _ResyncCandidate_Find(
        self,
        data: bytes,
        damaged_offset: int,
        options: ParseOptions,
    ) -> tuple[_RecordCandidate | None, int]:
        scan_stop = min(
            len(data),
            damaged_offset + 1 + max(0, options.maximum_resync_scan_bytes),
        )
        search_offset = damaged_offset + 1
        candidate_count = 0
        while (
            search_offset < scan_stop
            and candidate_count < options.maximum_resync_candidates
        ):
            candidate_offset = data.find(
                SYNC_BYTES,
                search_offset,
                scan_stop,
            )
            if candidate_offset < 0:
                break
            candidate_count += 1
            options.diagnostics.resync_candidate_count += 1
            status, candidate = self._RecordCandidate_Parse(
                data,
                candidate_offset,
                options.maximum_payload_length,
            )
            if status == "valid" and candidate is not None:
                return candidate, candidate_count
            search_offset = candidate_offset + 1
        return None, candidate_count

    @staticmethod
    def _TruncatedTail_Report(
        options: ParseOptions,
        data: bytes,
        offset: int,
        remaining: int,
        code: str,
        candidate: _RecordCandidate | None = None,
    ) -> None:
        diagnostics = options.diagnostics
        raw_end = min(
            len(data),
            offset + max(0, options.damaged_span_preview_bytes),
        )
        raw_bytes = bytes(data[offset:raw_end])
        diagnostics.truncated_tail = True
        diagnostics.trailing_bytes = remaining
        diagnostics.DamagedSpan_Add(
            start_offset=offset,
            end_offset=offset + remaining,
            reason=code,
            raw_bytes=raw_bytes,
            record_sequence=(
                candidate.record_sequence
                if candidate is not None
                else None
            ),
            record_type=(
                candidate.record_type
                if candidate is not None
                else None
            ),
            record_version=(
                candidate.record_version
                if candidate is not None
                else None
            ),
            timestamp_us=(
                candidate.timestamp_us
                if candidate is not None
                else None
            ),
        )
        diagnostics.Diagnostic_Add(
            code,
            DiagnosticSeverity.WARNING,
            offset=offset,
            record_sequence=(
                candidate.record_sequence
                if candidate is not None
                else None
            ),
            remaining=remaining,
            payload_length=(
                candidate.payload_length
                if candidate is not None
                else None
            ),
            raw_hex=raw_bytes.hex().upper(),
            raw_preview_truncated=raw_end < offset + remaining,
        )

    @staticmethod
    def Header_ParseBytes(
        header_bytes: bytes,
        options: ParseOptions,
    ) -> dict[str, object]:
        diagnostics = options.diagnostics
        expected_crc = struct.unpack_from("<I", header_bytes, 60)[0]
        actual_crc = zlib.crc32(header_bytes[:60]) & 0xFFFFFFFF
        diagnostics.header_crc_expected = expected_crc
        diagnostics.header_crc_actual = actual_crc
        header = {
            "magic_bytes": header_bytes[:8],
            "magic": header_bytes[:6].decode("ascii", errors="replace"),
            "profile_id": struct.unpack_from("<H", header_bytes, 8)[0],
            "file_header_size": struct.unpack_from("<H", header_bytes, 10)[0],
            "record_header_size": struct.unpack_from("<H", header_bytes, 12)[0],
            "configured_imu_rate_hz": struct.unpack_from("<H", header_bytes, 14)[0],
            "expected_mechanization_rate_hz": struct.unpack_from("<H", header_bytes, 16)[0],
            "coordinate_frame": header_bytes[18],
            "axis_numbers": tuple(header_bytes[19:22]),
            "quaternion_order": header_bytes[22],
            "quaternion_convention": header_bytes[23],
            "gravity_mps2": struct.unpack_from("<f", header_bytes, 24)[0],
            "air_compatibility_tag": header_bytes[28:36].decode("ascii", errors="replace"),
            "build_id": header_bytes[36:44].decode("ascii", errors="replace"),
            "record_crc_size": struct.unpack_from("<H", header_bytes, 44)[0],
            "mechanization_subsample_count": struct.unpack_from("<H", header_bytes, 46)[0],
            "firmware_version": tuple(header_bytes[48:52]),
            "maximum_record_size": struct.unpack_from("<H", header_bytes, 52)[0],
            "header_crc32": expected_crc,
        }
        semantics_valid = (
            header["magic_bytes"] == FILE_MAGIC
            and header["file_header_size"] == FILE_HEADER_SIZE
            and header["record_header_size"] == RECORD_HEADER_SIZE
            and header["record_crc_size"] == RECORD_CRC_SIZE
            and header["coordinate_frame"] == 1
            and header["axis_numbers"] == (3, 1, 2)
            and header["quaternion_order"] == 1
            and header["quaternion_convention"] == 1
        )
        diagnostics.header_valid = bool(semantics_valid and expected_crc == actual_crc)
        if expected_crc != actual_crc:
            diagnostics.Diagnostic_Add(
                "header_crc_failure",
                DiagnosticSeverity.WARNING,
                offset=60,
                expected_crc=expected_crc,
                actual_crc=actual_crc,
            )
        if not semantics_valid:
            diagnostics.Diagnostic_Add(
                "header_semantics_invalid",
                DiagnosticSeverity.ERROR,
                offset=0,
            )
        return header
