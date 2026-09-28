"""Declarative, actual-value algorithm parameters; no algorithm dispatch."""
from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import Any

PARAMETER_SCHEMA_ID = "silverstar.algorithm-parameters/1.0"


@dataclass(frozen=True, slots=True)
class AlgorithmParameterDefinition:
    parameter_id: str
    value_type: str
    default: float | int
    unit: str
    representation: str
    minimum: float | int
    maximum: float | int
    precision: int
    step: float | int
    group: str
    order: int
    description: dict[str, str]
    display_names: dict[str, str]
    generated_symbol: str
    shared_key: str = ""
    greater_than: str = ""
    legacy_default: float | int | None = None
    lifecycle: str = "active"

    def DisplayName_Get(self, language: str) -> str:
        return self.display_names.get(language, self.display_names["en_US"])

    def Description_Get(self, language: str) -> str:
        return self.description.get(language, self.description["en_US"])

    def Value_Resolve(self, value: Any) -> float | int:
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError(f"{self.parameter_id}: expected a finite number")
        if self.value_type == "integer" and type(value) is not int:
            raise ValueError(f"{self.parameter_id}: expected an integer")
        if self.value_type == "integer" and not -(2**31) <= value < 2**31:
            raise ValueError(f"{self.parameter_id}: outside int32 range")
        if not self.minimum <= value <= self.maximum:
            raise ValueError(f"{self.parameter_id}: outside [{self.minimum}, {self.maximum}]")
        # C storage is binary32; metadata reports exactly the value the target uses.
        try:
            resolved = (struct.unpack("<f", struct.pack("<f", value))[0]
                        if self.value_type == "float" else value)
        except (OverflowError, struct.error) as error:
            raise ValueError(f"{self.parameter_id}: unrepresentable target value") from error
        if not math.isfinite(resolved):
            raise ValueError(f"{self.parameter_id}: unrepresentable target value")
        return resolved


def AlgorithmParameters_Parse(value: Any) -> tuple[AlgorithmParameterDefinition, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or set(value) != {"schema_id", "parameters"}:
        raise ValueError("algorithm_parameters requires schema_id and parameters only")
    if value["schema_id"] != PARAMETER_SCHEMA_ID or not isinstance(value["parameters"], list):
        raise ValueError("Unsupported algorithm parameter schema")
    required = {"id", "type", "default", "unit", "representation", "min", "max",
                "precision", "step", "group", "order", "description", "display_names",
                "generated_symbol"}
    definitions = []
    for entry in value["parameters"]:
        if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - required - {"greater_than", "shared_key", "legacy_default", "lifecycle"}:
            raise ValueError("Algorithm parameter has missing or unknown fields")
        if not isinstance(entry["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", entry["id"]):
            raise ValueError("Invalid algorithm parameter id")
        if entry["type"] not in ("float", "integer"):
            raise ValueError("Invalid algorithm parameter type")
        if entry["representation"] not in ("value", "sigma", "variance", "covariance_diagonal"):
            raise ValueError("Invalid parameter representation")
        if entry["group"] not in ("basic", "advanced", "gnss_integrity"):
            raise ValueError("Invalid parameter group")
        if type(entry["precision"]) is not int or not 0 <= entry["precision"] <= 9:
            raise ValueError("Invalid parameter precision")
        if type(entry["order"]) is not int or entry["order"] < 0:
            raise ValueError("Invalid parameter order")
        for field in ("min", "max", "step"):
            if (type(entry[field]) not in (int, float)
                    or not -3.402823466e38 <= entry[field] <= 3.402823466e38):
                raise ValueError("Invalid parameter numeric bound")
        if entry["step"] <= 0 or entry["min"] >= entry["max"]:
            raise ValueError("Invalid parameter range/step")
        if entry["type"] == "integer" and any(type(entry[f]) is not int for f in ("min", "max", "step")):
            raise ValueError("Integer parameter bounds must be integers")
        if entry["type"] == "integer" and (entry["precision"] != 0 or entry["min"] < -(2**31) or entry["max"] >= 2**31):
            raise ValueError("Integer parameters require int32 bounds and zero decimals")
        if not isinstance(entry["unit"], str) or not entry["unit"].strip():
            raise ValueError("Parameter unit is required")
        for field in ("description", "display_names"):
            labels = entry[field]
            if not isinstance(labels, dict) or set(labels) != {"en_US", "zh_CN"} or not all(isinstance(s, str) and s.strip() for s in labels.values()):
                raise ValueError("Parameter labels require en_US and zh_CN")
        if not isinstance(entry["generated_symbol"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry["generated_symbol"]):
            raise ValueError("Invalid parameter generated symbol")
        shared_key = entry.get("shared_key", "")
        if not isinstance(shared_key, str) or (shared_key and not re.fullmatch(r"[a-z][a-z0-9_.-]*", shared_key)):
            raise ValueError("Invalid parameter shared_key")
        greater = entry.get("greater_than", "")
        lifecycle = entry.get("lifecycle", "active")
        if lifecycle not in ("active", "legacy_read_only"):
            raise ValueError("Invalid algorithm parameter lifecycle")
        if lifecycle != "active" and shared_key:
            raise ValueError("Legacy parameters cannot own shared runtime values")
        if not isinstance(greater, str):
            raise TypeError("Invalid parameter comparison")
        definition = AlgorithmParameterDefinition(
            entry["id"], entry["type"], entry["default"], entry["unit"],
            entry["representation"], entry["min"], entry["max"], entry["precision"],
            entry["step"], entry["group"], entry["order"], entry["description"],
            entry["display_names"], entry["generated_symbol"], shared_key, greater, entry.get("legacy_default"), lifecycle)
        definition.Value_Resolve(definition.default)
        if definition.legacy_default is not None:
            definition.Value_Resolve(definition.legacy_default)
        definitions.append(definition)
    by_id = {d.parameter_id: d for d in definitions}
    if len(by_id) != len(definitions) or len({d.generated_symbol for d in definitions}) != len(definitions):
        raise ValueError("Duplicate parameter id or generated symbol")
    for definition in definitions:
        if definition.greater_than:
            other = by_id.get(definition.greater_than)
            if other is None or definition.Value_Resolve(definition.default) <= other.Value_Resolve(other.default):
                raise ValueError("Invalid parameter default comparison")
    return tuple(sorted(definitions, key=lambda d: (d.order, d.parameter_id)))
