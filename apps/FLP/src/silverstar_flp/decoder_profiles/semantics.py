from __future__ import annotations

import hashlib
import json
import re
import string
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from silverstar_flp.core.dataset import ChannelDefinition
from silverstar_flp.core.semantic_columns import SemanticColumns_Get
from silverstar_flp.decoder_profiles.errors import DecoderProfileError

_CHANNEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_TEMPLATE_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TEMPLATE_FORMAT_PATTERN = re.compile(r"^(?:0?[1-9][0-9]*)?[dDxX]?$")


def _RecordName_Normalize(name: str) -> str:
    return name.removeprefix("FLIGHT_LOG_RECORD_").upper()


def _Integer_Parse(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise DecoderProfileError("decoder_semantics_integer_invalid")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError as exc:
            raise DecoderProfileError("decoder_semantics_integer_invalid", value) from exc
    raise DecoderProfileError("decoder_semantics_integer_invalid", str(value))


def _TemplateFields_Get(template: str) -> frozenset[str]:
    fields: set[str] = set()
    try:
        parsed = tuple(string.Formatter().parse(template))
    except ValueError as exc:
        raise DecoderProfileError("decoder_channel_template_invalid", template) from exc
    for _, field_name, format_spec, conversion in parsed:
        if field_name:
            if (
                not _TEMPLATE_FIELD_PATTERN.fullmatch(field_name)
                or conversion is not None
                or not _TEMPLATE_FORMAT_PATTERN.fullmatch(format_spec)
            ):
                raise DecoderProfileError("decoder_channel_template_invalid", template)
            fields.add(field_name)
    return frozenset(fields)


def _MetadataCollection_Normalize(value: Any, error_code: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (MappingProxyType(dict(value)),)
    if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
        return tuple(MappingProxyType(dict(item)) for item in value)
    raise DecoderProfileError(error_code)


def _FirmwareAlgorithms_Normalize(value: Any) -> tuple[FirmwareAlgorithmReference, ...]:
    if not isinstance(value, list):
        raise DecoderProfileError("decoder_algorithm_catalog_invalid")
    result: list[FirmwareAlgorithmReference] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise DecoderProfileError("decoder_algorithm_catalog_invalid")
        component_id = item
        if not component_id or component_id in seen:
            raise DecoderProfileError(
                "decoder_algorithm_catalog_duplicate",
                component_id,
            )
        seen.add(component_id)
        result.append(
            FirmwareAlgorithmReference(
                component_id=component_id,
                metadata=MappingProxyType({}),
            )
        )
    return tuple(result)


def _TimestampField_Select(
    catalog: Any,
    record_name: str,
    layout: Any,
    view: Mapping[str, Any] | None = None,
) -> str | None:
    if view is not None and "timestamp_field" in view:
        explicit = view["timestamp_field"]
        field = next((item for item in layout.fields if item.name == explicit), None)
        if not isinstance(explicit, str) or not explicit or field is None:
            raise DecoderProfileError(
                "decoder_record_view_timestamp_field_invalid", f"{record_name}:{explicit}"
            )
        metadata = catalog.FieldMetadata_Get(record_name, explicit)
        if (
            field.count != 1
            or field.data_type not in {"u32", "i32", "u64", "i64"}
            or field.scale != 1.0
            or field.offset != 0.0
            or not (metadata.get("timestamp") is True or explicit.endswith("timestamp_us"))
        ):
            raise DecoderProfileError(
                "decoder_record_view_timestamp_field_invalid", f"{record_name}:{explicit}"
            )
        return explicit
    named_fields = {
        field_layout.name
        for field_layout in layout.fields
        if field_layout.name is not None
    }
    for preferred in (
        "sample_timestamp_us",
        "timestamp_us",
        "interval_end_timestamp_us",
    ):
        if preferred in named_fields:
            return preferred
    candidates = [
        name for name in named_fields
        if catalog.FieldMetadata_Get(record_name, name).get("timestamp") is True
    ]
    # Multiple payload clocks may describe measurements inside a state snapshot.
    # None preserves the builder's record-header timestamp; never guess by name order.
    return candidates[0] if len(candidates) == 1 else None


def _ViewValidity_Get(
    raw_validity: Any,
    value_field: str,
    field_names: set[str | None],
) -> tuple[str | None, int | None]:
    if not isinstance(raw_validity, Mapping):
        return None, None
    rule = raw_validity.get(value_field)
    if rule is None:
        nested = raw_validity.get("fields", raw_validity.get("masks"))
        if isinstance(nested, Mapping):
            rule = nested.get(value_field)
    default_field = raw_validity.get(
        "validity_field",
        raw_validity.get("field", "valid_mask"),
    )
    if isinstance(rule, int) and not isinstance(rule, bool):
        return (
            (default_field, rule)
            if isinstance(default_field, str) and default_field in field_names
            else (None, None)
        )
    if isinstance(rule, Mapping):
        validity_field = rule.get(
            "validity_field",
            rule.get("field", default_field),
        )
        mask = rule.get("validity_mask", rule.get("mask"))
        if (
            isinstance(validity_field, str)
            and validity_field in field_names
            and isinstance(mask, int)
            and not isinstance(mask, bool)
            and mask >= 0
        ):
            return validity_field, mask
    return None, None


@dataclass(frozen=True, slots=True)
class FirmwareAlgorithmReference:
    component_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("firmware_algorithm_component_id_required")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


# Public name used by the package 1.1 domain model.  Keep the longer spelling as
# an implementation-compatible alias for callers introduced during development.
FirmwareAlgorithmRef = FirmwareAlgorithmReference


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    descriptor_id: int
    physical_device_id: int | None
    capability_class: str
    instance_id: str | int
    plugin_id: str
    model: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SemanticChannel:
    id_template: str
    value_field: str
    timestamp_field: str | None
    unit: str
    quantity: str
    columns: tuple[str, ...]
    validity_field: str | None
    validity_mask: int | None
    canonical_id: str | None
    canonical_when: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def FromDocument(
        cls,
        document: Mapping[str, Any],
        *,
        record_name: str,
        partition_by: tuple[str, ...],
    ) -> SemanticChannel:
        id_template = document.get("id_template")
        value_field = document.get("value_field")
        if not isinstance(id_template, str) or not id_template:
            raise DecoderProfileError("decoder_channel_id_template_invalid", record_name)
        if not isinstance(value_field, str) or not value_field:
            raise DecoderProfileError("decoder_channel_value_field_invalid", record_name)
        template_fields = _TemplateFields_Get(id_template)
        missing_partitions = [name for name in partition_by if name not in template_fields]
        if missing_partitions:
            raise DecoderProfileError(
                "decoder_channel_partition_missing_from_id",
                f"{record_name}:{','.join(missing_partitions)}",
            )
        timestamp_field = document.get("timestamp_field")
        validity_field = document.get("validity_field")
        if timestamp_field is not None and not isinstance(timestamp_field, str):
            raise DecoderProfileError("decoder_channel_timestamp_field_invalid", record_name)
        if validity_field is not None and not isinstance(validity_field, str):
            raise DecoderProfileError("decoder_channel_validity_field_invalid", record_name)
        columns = document.get("columns", ())
        if not isinstance(columns, (list, tuple)) or not all(
            isinstance(item, str) for item in columns
        ):
            raise DecoderProfileError("decoder_channel_columns_invalid", record_name)
        canonical_id = document.get("canonical_id")
        if canonical_id is not None and (
            not isinstance(canonical_id, str)
            or not _CHANNEL_ID_PATTERN.fullmatch(canonical_id)
        ):
            raise DecoderProfileError("decoder_canonical_channel_id_invalid", record_name)
        canonical_when = document.get("canonical_when", {})
        metadata = document.get("metadata", {})
        if not isinstance(canonical_when, Mapping) or not isinstance(metadata, Mapping):
            raise DecoderProfileError("decoder_channel_metadata_invalid", record_name)
        if canonical_id is not None and partition_by and not canonical_when:
            raise DecoderProfileError(
                "decoder_canonical_partition_condition_missing",
                record_name,
            )
        unit = document.get("unit", "1")
        quantity = document.get("quantity", "unknown")
        if not isinstance(unit, str) or not isinstance(quantity, str):
            raise DecoderProfileError("decoder_channel_unit_or_quantity_invalid", record_name)
        return cls(
            id_template=id_template,
            value_field=value_field,
            timestamp_field=timestamp_field,
            unit=unit,
            quantity=quantity,
            columns=tuple(columns),
            validity_field=validity_field,
            validity_mask=_Integer_Parse(document.get("validity_mask")),
            canonical_id=canonical_id,
            canonical_when=MappingProxyType(dict(canonical_when)),
            metadata=MappingProxyType(dict(metadata)),
        )


@dataclass(frozen=True, slots=True)
class RecordSemantics:
    record_name: str
    partition_by: tuple[str, ...]
    channels: tuple[SemanticChannel, ...]


@dataclass(frozen=True, slots=True)
class ProjectSemantics:
    records: Mapping[str, RecordSemantics]
    devices: Mapping[int, DeviceDescriptor]
    sha256: str
    schema_version: int
    project_name: str
    firmware_version: str
    event_catalog: tuple[Mapping[str, Any], ...]
    algorithm_catalog: tuple[FirmwareAlgorithmReference, ...]
    stream_config: tuple[Mapping[str, Any], ...]
    canonical_channels: tuple[Mapping[str, Any], ...]
    record_views: tuple[Mapping[str, Any], ...]
    raw_channel_id_templates: Mapping[str, Any]
    physical_devices: tuple[Mapping[str, Any], ...]
    raw_metadata: Mapping[str, Any]

    @classmethod
    def FromDocument(
        cls,
        document: Mapping[str, Any],
        *,
        source_bytes: bytes | None = None,
        manifest: Mapping[str, Any] | None = None,
    ) -> ProjectSemantics:
        schema_id = document.get("schema_id")
        if schema_id != "silverstar.project-semantics/1.2":
            raise DecoderProfileError(
                "decoder_project_semantics_schema_id_unsupported",
                str(schema_id),
            )
        from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareParameters_Validate

        FirmwareParameters_Validate(
            document.get("firmware_algorithm_parameters"),
            tuple(
                item.component_id
                for item in _FirmwareAlgorithms_Normalize(document.get("algorithms"))
            ),
        )
        raw_endpoints = document.get("capability_endpoints", [])
        if not isinstance(raw_endpoints, list) or not all(
            isinstance(item, Mapping) for item in raw_endpoints
        ):
            raise DecoderProfileError("decoder_capability_endpoints_invalid")
        endpoints_by_id = {
            endpoint.get("descriptor_id"): endpoint
            for endpoint in raw_endpoints
            if isinstance(endpoint.get("descriptor_id"), int)
        }
        raw_devices = document.get("device_descriptors")
        if not isinstance(raw_devices, list):
            raise DecoderProfileError("decoder_device_descriptors_invalid")
        devices: dict[int, DeviceDescriptor] = {}
        for index, raw_device in enumerate(raw_devices):
            if not isinstance(raw_device, Mapping):
                raise DecoderProfileError("decoder_device_descriptor_invalid", str(index))
            descriptor_id = _Integer_Parse(raw_device.get("descriptor_id"))
            if descriptor_id is None:
                continue
            if not 0 <= descriptor_id <= 0xFFFF:
                raise DecoderProfileError(
                    "decoder_device_descriptor_id_out_of_range",
                    str(descriptor_id),
                )
            if descriptor_id in devices:
                raise DecoderProfileError(
                    "decoder_device_descriptor_duplicate",
                    str(descriptor_id),
                )
            instance_id = raw_device.get("instance_id")
            endpoint = endpoints_by_id.get(descriptor_id, {})
            if not isinstance(instance_id, (str, int)) or isinstance(instance_id, bool):
                raise DecoderProfileError("decoder_device_instance_invalid", str(descriptor_id))
            capability_class = str(
                endpoint.get(
                    "device_class",
                    raw_device.get(
                        "capability_class",
                        raw_device.get("device_class", "unknown"),
                    ),
                )
            )
            plugin_id = str(
                endpoint.get(
                    "plugin",
                    raw_device.get("source_component", ""),
                )
            )
            model = str(
                endpoint.get(
                    "model",
                    plugin_id,
                )
            )
            capabilities = endpoint.get("capabilities", ())
            if not isinstance(capabilities, (list, tuple)) or not all(
                isinstance(item, str) for item in capabilities
            ):
                raise DecoderProfileError(
                    "decoder_capability_endpoint_capabilities_invalid",
                    str(descriptor_id),
                )
            physical_device_id = _Integer_Parse(
                endpoint.get(
                    "physical_device_id",
                    raw_device.get("physical_device_id"),
                )
            )
            if physical_device_id is not None and not 0 <= physical_device_id <= 0xFFFF:
                raise DecoderProfileError(
                    "decoder_physical_device_id_out_of_range",
                    str(physical_device_id),
                )
            devices[descriptor_id] = DeviceDescriptor(
                descriptor_id=descriptor_id,
                physical_device_id=physical_device_id,
                capability_class=capability_class,
                instance_id=instance_id,
                plugin_id=plugin_id,
                model=model,
                metadata=MappingProxyType(
                    {
                        **dict(raw_device),
                        **dict(endpoint),
                        "capabilities": tuple(capabilities),
                    }
                ),
            )

        records: dict[str, RecordSemantics] = {}

        canonical_bytes = source_bytes or json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        declared_schema_version = document.get("schema_version")
        if declared_schema_version is not None:
            parsed_schema_version = _Integer_Parse(declared_schema_version)
            if parsed_schema_version != 0x00010002:
                raise DecoderProfileError(
                    "decoder_project_semantics_schema_unsupported",
                    str(parsed_schema_version),
                )
        schema_version = 0x00010002
        event_catalog = _MetadataCollection_Normalize(
            document.get("event_catalog"),
            "decoder_event_catalog_invalid",
        )
        algorithm_catalog = _FirmwareAlgorithms_Normalize(
            document.get("algorithms"),
        )
        stream_config = _MetadataCollection_Normalize(
            document.get("logging_streams"),
            "decoder_stream_config_invalid",
        )
        canonical_channels = _MetadataCollection_Normalize(
            document.get("canonical_channels"),
            "decoder_canonical_channels_invalid",
        )
        record_views = _MetadataCollection_Normalize(
            document.get("record_views"),
            "decoder_record_views_invalid",
        )
        raw_templates = document.get("raw_channel_id_templates", {})
        if not isinstance(raw_templates, Mapping):
            raise DecoderProfileError("decoder_raw_channel_templates_invalid")
        physical_devices = _MetadataCollection_Normalize(
            document.get("physical_devices"),
            "decoder_physical_devices_invalid",
        )
        project_name = document.get("project")
        firmware_version = document.get("firmware_version")
        if not isinstance(project_name, str) or not project_name:
            raise DecoderProfileError("decoder_project_name_invalid")
        if not isinstance(firmware_version, str) or not firmware_version:
            raise DecoderProfileError("decoder_firmware_version_invalid")
        return cls(
            records=MappingProxyType(records),
            devices=MappingProxyType(devices),
            sha256=hashlib.sha256(canonical_bytes).hexdigest(),
            schema_version=schema_version,
            project_name=project_name,
            firmware_version=firmware_version,
            event_catalog=event_catalog,
            algorithm_catalog=algorithm_catalog,
            stream_config=stream_config,
            canonical_channels=canonical_channels,
            record_views=record_views,
            raw_channel_id_templates=MappingProxyType(dict(raw_templates)),
            physical_devices=physical_devices,
            raw_metadata=MappingProxyType(dict(document)),
        )

    @property
    def firmware_algorithm_ids(self) -> tuple[str, ...]:
        return tuple(item.component_id for item in self.algorithm_catalog)

    def Catalog_Bind(self, catalog: Any) -> ProjectSemantics:
        """Derive field channels from FCCG record_views when no explicit map exists."""
        if self.records or not self.record_views:
            return self
        layouts_by_name: dict[str, list[Any]] = defaultdict(list)
        for layout in catalog.layouts.values():
            layouts_by_name[layout.name.upper()].append(layout)
        bound_records: dict[str, RecordSemantics] = {}
        for view in self.record_views:
            raw_record_name = view.get("record")
            if not isinstance(raw_record_name, str):
                raise DecoderProfileError("decoder_record_view_name_invalid")
            record_name = _RecordName_Normalize(raw_record_name)
            layouts = layouts_by_name.get(record_name)
            if not layouts:
                raise DecoderProfileError(
                    "decoder_record_view_catalog_missing",
                    record_name,
                )
            partition_value = view.get("partition_by", ())
            if isinstance(partition_value, str):
                partition_value = [partition_value]
            if not isinstance(partition_value, (list, tuple)) or not all(
                isinstance(item, str) and item for item in partition_value
            ):
                raise DecoderProfileError(
                    "decoder_record_view_partition_invalid",
                    record_name,
                )
            partition_by = tuple(partition_value)
            first_layout = layouts[0]
            field_names = {
                field_layout.name
                for field_layout in first_layout.fields
                if field_layout.name is not None
            }
            base_template = self.raw_channel_id_templates.get(record_name)
            if base_template is None:
                base_template = self.raw_channel_id_templates.get("default")
            if (
                not partition_by
                or not isinstance(base_template, str)
                or not base_template
            ):
                base_template = "{record}"
            if not isinstance(base_template, str):
                raise DecoderProfileError(
                    "decoder_raw_channel_template_invalid",
                    record_name,
                )
            template_fields = _TemplateFields_Get(base_template)
            available_template_fields = {
                "record",
                "record_name",
                *field_names,
            }
            if "source_descriptor_id" in field_names:
                available_template_fields.update(
                    {
                        "descriptor_id",
                        "physical_device_id",
                        "capability_class",
                        "plugin_id",
                        "model",
                    }
                )
            if not template_fields.issubset(available_template_fields):
                base_template = "{record}"
                template_fields = _TemplateFields_Get(base_template)
            for partition in partition_by:
                if partition not in template_fields:
                    base_template += f":{{{partition}}}"
            selected_columns = view.get("columns")
            if isinstance(selected_columns, list) and all(
                isinstance(item, str) for item in selected_columns
            ):
                selected_fields = set(selected_columns)
            else:
                selected_fields = field_names
            timestamp_field = _TimestampField_Select(
                catalog,
                record_name,
                first_layout,
                view,
            )
            if "timestamp_field" in view:
                for layout in layouts[1:]:
                    _TimestampField_Select(catalog, record_name, layout, view)
            raw_validity = view.get("validity", {})
            channels: list[SemanticChannel] = []
            for field_layout in first_layout.fields:
                field_name = field_layout.name
                if (
                    field_name is None
                    or field_name not in selected_fields
                    or field_name in partition_by
                    or field_name == timestamp_field
                    or field_name == "reserved"
                ):
                    continue
                field_metadata = dict(
                    catalog.FieldMetadata_Get(record_name, field_name)
                )
                unit = field_metadata.get("unit", "1")
                quantity = field_metadata.get("quantity", "dimensionless")
                if not isinstance(unit, str):
                    unit = "1"
                if not isinstance(quantity, str):
                    quantity = "dimensionless"
                columns = field_metadata.get("columns")
                if not isinstance(columns, list) or len(columns) != field_layout.count:
                    columns = list(SemanticColumns_Get(
                        record_name, field_name, field_layout.count,
                    ))
                validity_field, validity_mask = _ViewValidity_Get(
                    raw_validity,
                    field_name,
                    field_names,
                )
                channel_document = {
                    "id_template": f"{base_template}.{field_name}",
                    "value_field": field_name,
                    "timestamp_field": timestamp_field,
                    "unit": unit,
                    "quantity": quantity,
                    "columns": columns,
                    "validity_field": validity_field,
                    "validity_mask": validity_mask,
                    "metadata": {
                        **field_metadata,
                        "record_type": first_layout.record_type,
                        "record_version": first_layout.record_version,
                        "record_view": dict(view),
                    },
                }
                channels.append(
                    SemanticChannel.FromDocument(
                        channel_document,
                        record_name=record_name,
                        partition_by=partition_by,
                    )
                )
            bound_records[record_name] = RecordSemantics(
                record_name=record_name,
                partition_by=partition_by,
                channels=tuple(channels),
            )
        return replace(self, records=MappingProxyType(bound_records))

    def ChannelDefinitions_Get(
        self,
        record_name: str,
        payload: Mapping[str, Any],
    ) -> tuple[ChannelDefinition, ...]:
        semantics = self.records.get(_RecordName_Normalize(record_name))
        if semantics is None:
            return ()
        context = dict(payload)
        context.setdefault("record", semantics.record_name)
        context.setdefault("record_name", semantics.record_name)
        descriptor: DeviceDescriptor | None = None
        descriptor_value = payload.get("source_descriptor_id")
        descriptor_id = _Integer_Parse(descriptor_value)
        if descriptor_id is not None:
            descriptor = self.devices.get(descriptor_id)
        if descriptor is not None:
            payload_instance = payload.get("instance_id")
            if (
                payload_instance is not None
                and payload_instance != descriptor.instance_id
            ):
                raise DecoderProfileError(
                    "decoder_device_instance_mismatch",
                    f"descriptor={descriptor.descriptor_id}",
                )
            descriptor_context = {
                "descriptor_id": descriptor.descriptor_id,
                "source_descriptor_id": descriptor.descriptor_id,
                "physical_device_id": descriptor.physical_device_id,
                "capability_class": descriptor.capability_class,
                "instance_id": descriptor.instance_id,
                "plugin_id": descriptor.plugin_id,
                "model": descriptor.model,
            }
            for key, value in descriptor_context.items():
                context.setdefault(key, value)
        for partition_field in semantics.partition_by:
            if partition_field not in context:
                raise DecoderProfileError(
                    "decoder_partition_field_missing",
                    f"{semantics.record_name}:{partition_field}",
                )

        definitions: list[ChannelDefinition] = []
        for channel in semantics.channels:
            if channel.value_field not in payload:
                raise DecoderProfileError(
                    "decoder_channel_value_missing",
                    f"{semantics.record_name}:{channel.value_field}",
                )
            try:
                channel_id = channel.id_template.format_map(context)
            except (KeyError, ValueError) as exc:
                raise DecoderProfileError(
                    "decoder_channel_template_failed",
                    f"{semantics.record_name}:{channel.id_template}",
                ) from exc
            if not _CHANNEL_ID_PATTERN.fullmatch(channel_id):
                raise DecoderProfileError("decoder_channel_id_invalid", channel_id)
            metadata = {
                **dict(channel.metadata),
                "record_name": semantics.record_name,
                "partition_by": semantics.partition_by,
            }
            if descriptor is not None:
                canonical_channel_ids = tuple(
                    str(item["channel_id"])
                    for item in self.canonical_channels
                    if isinstance(item.get("channel_id"), str)
                    and isinstance(item.get("endpoint_descriptor_ids"), list)
                    and descriptor.descriptor_id in item["endpoint_descriptor_ids"]
                )
                metadata.update(
                    {
                        "descriptor_id": descriptor.descriptor_id,
                        "physical_device_id": descriptor.physical_device_id,
                        "capability_class": descriptor.capability_class,
                        "instance_id": descriptor.instance_id,
                        "plugin_id": descriptor.plugin_id,
                        "model": descriptor.model,
                        "physical_device_instance": descriptor.metadata.get(
                            "physical_device_instance",
                            descriptor.metadata.get("source_instance_id"),
                        ),
                        "capabilities": tuple(
                            descriptor.metadata.get("capabilities", ())
                        ),
                        "canonical_channel_ids": canonical_channel_ids,
                    }
                )
            definitions.append(
                ChannelDefinition(
                    channel_id=channel_id,
                    field_name=channel.value_field,
                    unit=channel.unit,
                    quantity=channel.quantity,
                    columns=channel.columns,
                    timestamp_field=channel.timestamp_field,
                    validity_field=channel.validity_field,
                    validity_mask=channel.validity_mask,
                    metadata=metadata,
                )
            )
            canonical_matches = all(
                context.get(key) == expected
                for key, expected in channel.canonical_when.items()
            )
            if channel.canonical_id is not None and canonical_matches:
                definitions.append(
                    ChannelDefinition(
                        channel_id=channel.canonical_id,
                        field_name=channel.value_field,
                        unit=channel.unit,
                        quantity=channel.quantity,
                        columns=channel.columns,
                        timestamp_field=channel.timestamp_field,
                        validity_field=channel.validity_field,
                        validity_mask=channel.validity_mask,
                        metadata={**metadata, "canonical": True},
                    )
                )
        return tuple(definitions)
