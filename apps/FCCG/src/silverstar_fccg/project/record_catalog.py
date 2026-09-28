from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.plugins.manifest import PluginManifest


class RecordCatalogError(FccgError):
    pass


_PRIMITIVE_SIZES = {
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


def _Canonical_Get(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _RecordKey_Get(record: dict[str, Any], source: str) -> tuple[int, int]:
    record_id = record.get("id")
    version = record.get("version")
    if (
        not isinstance(record_id, str)
        or len(record_id) != 4
        or not record_id.startswith("0x")
    ):
        raise RecordCatalogError(
            f"{source}: record.id must use the exact 0xNN form"
        )
    try:
        numeric_id = int(record_id[2:], 16)
    except ValueError as error:
        raise RecordCatalogError(
            f"{source}: record.id must use the exact 0xNN form"
        ) from error
    if not isinstance(version, int) or isinstance(version, bool) or not 0 <= version <= 255:
        raise RecordCatalogError(
            f"{source}: record.version must be an integer from 0 to 255"
        )
    return numeric_id, version


def _Record_Validate(record: Any, source: str) -> tuple[int, int]:
    if not isinstance(record, dict):
        raise RecordCatalogError(f"{source}: records must contain objects")
    key = _RecordKey_Get(record, source)
    name = record.get("name")
    payload_size = record.get("payload_size")
    fields = record.get("fields")
    if not isinstance(name, str) or not name:
        raise RecordCatalogError(f"{source}: record.name must be non-empty text")
    if (
        not isinstance(payload_size, int)
        or isinstance(payload_size, bool)
        or not 1 <= payload_size <= 256
    ):
        raise RecordCatalogError(
            f"{source}: {name} payload_size must be from 1 to 256"
        )
    if not isinstance(fields, list) or not fields:
        raise RecordCatalogError(f"{source}: {name} fields must be non-empty")

    names: set[str] = set()
    occupied: list[tuple[int, int, str]] = []
    next_offset = 0
    for index, field in enumerate(fields):
        field_source = f"{source}: {name}.fields[{index}]"
        if not isinstance(field, dict):
            raise RecordCatalogError(f"{field_source} must be an object")
        field_type = field.get("type")
        if field_type not in _PRIMITIVE_SIZES:
            raise RecordCatalogError(
                f"{field_source}.type is not a supported primitive"
            )
        count = field.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise RecordCatalogError(f"{field_source}.count must be positive")
        field_name = field.get("name", "")
        if field_type != "pad":
            if not isinstance(field_name, str) or not field_name:
                raise RecordCatalogError(f"{field_source}.name is required")
            if field_name in names:
                raise RecordCatalogError(
                    f"{source}: {name} contains duplicate field {field_name}"
                )
            names.add(field_name)
        elif field_name and not isinstance(field_name, str):
            raise RecordCatalogError(f"{field_source}.name must be text")

        offset = field.get("offset", next_offset)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise RecordCatalogError(f"{field_source}.offset must be non-negative")
        length = _PRIMITIVE_SIZES[field_type] * count
        end = offset + length
        if end > payload_size:
            raise RecordCatalogError(
                f"{field_source} exceeds payload_size {payload_size}"
            )
        for previous_start, previous_end, previous_name in occupied:
            if offset < previous_end and previous_start < end:
                raise RecordCatalogError(
                    f"{source}: {name} fields {previous_name} and "
                    f"{field_name or 'pad'} overlap"
                )
        occupied.append((offset, end, field_name or f"pad[{index}]"))
        next_offset = end
    if max(end for _start, end, _name in occupied) != payload_size:
        raise RecordCatalogError(
            f"{source}: {name} fields do not cover payload_size {payload_size}"
        )
    return key


def RecordCatalog_Validate(catalog: Any, source: str = "record catalog") -> None:
    if not isinstance(catalog, dict) or not isinstance(catalog.get("records"), list):
        raise RecordCatalogError(f"{source}: records array is required")
    seen: dict[tuple[int, int], str] = {}
    for record in catalog["records"]:
        key = _Record_Validate(record, source)
        canonical = _Canonical_Get(record)
        previous = seen.get(key)
        if previous is not None and previous != canonical:
            raise RecordCatalogError(
                f"{source}: record 0x{key[0]:02X} version {key[1]} conflicts"
            )
        if previous is not None:
            raise RecordCatalogError(
                f"{source}: record 0x{key[0]:02X} version {key[1]} is duplicated"
            )
        seen[key] = canonical


def RecordCatalogFragment_Load(
    manifest: PluginManifest, relative_path: str
) -> dict[str, Any]:
    path = manifest.payload_root.joinpath(*relative_path.split("/")).resolve()
    try:
        path.relative_to(manifest.payload_root.resolve())
    except ValueError as error:
        raise RecordCatalogError(
            f"{manifest.component_id}: Record Catalog fragment leaves payload"
        ) from error
    if path.is_symlink() or not path.is_file():
        raise RecordCatalogError(
            f"{manifest.component_id}: Record Catalog fragment is missing or unsafe: "
            f"{relative_path}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RecordCatalogError(
            f"{manifest.component_id}: cannot read Record Catalog fragment "
            f"{relative_path}"
        ) from error
    if not isinstance(value, dict) or set(value) - {"records", "record_modes"}:
        raise RecordCatalogError(
            f"{manifest.component_id}: Record Catalog fragment permits only "
            "records and record_modes"
        )
    if not isinstance(value.get("records"), list) or not value["records"]:
        raise RecordCatalogError(
            f"{manifest.component_id}: Record Catalog fragment needs records"
        )
    modes = value.get("record_modes", {})
    if not isinstance(modes, dict) or not all(
        isinstance(name, str)
        and bool(name)
        and isinstance(mode, str)
        and bool(mode)
        for name, mode in modes.items()
    ):
        raise RecordCatalogError(
            f"{manifest.component_id}: record_modes must map names to text"
        )
    # Validate each fragment independently before it reaches the base catalog.
    RecordCatalog_Validate({"records": value["records"]}, relative_path)
    return value


def RecordCatalog_Merge(
    base: dict[str, Any],
    fragments: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    RecordCatalog_Validate(base, "Logging Protocol Record Catalog")
    merged = deepcopy(base)
    records = merged["records"]
    by_key = {
        _RecordKey_Get(record, "Logging Protocol Record Catalog"): _Canonical_Get(
            record
        )
        for record in records
    }
    modes = merged.setdefault("record_modes", {})
    if not isinstance(modes, dict):
        raise RecordCatalogError("Logging Protocol record_modes must be an object")
    for source, fragment in fragments:
        for record in fragment["records"]:
            key = _RecordKey_Get(record, source)
            canonical = _Canonical_Get(record)
            previous = by_key.get(key)
            if previous is not None and previous != canonical:
                raise RecordCatalogError(
                    f"{source}: record 0x{key[0]:02X} version {key[1]} "
                    "conflicts with an existing semantic definition"
                )
            if previous is None:
                records.append(deepcopy(record))
                by_key[key] = canonical
        for name, mode in fragment.get("record_modes", {}).items():
            previous_mode = modes.get(name)
            if previous_mode is not None and previous_mode != mode:
                raise RecordCatalogError(
                    f"{source}: record mode {name} conflicts with {previous_mode}"
                )
            modes[name] = mode
    RecordCatalog_Validate(merged, "merged Record Catalog")
    return merged
