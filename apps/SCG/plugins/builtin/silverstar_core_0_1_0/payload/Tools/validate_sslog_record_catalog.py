#!/usr/bin/env python3
"""Validate the declarative SSLOG Record Catalog and generated profile IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


PACKAGE_SCHEMA_ID = "silverstar.ssdecoder.package-schema/1.2"
CONTAINER_PLUGIN_ID = "silverstar.sslog.container/0.0"
TYPE_SIZES = {
    "u8": 1,
    "i8": 1,
    "u16": 2,
    "i16": 2,
    "u32": 4,
    "i32": 4,
    "u64": 8,
    "i64": 8,
    "f32": 4,
    "pad": 1,
}


class CatalogValidationError(RuntimeError):
    """Raised when the checked-in catalog mirrors are inconsistent."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"cannot read JSON {path}: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogValidationError(message)


def record_wire_size(record: dict[str, Any]) -> int:
    total = 0
    for field in record.get("fields", []):
        field_type = field.get("type")
        require(field_type in TYPE_SIZES,
                f"{record.get('name')}: unsupported field type {field_type}")
        count = field.get("count", 1)
        require(isinstance(count, int) and count > 0,
                f"{record.get('name')}: invalid field count {count}")
        require(field_type == "pad" or isinstance(field.get("name"), str),
                f"{record.get('name')}: non-padding field has no name")
        total += TYPE_SIZES[field_type] * count
    return total


def validate_catalog_shape(catalog: dict[str, Any]) -> None:
    required = {
        "catalog_schema_id", "canonical_json", "field_contract",
        "record_modes", "instance_routing_fields", "format", "endianness",
        "record_header_size", "record_crc", "max_payload_size", "records",
    }
    require(required.issubset(catalog), "Record Catalog is missing required keys")
    require(catalog["catalog_schema_id"] ==
            "silverstar.sslog.record-catalog/1.0",
            "unexpected Record Catalog schema ID")
    require(catalog["format"] == "SSLOG0", "SSLOG format changed")
    require(catalog["endianness"] == "little", "SSLOG endian changed")
    defaults = catalog["field_contract"].get("defaults", {})
    for key in ("unit", "quantity", "scale", "offset", "enum", "bitfield",
                "timestamp", "validity"):
        require(key in defaults, f"field semantic default missing: {key}")
    canonical = catalog["canonical_json"]
    require(canonical.get("encoding") == "UTF-8",
            "canonical JSON encoding must be UTF-8")
    require(canonical.get("key_order") == "lexicographic",
            "canonical JSON keys must be lexicographically sorted")
    require(canonical.get("whitespace") == "none",
            "canonical JSON whitespace contract changed")
    require(canonical.get("line_ending") == "LF" and
            canonical.get("terminal_newline") is True,
            "canonical JSON newline contract changed")
    modes = set(catalog["record_modes"].values())
    require(modes.issubset({"one-shot", "event", "measurement",
                            "source-driven", "periodic"}),
            "Record Catalog contains an executable or unknown producer mode")


def validate_records(catalog: dict[str, Any]) -> None:
    records = catalog["records"]
    require(bool(records), "Record Catalog must contain records")
    ids: set[str] = set()
    enums: set[str] = set()
    names: set[str] = set()
    for record in records:
        for key in ("id", "enum", "name", "version", "payload_size",
                    "size_macro", "c_type", "member", "default_stream",
                    "fields"):
            require(key in record, f"catalog record missing {key}")
        require(record["id"] not in ids, f"duplicate Record ID {record['id']}")
        require(record["enum"] not in enums,
                f"duplicate Record enum {record['enum']}")
        require(record["name"] not in names,
                f"duplicate Record name {record['name']}")
        ids.add(record["id"])
        enums.add(record["enum"])
        names.add(record["name"])
        actual_size = record_wire_size(record)
        require(actual_size == record["payload_size"],
                f"{record['name']}: fields={actual_size}, "
                f"payload_size={record['payload_size']}")
        require(record["name"] in catalog["record_modes"],
                f"{record['name']}: producer mode is missing")
    require("0x1D" in ids, "DECODER_PROFILE_DESCRIPTOR ID 0x1D is missing")


def validate_parser_mirror(catalog: dict[str, Any], parser: dict[str, Any]) -> None:
    require(parser.get("catalog_schema_id") == catalog["catalog_schema_id"],
            "parser metadata catalog schema ID mismatch")
    catalog_records = catalog["records"]
    parser_records = parser.get("records", [])
    require(len(parser_records) == len(catalog_records),
            "parser metadata record count mismatch")
    for expected, actual in zip(catalog_records, parser_records):
        for key in ("id", "enum", "name", "version", "payload_size",
                    "size_macro", "c_type", "member", "default_stream",
                    "fields"):
            require(actual.get(key) == expected.get(key),
                    f"parser metadata mismatch: {expected['name']}.{key}")


def validate_c_mirror(repo: Path, catalog: dict[str, Any]) -> None:
    header = (repo / "Protocol/SSLOG/Inc/sslog_records.h").read_text(
        encoding="utf-8")
    source = (repo / "Protocol/SSLOG/Src/sslog_records.c").read_text(
        encoding="utf-8")
    config = (repo / "Generated/Src/project_log_config.c").read_text(
        encoding="utf-8")
    for record in catalog["records"]:
        record_id = int(record["id"], 16)
        enum_pattern = rf"\b{re.escape(record['enum'])}\s*=\s*0x{record_id:02X}U\b"
        size_pattern = rf"\b{re.escape(record['size_macro'])}\s+{record['payload_size']}U\b"
        require(re.search(enum_pattern, header) is not None,
                f"C Record ID mismatch: {record['enum']}")
        require(re.search(size_pattern, header) is not None,
                f"C payload size mismatch: {record['enum']}")
        require(record["enum"] in source and record["name"] in source,
                f"C metadata/codec missing: {record['name']}")
        require(record["enum"] in config,
                f"Generated log selection missing: {record['name']}")
    count = len(catalog["records"])
    require(re.search(rf"\bSSLOG_RECORD_COUNT\s+{count}U\b", header) is not None,
            "C SSLOG_RECORD_COUNT differs from the Record Catalog")
    c_enums = set(re.findall(r"\b(FLIGHT_LOG_RECORD_\w+)\s*=\s*0x[0-9A-Fa-f]+U", header))
    require(c_enums == {record["enum"] for record in catalog["records"]},
            "C Record IDs contain missing or retired entries")


def profile_hashes(catalog: Any, semantics: Any) -> tuple[bytes, bytes, bytes]:
    catalog_hash = hashlib.sha256(canonical_json_bytes(catalog)).digest()
    semantics_hash = hashlib.sha256(canonical_json_bytes(semantics)).digest()
    generation_input = (
        PACKAGE_SCHEMA_ID.encode("utf-8") + b"\n" +
        CONTAINER_PLUGIN_ID.encode("utf-8") + b"\n" +
        catalog_hash + semantics_hash
    )
    generation_hash = hashlib.sha256(generation_input).digest()
    return catalog_hash, semantics_hash, generation_hash


def c_hash_bytes(source: str, symbol: str) -> bytes:
    pattern = rf"{re.escape(symbol)}\s*\[[^]]+\]\s*=\s*\{{(.*?)\}};"
    match = re.search(pattern, source, re.DOTALL)
    require(match is not None, f"Generated hash symbol is missing: {symbol}")
    values = bytes(int(value, 16) for value in re.findall(
        r"0x([0-9A-Fa-f]{2})U", match.group(1)))
    require(len(values) == 16, f"Generated hash width is not 16: {symbol}")
    return values


def validate_generated_hashes(repo: Path, hashes: tuple[bytes, bytes, bytes]) -> None:
    source = (repo / "Generated/Src/project_log_decoder_profile.c").read_text(
        encoding="utf-8")
    symbols = (
        "s_record_catalog_hash",
        "s_project_semantics_hash",
        "s_generation_profile_hash",
    )
    for symbol, expected in zip(symbols, hashes):
        require(c_hash_bytes(source, symbol) == expected[:16],
                f"Generated decoder profile hash mismatch: {symbol}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-hashes", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    catalog = load_json(repo / "Protocol/SSLOG/schema/sslog_schema.json")
    parser_metadata = load_json(
        repo / "Protocol/SSLOG/schema/sslog_parser_metadata.json")
    catalog_schema = load_json(
        repo / "Protocol/SSLOG/schema/sslog_record_catalog.schema.json")
    semantics = load_json(repo / "Generated/project_semantics.json")
    require(catalog_schema.get("$id") == catalog["catalog_schema_id"],
            "Record Catalog JSON schema ID mismatch")
    validate_catalog_shape(catalog)
    validate_records(catalog)
    validate_parser_mirror(catalog, parser_metadata)
    validate_c_mirror(repo, catalog)
    hashes = profile_hashes(catalog, semantics)
    labels = ("record_catalog", "project_semantics", "generation_profile")
    for label, digest in zip(labels, hashes):
        print(f"{label}_sha256={digest.hex()}")
    if not args.print_hashes:
        validate_generated_hashes(repo, hashes)
    count = len(catalog["records"])
    print(f"SSLOG Record Catalog validation passed: records={count} payloads={count}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CatalogValidationError as exc:
        print(f"SSLOG Record Catalog validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
