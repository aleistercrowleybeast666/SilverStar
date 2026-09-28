from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from silverstar_flp.decoder_profiles.errors import DecoderProfileError, RecordDecodeError

_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCALAR_FORMATS: Mapping[str, tuple[str, int]] = MappingProxyType(
    {
        "u8": ("B", 1),
        "i8": ("b", 1),
        "u16": ("H", 2),
        "i16": ("h", 2),
        "u32": ("I", 4),
        "i32": ("i", 4),
        "u64": ("Q", 8),
        "i64": ("q", 8),
        "f32": ("f", 4),
        "f64": ("d", 8),
    }
)
SUPPORTED_SCALAR_TYPES = frozenset(_SCALAR_FORMATS)


def _Integer_Parse(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise DecoderProfileError("decoder_integer_invalid", field_name)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise DecoderProfileError(
                "decoder_integer_invalid",
                f"{field_name}={value}",
            ) from exc
    raise DecoderProfileError("decoder_integer_invalid", field_name)


def _Labels_Normalize(value: Any, *, field_name: str) -> Mapping[int, str]:
    if value is None:
        return MappingProxyType({})
    normalized: dict[int, str] = {}
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, list):
        items = (
            (item.get("value", item.get("bit")), item.get("name", item.get("label")))
            for item in value
            if isinstance(item, Mapping)
        )
    else:
        raise DecoderProfileError("decoder_labels_invalid", field_name)
    for raw_key, raw_label in items:
        if isinstance(raw_key, str) and isinstance(raw_label, int):
            raw_key, raw_label = raw_label, raw_key
        key = _Integer_Parse(raw_key, field_name=field_name)
        if not isinstance(raw_label, str) or not raw_label:
            raise DecoderProfileError("decoder_label_invalid", f"{field_name}:{key}")
        if key in normalized:
            raise DecoderProfileError("decoder_label_duplicate", f"{field_name}:{key}")
        normalized[key] = raw_label
    return MappingProxyType(normalized)


def _BitLabels_Normalize(value: Any, *, field_name: str) -> Mapping[int, str]:
    if value is None:
        return MappingProxyType({})
    if isinstance(value, Mapping):
        return _Labels_Normalize(value, field_name=field_name)
    if not isinstance(value, list):
        raise DecoderProfileError("decoder_labels_invalid", field_name)
    normalized: dict[int, str] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise DecoderProfileError("decoder_labels_invalid", field_name)
        raw_bit = item.get("bit")
        raw_mask = item.get("mask")
        if raw_bit is None and raw_mask is None:
            raise DecoderProfileError("decoder_label_invalid", field_name)
        if raw_bit is None:
            mask = _Integer_Parse(raw_mask, field_name=field_name)
            if mask <= 0 or mask & (mask - 1):
                raise DecoderProfileError("decoder_bitfield_mask_invalid", field_name)
            bit = mask.bit_length() - 1
        else:
            bit = _Integer_Parse(raw_bit, field_name=field_name)
        label = item.get("name", item.get("label"))
        if bit < 0 or bit > 63 or not isinstance(label, str) or not label:
            raise DecoderProfileError("decoder_label_invalid", f"{field_name}:{bit}")
        if bit in normalized:
            raise DecoderProfileError("decoder_label_duplicate", f"{field_name}:{bit}")
        normalized[bit] = label
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class FieldLayout:
    name: str | None
    data_type: str
    count: int = 1
    scale: float = 1.0
    offset: float = 0.0
    enum_labels: Mapping[int, str] = field(default_factory=dict)
    bit_labels: Mapping[int, str] = field(default_factory=dict)
    enum_reference: str | None = None
    bitfield_reference: str | None = None

    @property
    def byte_size(self) -> int:
        if self.data_type == "pad":
            return self.count
        return _SCALAR_FORMATS[self.data_type][1] * self.count

    @classmethod
    def FromDocument(cls, document: Mapping[str, Any], index: int) -> FieldLayout:
        data_type = document.get("type")
        if not isinstance(data_type, str):
            raise DecoderProfileError("decoder_field_type_missing", f"field={index}")
        data_type = data_type.lower()
        array_match = re.fullmatch(r"([a-z0-9]+)\[([1-9][0-9]*)\]", data_type)
        explicit_count = document.get(
            "count",
            document.get("array_length", document.get("length")),
        )
        if array_match is not None:
            data_type = array_match.group(1)
            if explicit_count is not None:
                raise DecoderProfileError(
                    "decoder_field_count_conflict",
                    f"field={index}",
                )
            explicit_count = int(array_match.group(2))
        if data_type == "padding":
            data_type = "pad"
        if data_type != "pad" and data_type not in _SCALAR_FORMATS:
            raise DecoderProfileError("decoder_field_type_unsupported", data_type)
        count = _Integer_Parse(
            explicit_count if explicit_count is not None else document.get("bytes", 1),
            field_name=f"field[{index}].count",
        )
        if count <= 0 or count > 65_536:
            raise DecoderProfileError("decoder_field_count_invalid", f"field={index}")
        name = document.get("name")
        if data_type == "pad":
            name = None
        elif not isinstance(name, str) or not _FIELD_NAME_PATTERN.fullmatch(name):
            raise DecoderProfileError("decoder_field_name_invalid", f"field={index}")
        scale = document.get("scale", 1.0)
        offset = document.get("offset", 0.0)
        if (
            isinstance(scale, bool)
            or not isinstance(scale, (int, float))
            or not math.isfinite(scale)
        ):
            raise DecoderProfileError("decoder_field_scale_invalid", str(name))
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, float))
            or not math.isfinite(offset)
        ):
            raise DecoderProfileError("decoder_field_offset_invalid", str(name))
        raw_enum = document.get("enum")
        raw_bitfield = document.get("bitfield")
        return cls(
            name=name,
            data_type=data_type,
            count=count,
            scale=float(scale),
            offset=float(offset),
            enum_labels=_Labels_Normalize(
                None if isinstance(raw_enum, str) else raw_enum,
                field_name=str(name),
            ),
            bit_labels=_BitLabels_Normalize(
                None if isinstance(raw_bitfield, str) else raw_bitfield,
                field_name=str(name),
            ),
            enum_reference=raw_enum if isinstance(raw_enum, str) else None,
            bitfield_reference=(
                raw_bitfield if isinstance(raw_bitfield, str) else None
            ),
        )

    def Decode(self, payload: bytes, cursor: int) -> tuple[Any, int]:
        if self.data_type == "pad":
            end = cursor + self.count
            if end > len(payload):
                raise RecordDecodeError("record_payload_underflow", f"offset={cursor}")
            return None, end
        format_text, scalar_size = _SCALAR_FORMATS[self.data_type]
        size = scalar_size * self.count
        if cursor + size > len(payload):
            raise RecordDecodeError("record_payload_underflow", f"offset={cursor}")
        values = struct.unpack_from("<" + (format_text * self.count), payload, cursor)
        transformed = tuple((value * self.scale) + self.offset for value in values)
        if self.scale == 1.0 and self.offset == 0.0:
            transformed = values
        value: Any = transformed[0] if self.count == 1 else tuple(transformed)
        return value, cursor + size


@dataclass(frozen=True, slots=True)
class RecordLayout:
    record_type: int
    record_version: int
    name: str
    payload_size: int
    fields: tuple[FieldLayout, ...]

    @classmethod
    def FromDocument(cls, document: Mapping[str, Any], index: int) -> RecordLayout:
        type_value = document.get("id")
        version_value = document.get("version")
        record_type = _Integer_Parse(type_value, field_name=f"records[{index}].record_type")
        record_version = _Integer_Parse(
            version_value,
            field_name=f"records[{index}].record_version",
        )
        if not 0 <= record_type <= 255 or not 0 <= record_version <= 255:
            raise DecoderProfileError("decoder_record_key_out_of_range", f"record={index}")
        raw_name = document.get("name")
        if not isinstance(raw_name, str) or not raw_name:
            raise DecoderProfileError("decoder_record_name_invalid", f"record={index}")
        name = raw_name.removeprefix("FLIGHT_LOG_RECORD_")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise DecoderProfileError("decoder_record_name_invalid", f"record={index}")
        raw_fields = document.get("fields")
        if not isinstance(raw_fields, list):
            raise DecoderProfileError("decoder_record_fields_invalid", name)
        fields = tuple(
            FieldLayout.FromDocument(field_document, field_index)
            for field_index, field_document in enumerate(raw_fields)
            if isinstance(field_document, Mapping)
        )
        if len(fields) != len(raw_fields):
            raise DecoderProfileError("decoder_record_field_invalid", name)
        payload_size = _Integer_Parse(
            document.get("payload_size"),
            field_name=f"records[{index}].payload_size",
        )
        calculated_size = sum(field.byte_size for field in fields)
        if payload_size < 0 or payload_size > 1_048_576:
            raise DecoderProfileError(
                "decoder_record_payload_size_invalid",
                f"{name}:{payload_size}",
            )
        if calculated_size != payload_size:
            raise DecoderProfileError(
                "decoder_record_payload_size_mismatch",
                f"{name}:declared={payload_size}:calculated={calculated_size}",
            )
        field_names = [field.name for field in fields if field.name is not None]
        if len(field_names) != len(set(field_names)):
            raise DecoderProfileError("decoder_record_field_duplicate", name)
        return cls(record_type, record_version, name, payload_size, fields)

    def Decode(self, payload: bytes) -> dict[str, Any]:
        if len(payload) != self.payload_size:
            raise RecordDecodeError(
                "record_payload_length_mismatch",
                f"{self.name}:actual={len(payload)}:expected={self.payload_size}",
            )
        decoded: dict[str, Any] = {}
        cursor = 0
        for field_layout in self.fields:
            value, cursor = field_layout.Decode(payload, cursor)
            if field_layout.name is None:
                continue
            decoded[field_layout.name] = value
            if field_layout.enum_labels and isinstance(value, int):
                decoded[f"{field_layout.name}__enum"] = field_layout.enum_labels.get(
                    value,
                    f"UNKNOWN_{value}",
                )
            if field_layout.bit_labels and isinstance(value, int):
                decoded[f"{field_layout.name}__bits"] = tuple(
                    label
                    for bit, label in sorted(field_layout.bit_labels.items())
                    if value & (1 << bit)
                )
        if cursor != len(payload):
            raise RecordDecodeError(
                "record_payload_trailing_bytes",
                f"{self.name}:remaining={len(payload) - cursor}",
            )
        return decoded


@dataclass(frozen=True, slots=True)
class RecordCatalog:
    layouts: Mapping[tuple[int, int], RecordLayout]
    field_metadata: Mapping[tuple[str, str], Mapping[str, Any]]
    sha256: str
    schema_version: int

    @classmethod
    def FromDocument(
        cls,
        document: Mapping[str, Any],
        *,
        source_bytes: bytes | None = None,
    ) -> RecordCatalog:
        catalog_schema_id = document.get("catalog_schema_id")
        if catalog_schema_id != "silverstar.sslog.record-catalog/1.0":
            raise DecoderProfileError(
                "decoder_record_catalog_schema_id_unsupported",
                str(catalog_schema_id),
            )
        endianness = document.get("endianness")
        if endianness != "little":
            raise DecoderProfileError("decoder_endianness_unsupported", str(endianness))
        raw_records = document.get("records")
        if not isinstance(raw_records, list) or not raw_records:
            raise DecoderProfileError("decoder_record_catalog_empty")
        layouts: dict[tuple[int, int], RecordLayout] = {}
        for index, raw_layout in enumerate(raw_records):
            if not isinstance(raw_layout, Mapping):
                raise DecoderProfileError("decoder_record_layout_invalid", f"record={index}")
            layout = RecordLayout.FromDocument(raw_layout, index)
            key = (layout.record_type, layout.record_version)
            if key in layouts:
                raise DecoderProfileError(
                    "decoder_record_layout_conflict",
                    f"type={key[0]}:version={key[1]}",
                )
            layouts[key] = layout
        canonical_bytes = source_bytes or json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            layouts=MappingProxyType(layouts),
            field_metadata=_FieldMetadata_Build(document, raw_records),
            sha256=hashlib.sha256(canonical_bytes).hexdigest(),
            schema_version=1,
        )

    def Layout_Get(self, record_type: int, record_version: int) -> RecordLayout | None:
        return self.layouts.get((record_type, record_version))

    def HasRecordType(self, record_type: int) -> bool:
        return any(key[0] == record_type for key in self.layouts)

    def FieldMetadata_Get(
        self,
        record_name: str,
        field_name: str,
    ) -> Mapping[str, Any]:
        return self.field_metadata.get((record_name.upper(), field_name), MappingProxyType({}))


def _FieldMetadata_Build(
    catalog_document: Mapping[str, Any],
    raw_records: list[Any],
) -> Mapping[tuple[str, str], Mapping[str, Any]]:
    contract = catalog_document.get("field_contract", {})
    if not isinstance(contract, Mapping):
        raise DecoderProfileError("decoder_field_contract_invalid")
    defaults = contract.get("defaults", {})
    rules = contract.get("semantic_rules", [])
    if not isinstance(defaults, Mapping) or not isinstance(rules, list):
        raise DecoderProfileError("decoder_field_contract_invalid")
    metadata: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            continue
        raw_name = raw_record.get("name")
        raw_fields = raw_record.get("fields", [])
        if not isinstance(raw_name, str) or not isinstance(raw_fields, list):
            continue
        record_name = raw_name.removeprefix("FLIGHT_LOG_RECORD_").upper()
        for raw_field in raw_fields:
            if not isinstance(raw_field, Mapping):
                continue
            field_name = raw_field.get("name")
            if not isinstance(field_name, str):
                continue
            values = dict(defaults)
            for raw_rule in rules:
                if not isinstance(raw_rule, Mapping):
                    raise DecoderProfileError("decoder_field_semantic_rule_invalid")
                name_matches = raw_rule.get("name") == field_name
                suffix = raw_rule.get("suffix")
                suffix_matches = isinstance(suffix, str) and field_name.endswith(suffix)
                if name_matches or suffix_matches:
                    values.update(
                        {
                            key: value
                            for key, value in raw_rule.items()
                            if key not in ("name", "suffix")
                        }
                    )
            for key in (
                "unit",
                "quantity",
                "scale",
                "offset",
                "enum",
                "bitfield",
                "timestamp",
                "validity",
                "columns",
            ):
                if key in raw_field:
                    values[key] = raw_field[key]
            metadata[(record_name, field_name)] = MappingProxyType(values)
    return MappingProxyType(metadata)
