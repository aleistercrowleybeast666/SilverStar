"""Strict data-only FCCG resolved-parameter contract; no executable plugin loading."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from silverstar_flp.decoder_profiles.errors import DecoderProfileError

PARAMETER_SCHEMA_ID = "silverstar.algorithm-parameters/1.0"


def FirmwareParameters_Validate(value: Any, members: tuple[str, ...]) -> None:
    if not isinstance(value, list):
        raise DecoderProfileError("firmware_parameter_sets_invalid")
    components = set()
    representations = {}
    for group in value:
        if not isinstance(group, Mapping) or set(group) != {
            "component",
            "schema_id",
            "manifest_sha256",
            "parameters",
        }:
            raise DecoderProfileError("firmware_parameter_set_invalid")
        component = group["component"]
        if not isinstance(component, str) or component not in members or component in components:
            raise DecoderProfileError("firmware_parameter_owner_invalid")
        components.add(component)
        if group["schema_id"] != PARAMETER_SCHEMA_ID:
            raise DecoderProfileError("firmware_parameter_schema_unsupported")
        digest = group["manifest_sha256"]
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise DecoderProfileError("firmware_parameter_manifest_invalid")
        if not isinstance(group["parameters"], list):
            raise DecoderProfileError("firmware_parameters_invalid")
        seen = set()
        for item in group["parameters"]:
            if not isinstance(item, Mapping) or set(item) != {
                "id",
                "value",
                "unit",
                "representation",
                "storage_type",
                "description",
            }:
                raise DecoderProfileError("firmware_parameter_invalid")
            name = item["id"]
            if (
                not isinstance(name, str)
                or not re.fullmatch("[a-z][a-z0-9_]*", name)
                or name in seen
            ):
                raise DecoderProfileError("firmware_parameter_id_invalid")
            seen.add(name)
            number = item["value"]
            storage = item["storage_type"]
            if (
                type(number) not in (int, float)
                or not math.isfinite(number)
                or storage not in ("float32", "int32")
                or (
                    storage == "int32"
                    and (type(number) is not int or not -(2**31) <= number < 2**31)
                )
                or (storage == "float32" and abs(number) > 3.4028234663852886e38)
            ):
                raise DecoderProfileError("firmware_parameter_value_invalid", name)
            representation = item["representation"]
            if representation not in ("value", "sigma", "variance", "covariance_diagonal"):
                raise DecoderProfileError("firmware_parameter_representation_invalid", name)
            if name in representations and representations[name] != representation:
                raise DecoderProfileError("firmware_parameter_representation_conflict", name)
            representations[name] = representation
            if any(
                not isinstance(item[field], str) or not item[field].strip()
                for field in ("unit", "description")
            ):
                raise DecoderProfileError("firmware_parameter_metadata_invalid", name)


def FirmwareParameters_CheckPlugins(value: Any, *, integrity_revision: int = 0) -> None:
    # Only already trusted builtin algorithm schemas are inspected. Membership never
    # instantiates executable components named by the package.
    from silverstar_flp.plugins.registry import builtin_registry

    registry = builtin_registry()
    for plugin in registry.algorithms:
        tunables = {p.parameter_id for p in plugin.metadata.parameter_schema}
        specs = {p.parameter_id: p for p in (*plugin.metadata.parameter_schema,
                                           *plugin.metadata.firmware_only_parameter_schema)}
        for group in value:
            if group["component"] not in plugin.metadata.firmware_component_ids:
                continue
            try:
                identifiers = {item["id"] for item in group["parameters"]}
                if plugin.metadata.plugin_id == "silverstar.algorithm.kf6":
                    integrity_ids = {
                        name for name in specs if name.startswith("gnss_integrity_")
                    }
                    present = identifiers & integrity_ids
                    if integrity_revision == 1:
                        raise ValueError("gnss_integrity_revision_1_legacy_candidate_unsupported")
                    if integrity_revision in (2, 3) and present != integrity_ids:
                        raise ValueError("gnss_integrity_parameters_incomplete")
                for item in group["parameters"]:
                    name = item["id"]
                    if integrity_revision == 0 and name.startswith("gnss_integrity_"):
                        continue
                    if name not in specs:
                        raise ValueError(f"parameter_unknown:{name}")
                    spec = specs[name]
                    if item["unit"] != spec.unit or item["representation"] != spec.representation:
                        raise ValueError(f"parameter_contract_mismatch:{name}")
                    expected_storage = "float32" if spec.kind == "float" else "int32"
                    if item["storage_type"] != expected_storage:
                        raise ValueError(f"parameter_storage_type_mismatch:{name}")
                    spec.Value_Validate(item["value"])
                plugin.metadata.Parameters_Validate(
                    {p["id"]: p["value"] for p in group["parameters"]
                     if p["id"] in tunables
                     and (integrity_revision != 0 or not p["id"].startswith("gnss_integrity_"))},
                    complete=False
                )
            except ValueError as exc:
                raise DecoderProfileError("firmware_parameter_contract_invalid", str(exc)) from exc


def FirmwareMechanizationAggregation_Get(dataset: Any) -> int | None:
    """Optional additive field in parameter schema1.0; old packages stay unchanged."""
    context = getattr(dataset, "semantic_context", None)
    if context is None:
        return None
    group = context.FirmwareParameters_Get("silverstar.algorithm.ins.coning2_sculling2")
    item = group.get("mechanization_aggregation") if group is not None else None
    return item["value"] if item is not None else None


def FirmwareMechanizationRecords_Validate(dataset: Any) -> None:
    declared = FirmwareMechanizationAggregation_Get(dataset)
    if declared is None:
        return  # Legacy packages use their original recorded configuration contract.
    header = getattr(dataset, "header", {})
    if "mechanization_subsample_count" in header and header["mechanization_subsample_count"] != declared:
        raise DecoderProfileError("firmware_mechanization_configuration_mismatch",
                                  f"header:declared={declared}:recorded={header['mechanization_subsample_count']}")
    for name, field in (("SYSTEM_CONFIG", "mechanization_subsample_count"),
                        ("INERTIAL_INCREMENT", "subsample_count")):
        for record in dataset.Records_Get(name):
            if field in record.payload and record.payload[field] != declared:
                raise DecoderProfileError("firmware_mechanization_configuration_mismatch",
                                          f"{name}:{field}:declared={declared}:recorded={record.payload[field]}")
