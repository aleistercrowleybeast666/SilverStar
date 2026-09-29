from __future__ import annotations

import struct
from typing import Any

from silverstar_fccg.plugins.algorithm_parameters import PARAMETER_SCHEMA_ID
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import PluginManifest
from silverstar_fccg.project.model import ProjectModel


def AlgorithmParameterOwners_Get(model: ProjectModel, catalog: PluginCatalog) -> tuple[PluginManifest, ...]:
    owners = (catalog.Component_Get(component) for component in model.ComponentIds_Get())
    return tuple(sorted((owner for owner in owners if owner.algorithm_parameters), key=lambda owner: (
        owner.selection is None,
        owner.selection.ui_order if owner.selection is not None else 0,
        owner.component_id,
    )))


def AlgorithmParameterSharedGroups_Get(owners: tuple[PluginManifest, ...]) -> dict[str, tuple[tuple[PluginManifest, Any], ...]]:
    groups: dict[str, list[tuple[PluginManifest, Any]]] = {}
    for owner in owners:
        for parameter in owner.algorithm_parameters:
            if parameter.shared_key:
                groups.setdefault(parameter.shared_key, []).append((owner, parameter))
    return {key: tuple(value) for key, value in sorted(groups.items())}


def AlgorithmParameters_Reconcile(model: ProjectModel, catalog: PluginCatalog) -> None:
    owners = AlgorithmParameterOwners_Get(model, catalog)
    existing_shared: dict[str, float | int] = {}
    for owner in owners:
        old_values = model.algorithm_parameters.get(owner.component_id, {})
        for parameter in owner.algorithm_parameters:
            if parameter.shared_key and parameter.parameter_id in old_values:
                existing_shared.setdefault(parameter.shared_key, old_values[parameter.parameter_id])
    # Removed algorithms are pruned. Unknown fields within a retained algorithm
    # remain visible to validation; never silently discard stale configuration.
    model.algorithm_parameters = {
        owner.component_id: {
            **{p.parameter_id: existing_shared.get(p.shared_key, p.legacy_default if owner.component_id in model.algorithm_parameters and p.legacy_default is not None else p.default) for p in owner.algorithm_parameters},
            **model.algorithm_parameters.get(owner.component_id, {}),
        } for owner in owners
    }


def AlgorithmParameters_Resolve(model: ProjectModel, catalog: PluginCatalog) -> list[dict[str, Any]]:
    owners = AlgorithmParameterOwners_Get(model, catalog)
    if set(model.algorithm_parameters) != {m.component_id for m in owners}:
        raise ValueError("Algorithm parameter owners are missing or stale")
    symbols: set[str] = set()
    shared_values: dict[str, float | int] = {}
    shared_contracts: dict[str, tuple[object, ...]] = {}
    result = []
    for owner in owners:
        definitions = owner.algorithm_parameters
        values = model.algorithm_parameters[owner.component_id]
        if set(values) != {p.parameter_id for p in definitions}:
            raise ValueError(f"{owner.component_id}: missing or unknown algorithm parameter")
        resolved = {p.parameter_id: p.Value_Resolve(values[p.parameter_id]) for p in definitions}
        parameters = []
        for parameter in definitions:
            if parameter.shared_key:
                contract = (parameter.value_type, parameter.default, parameter.unit,
                            parameter.representation, parameter.minimum, parameter.maximum,
                            parameter.precision, parameter.step)
                if (parameter.shared_key in shared_contracts
                        and contract != shared_contracts[parameter.shared_key]):
                    raise ValueError(f"Incompatible shared parameter declaration: {parameter.shared_key}")
                shared_contracts[parameter.shared_key] = contract
                raw_value = values[parameter.parameter_id]
                if parameter.shared_key in shared_values and raw_value != shared_values[parameter.shared_key]:
                    raise ValueError(f"Shared parameter mismatch: {parameter.shared_key}")
                shared_values[parameter.shared_key] = raw_value
            if parameter.generated_symbol in symbols:
                raise ValueError("Conflicting algorithm parameter generated symbols")
            symbols.add(parameter.generated_symbol)
            if parameter.greater_than and resolved[parameter.parameter_id] <= resolved[parameter.greater_than]:
                raise ValueError(f"{parameter.parameter_id} must exceed {parameter.greater_than} in target precision")
            parameters.append({"id": parameter.parameter_id, "value": resolved[parameter.parameter_id],
                               "unit": parameter.unit, "representation": parameter.representation,
                               "storage_type": "float32" if parameter.value_type == "float" else "int32",
                               "description": parameter.description["en_US"]})
        result.append({"component": owner.component_id, "schema_id": PARAMETER_SCHEMA_ID,
                       "manifest_sha256": owner.ManifestSha256_Get(), "parameters": parameters})
    return result


def AlgorithmParametersHeader_Render(model: ProjectModel, catalog: PluginCatalog) -> str:
    resolved = {r["component"]: {p["id"]: p["value"] for p in r["parameters"]}
                for r in AlgorithmParameters_Resolve(model, catalog)}
    rows = ["#ifndef __PROJECT_ALGORITHM_PARAMETERS_H", "#define __PROJECT_ALGORITHM_PARAMETERS_H",
            "", "/* Generated actual values. Binary32 constants; no runtime parsing. */"]
    for owner in AlgorithmParameterOwners_Get(model, catalog):
        for parameter in owner.algorithm_parameters:
            value = resolved[owner.component_id][parameter.parameter_id]
            literal = f"{value:.9e}f" if parameter.value_type == "float" else str(value)
            # Existing override convention is retained for explicit Host fixtures.
            rows.extend((f"#ifndef {parameter.generated_symbol}",
                         f"#define {parameter.generated_symbol} {literal}", "#endif"))
    return "\n".join((*rows, "", "#endif /* __PROJECT_ALGORITHM_PARAMETERS_H */", ""))


def _ParameterKeyHash_Get(key: str) -> int:
    value = 0x811C9DC5
    for byte in key.encode("utf-8"):
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def ProjectMissionParametersSource_Render(
    model: ProjectModel, catalog: PluginCatalog
) -> str:
    entries: list[tuple[int, int, str]] = []
    hashes: set[int] = set()
    for owner in AlgorithmParameters_Resolve(model, catalog):
        for parameter in owner["parameters"]:
            key_hash = _ParameterKeyHash_Get(
                f'{owner["component"]}/{parameter["id"]}'
            )
            if key_hash in hashes:
                raise ValueError("Mission parameter key hash collision")
            hashes.add(key_hash)
            if parameter["storage_type"] == "float32":
                value_bits = struct.unpack("<I", struct.pack("<f", parameter["value"]))[0]
                kind = "SystemProjectParameterKind_Float32"
            else:
                value_bits = int(parameter["value"]) & 0xFFFFFFFF
                kind = "SystemProjectParameterKind_Int32"
            entries.append((key_hash, value_bits, kind))
    if len(entries) > 96:
        raise ValueError("Mission parameter snapshot exceeds the static 96-entry bound")
    rows = [
        '#include "system_project_parameters_if.h"',
        "#include <stddef.h>",
        '#include "silverstar_assert.h"',
        "",
        "/* Generated from the selected manifest parameters and their actual values. */",
        f"#define PROJECT_MISSION_PARAMETER_COUNT {len(entries)}U",
        "static const SystemProjectParameter s_parameters[] =",
        "{",
    ]
    for key_hash, value_bits, kind in entries:
        rows.append(f"    {{0x{key_hash:08X}UL, 0x{value_bits:08X}UL, {kind}}},")
    if not entries:
        rows.append("    {0U, 0U, SystemProjectParameterKind_Int32},")
    rows.extend((
        "};",
        "",
        "uint16_t SystemProjectParameter_CountGet(void)",
        "{ return PROJECT_MISSION_PARAMETER_COUNT; }",
        "",
        "SystemProjectParameterResult SystemProjectParameter_Get(",
        "    uint16_t index, SystemProjectParameter *parameter)",
        "{",
        "    if (parameter == NULL)",
        "    { return SystemProjectParameterResult_InvalidArgument; }",
        "    if (index >= PROJECT_MISSION_PARAMETER_COUNT)",
        "    { return SystemProjectParameterResult_NotFound; }",
        "    SILVERSTAR_ASSERT_OBJECT(parameter, SystemProjectParameter,",
        "        SILVERSTAR_ASSERT_MODULE_GENERATED);",
        "    *parameter = s_parameters[index];",
        "    return SystemProjectParameterResult_Ok;",
        "}",
        "",
    ))
    return "\n".join(rows)
