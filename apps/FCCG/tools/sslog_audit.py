"""Strict, offline SSLOG 0.0 byte audit. Never resynchronize to obtain a pass.

Use --decoder for hardware acceptance, or --catalog for codec-only fixtures.
Record IDs, lengths and fields come exclusively from declarative protocol data.
The optional boundary signatures are hypotheses, not repaired output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any
import zipfile
import zlib

_SIZES = {"u8": 1, "i8": 1, "pad": 1, "u16": 2, "i16": 2,
          "u32": 4, "i32": 4, "f32": 4, "u64": 8, "i64": 8}
_HEADER_SIZE = 64
_RECORD_HEADER_SIZE = 24
_CRC_SIZE = 4
_MAGIC = b"SSLOG0\0\0"
_SYNC = b"FLG1"


def Audit_ProfileLoad(path: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    if path.suffix.lower() != ".ssdecoder":
        return json.loads(path.read_text(encoding="utf-8")), None
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate decoder archive members")
        # No extraction, imports, scripts or archive-specified paths are executed.
        for name in ("manifest.json", "record_catalog.json", "project_semantics.json"):
            if archive.getinfo(name).file_size > 8 * 1024 * 1024:
                raise ValueError("decoder member exceeds audit input bound")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "SilverStar.ssdecoder":
            raise ValueError("invalid decoder format")
        schema = manifest.get("package_schema", {})
        if (schema.get("major"), schema.get("minor")) != (1, 2):
            raise ValueError("audit requires decoder package 1.2")
        catalog_bytes = archive.read("record_catalog.json")
        semantics_bytes = archive.read("project_semantics.json")
    catalog_hash = hashlib.sha256(catalog_bytes).hexdigest()
    semantics_hash = hashlib.sha256(semantics_bytes).hexdigest()
    if (catalog_hash != manifest.get("record_catalog_sha256") or
            semantics_hash != manifest.get("project_semantics_sha256")):
        raise ValueError("decoder payload hash mismatch")
    generation_hash = hashlib.sha256(
        b"silverstar.ssdecoder.package-schema/1.2\nsilverstar.sslog.container/0.0\n"
        + bytes.fromhex(catalog_hash) + bytes.fromhex(semantics_hash)).hexdigest()
    if generation_hash != manifest.get("generation_profile_sha256"):
        raise ValueError("decoder generation profile hash mismatch")
    return json.loads(catalog_bytes), {
        "record_catalog_hash_128": catalog_hash[:32],
        "project_semantics_hash_128": semantics_hash[:32],
        "generation_profile_hash_128": generation_hash[:32],
    }


def Audit_FieldsRead(payload: bytes, metadata: dict[str, Any]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    position = 0
    for field in metadata["fields"]:
        position = field.get("offset", position)
        length = _SIZES[field["type"]] * field.get("count", 1)
        if position < 0 or position + length > len(payload):
            raise ValueError("catalog field exceeds record payload")
        result[field.get("name", "")] = payload[position:position + length]
        position += length
    return result


def _FrameError_Get(data: bytes, position: int,
                    records: dict[tuple[int, int], dict[str, Any]],
                    maximum: int) -> tuple[str | None, int]:
    if len(data) - position < _RECORD_HEADER_SIZE + _CRC_SIZE:
        return "trailing_bytes", 0
    if data[position:position + 4] != _SYNC:
        return "bad_sync", 0
    payload_size = struct.unpack_from("<H", data, position + 6)[0]
    length = _RECORD_HEADER_SIZE + payload_size + _CRC_SIZE
    if length > maximum:
        return "oversized_length", length
    metadata = records.get((data[position + 5], data[position + 4]))
    if metadata is None:
        return "unknown_record_or_version", length
    if payload_size != metadata["payload_size"]:
        return "payload_length_mismatch", length
    if position + length > len(data):
        return "truncated_record", length
    stored = struct.unpack_from("<I", data, position + length - _CRC_SIZE)[0]
    if zlib.crc32(data[position:position + length - _CRC_SIZE]) != stored:
        return "bad_crc", length
    return None, length


def Audit_BoundarySignatures(data: bytes, position: int, length: int,
                            records: dict[tuple[int, int], dict[str, Any]],
                            maximum: int) -> list[dict[str, Any]]:
    """Test one-byte hypotheses at the first bad frame's sector boundaries."""
    signatures = []
    if not 28 <= length <= maximum:
        return signatures
    for boundary in range(((position // 512) + 1) * 512, position + length + 1, 512):
        for offset in (boundary - 1, boundary, boundary + 1):
            if not position <= offset < min(position + length, len(data)):
                continue
            local = offset - position
            original = data[position:position + length + 1]
            removed = original[:local] + original[local + 1:]
            if _FrameError_Get(removed, 0, records, maximum)[0] is None:
                signatures.append({"kind": "extra_byte", "offset": offset,
                                   "sector_boundary": boundary,
                                   "adjacent_equal": offset > 0 and data[offset] == data[offset - 1]})
            original = data[position:position + length - 1]
            for value in range(256):
                inserted = original[:local] + bytes([value]) + original[local:]
                if _FrameError_Get(inserted, 0, records, maximum)[0] is None:
                    signatures.append({"kind": "missing_byte", "offset": offset,
                                       "sector_boundary": boundary, "candidate_byte": value})
                    break
    return signatures


def Audit_CandidatesScan(data: bytes, catalog: dict[str, Any]) -> dict[str, Any]:
    """Forensics only: scan magic candidates without changing the strict verdict.

    Recovered sequence gaps combine corruption losses and producer drops. They
    cannot be used to account for queue loss or to qualify a damaged file.
    """
    records = {(int(record["id"], 16), record["version"]): record for record in catalog["records"]}
    maximum = 28 + int(catalog.get("max_payload_size", 256))
    result: dict[str, Any] = {"candidates": 0, "valid_crc_candidates": 0,
                             "errors": {}, "sequence_gap_count": 0,
                             "sequence_reorders": 0, "queue_overflow_max": 0}
    position = 64
    expected = None
    while (position := data.find(_SYNC, position)) >= 0:
        result["candidates"] += 1
        error, length = _FrameError_Get(data, position, records, maximum)
        if error:
            result["errors"][error] = result["errors"].get(error, 0) + 1
        else:
            result["valid_crc_candidates"] += 1
            sequence = struct.unpack_from("<I", data, position + 8)[0]
            if expected is not None:
                delta = (sequence - expected) & 0xFFFFFFFF
                if delta >= 0x80000000:
                    result["sequence_reorders"] += 1
                elif delta:
                    result["sequence_gap_count"] += 1
            expected = (sequence + 1) & 0xFFFFFFFF
            metadata = records[(data[position + 5], data[position + 4])]
            if metadata["name"] == "STATS":
                fields = Audit_FieldsRead(data[position + 24:position + length - 4], metadata)
                overflow = int.from_bytes(fields["logger_queue_overflow_count"], "little")
                result["queue_overflow_max"] = max(result["queue_overflow_max"], overflow)
        position += 1
    return result


def Audit_Bytes(data: bytes, catalog: dict[str, Any], *,
                decoder_hashes: dict[str, str] | None = None,
                allow_queue_drops: bool = False) -> dict[str, Any]:
    if (catalog.get("format") != "SSLOG0" or
            catalog.get("record_header_size") != _RECORD_HEADER_SIZE or
            catalog.get("record_crc") != "CRC-32/ISO-HDLC"):
        raise ValueError("unsupported container contract")
    records = {(int(record["id"], 16), record["version"]): record
               for record in catalog["records"]}
    if len(records) != len(catalog["records"]):
        raise ValueError("duplicate catalog record/version")
    maximum = _RECORD_HEADER_SIZE + int(catalog.get("max_payload_size", 256)) + _CRC_SIZE
    result: dict[str, Any] = {
        "file_bytes": len(data), "header_crc_ok": False, "records": 0,
        "integrity_ok": False, "sequence_gap_records": 0, "sequence_gap_count": 0,
        "sequence_reorders": 0, "queue_overflow_max": 0, "record_counts": {},
        "errors": [], "boundary_signatures": [], "decoder_match": None,
        "passed": False,
    }
    if len(data) < _HEADER_SIZE:
        result["errors"].append({"kind": "truncated_file_header", "offset": 0})
        return result
    result["header_crc_ok"] = zlib.crc32(data[:60]) == struct.unpack_from("<I", data, 60)[0]
    if (data[:8] != _MAGIC or struct.unpack_from("<H", data, 10)[0] != 64 or
            struct.unpack_from("<H", data, 12)[0] != 24 or
            struct.unpack_from("<H", data, 44)[0] != 4 or
            struct.unpack_from("<H", data, 52)[0] != maximum or
            not result["header_crc_ok"]):
        result["errors"].append({"kind": "invalid_file_header", "offset": 0})
        return result
    position = _HEADER_SIZE
    expected_sequence = 0
    descriptor_count = 0
    descriptor_matches = True
    while position < len(data):
        error, length = _FrameError_Get(data, position, records, maximum)
        if error is not None:
            result["errors"].append({"kind": error, "offset": position, "declared_length": length})
            result["boundary_signatures"] = Audit_BoundarySignatures(
                data, position, length, records, maximum)
            break  # Exact framing is mandatory. No parser resync.
        metadata = records[(data[position + 5], data[position + 4])]
        sequence = struct.unpack_from("<I", data, position + 8)[0]
        delta = (sequence - expected_sequence) & 0xFFFFFFFF
        if delta:
            if delta >= 0x80000000:
                result["sequence_reorders"] += 1
            else:
                result["sequence_gap_records"] += delta
                result["sequence_gap_count"] += 1
        expected_sequence = (sequence + 1) & 0xFFFFFFFF
        fields = Audit_FieldsRead(data[position + 24:position + length - 4], metadata)
        if metadata["name"] == "STATS":
            overflow = int.from_bytes(fields["logger_queue_overflow_count"], "little")
            result["queue_overflow_max"] = max(result["queue_overflow_max"], overflow)
        if metadata["name"] == "DECODER_PROFILE_DESCRIPTOR" and decoder_hashes is not None:
            descriptor_count += 1
            descriptor_matches &= all(fields[name].hex() == value
                                      for name, value in decoder_hashes.items())
        counts = result["record_counts"]
        counts[metadata["name"]] = counts.get(metadata["name"], 0) + 1
        result["records"] += 1
        position += length
    result["strict_end_offset"] = position
    result["unvalidated_tail_bytes"] = len(data) - position
    if result["records"] == 0 and not result["errors"]:
        result["errors"].append({"kind": "empty_log", "offset": position})
    result["integrity_ok"] = not result["errors"]
    result["sequence_ok"] = result["sequence_gap_count"] == 0 and result["sequence_reorders"] == 0
    result["queue_drop_accounted"] = (result["sequence_gap_records"] == result["queue_overflow_max"]
                                      and result["sequence_reorders"] == 0)
    if decoder_hashes is not None:
        result["decoder_match"] = descriptor_count > 0 and descriptor_matches
    result["passed"] = bool(result["integrity_ok"] and
                            (result["sequence_ok"] or (allow_queue_drops and result["queue_drop_accounted"]))
                            and result["decoder_match"] is not False)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    profiles = parser.add_mutually_exclusive_group(required=True)
    profiles.add_argument("--decoder", type=Path)
    profiles.add_argument("--catalog", type=Path)
    parser.add_argument("--allow-queue-drops", action="store_true",
                        help="pass only gaps exactly accounted for by valid STATS overflow counts")
    parser.add_argument("--scan-candidates", action="store_true",
                        help="add forensic candidate counts; never changes the strict pass/fail result")
    args = parser.parse_args()
    try:
        catalog, hashes = Audit_ProfileLoad(args.decoder or args.catalog)
        data = args.log.read_bytes()
        report = Audit_Bytes(data, catalog, decoder_hashes=hashes,
                             allow_queue_drops=args.allow_queue_drops)
        if args.scan_candidates:
            report["candidate_scan_forensics_only"] = Audit_CandidatesScan(data, catalog)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"passed": False, "input_error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
