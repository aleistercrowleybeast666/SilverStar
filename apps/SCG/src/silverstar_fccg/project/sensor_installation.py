"""Measured installation metadata; no estimator or calibration math consumes it yet."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from silverstar_fccg.project.model import ProjectModel

SENSOR_INSTALLATION_SCHEMA = "silverstar.sensor-installation/1"
# Engineering input bound, shared by file validation and the numeric editor.
SENSOR_POSITION_LIMIT_M = 1_000_000.0


@dataclass(frozen=True, slots=True)
class SensorPosition:
    x: float
    y: float
    z: float

    def Dictionary_Get(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SensorInstallationConfiguration:
    origin_description: str = ""

    def Dictionary_Get(self) -> dict[str, Any]:
        return {
            "schema": SENSOR_INSTALLATION_SCHEMA,
            "frame": "body",
            "unit": "m",
            "origin_kind": "fixed_body_structure",
            "origin_description": self.origin_description,
            "input_source": "measurement_or_cad",
        }


def SensorPosition_Parse(value: Any) -> SensorPosition:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError("position_body_m must contain exactly x, y and z")
    for coordinate in value.values():
        if (type(coordinate) not in (int, float) or
                not -SENSOR_POSITION_LIMIT_M <= coordinate <= SENSOR_POSITION_LIMIT_M or
                not math.isfinite(coordinate)):
            raise ValueError("position_body_m requires finite numeric metres within +/-1000000")
    return SensorPosition(**{axis: float(value[axis]) for axis in ("x", "y", "z")})


def SensorInstallationConfiguration_Parse(value: Any) -> SensorInstallationConfiguration:
    expected = SensorInstallationConfiguration().Dictionary_Get()
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Invalid sensor_installation fields")
    if any(value[key] != expected[key] for key in expected if key != "origin_description"):
        raise ValueError("Unsupported sensor_installation schema, frame, unit or origin kind")
    description = value["origin_description"]
    if (not isinstance(description, str) or len(description) > 512 or
            any(ord(char) < 32 or ord(char) == 127 for char in description)):
        raise ValueError("origin_description must be text without control characters (max 512)")
    return SensorInstallationConfiguration(description)


def SensorInstallationSnapshot_Get(model: ProjectModel, catalog) -> dict[str, Any]:
    """Keep instance IDs and original legacy input distinct; never infer a transform."""
    from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve

    configuration = model.sensor_installation
    if configuration is None:
        raise ValueError("sensor_installation is not configured")
    if not configuration.origin_description.strip():
        raise ValueError("Define the fixed structural origin and body X/Y datums before generation")
    if any(item.position_body_m is not None and
           catalog.Component_Get(item.plugin).component_class not in ("imu", "gnss")
           for item in model.device_instances):
        raise ValueError("Installation position requires an IMU/GNSS instance")
    legacy_id = "silverstar.algorithm.estimator.eskf15"
    legacy_keys = tuple("lever_arm_body_" + axis + "_m" for axis in ("x", "y", "z"))
    legacy_inputs = model.algorithm_parameters.get(legacy_id, {})
    resolved = next(({item["id"]: item["value"] for item in owner["parameters"]}
                     for owner in AlgorithmParameters_Resolve(model, catalog)
                     if owner["component"] == legacy_id), {})
    legacy_resolved = {key: resolved[key] for key in legacy_keys if key in resolved}
    return {
        **configuration.Dictionary_Get(),
        "axes": {"handedness": "right", "positive_z": "nose",
                 "transverse_axes": "existing body X/Y; identify physical datums in origin_description"},
        "runtime_applied": False,
        "compensation_status": "configuration_only_not_applied",
        "devices": [
            {"instance_id": item.instance_id, "plugin": item.plugin,
             "component_class": catalog.Component_Get(item.plugin).component_class,
             "position_body_m": item.position_body_m.Dictionary_Get() if item.position_body_m else None}
            for item in model.device_instances
            if catalog.Component_Get(item.plugin).component_class in ("imu", "gnss")
        ],
        "legacy_eskf15": {
            "input_values": {key: legacy_inputs[key] for key in legacy_keys if key in legacy_inputs},
            "active_global_values_m": legacy_resolved,
            "migration": "preserved_without_origin_or_instance_inference",
        },
    }


def SensorInstallationHeader_Render(model: ProjectModel) -> str:
    lines = [
        "/* AUTO-GENERATED. Measured metadata only; no runtime compensation is enabled. */",
        "#ifndef __PROJECT_SENSOR_INSTALLATION_H",
        "#define __PROJECT_SENSOR_INSTALLATION_H",
        "#define PROJECT_SENSOR_INSTALLATION_SCHEMA_VERSION 1U",
        "#define PROJECT_SENSOR_INSTALLATION_RUNTIME_APPLIED 0U",
        "/* Metres from a fixed structural origin; right-handed body axes, +Z nose. */",
    ]
    for instance in model.device_instances:
        position = instance.position_body_m
        if position is None:
            continue
        prefix = "PROJECT_SENSOR_INSTALLATION_" + instance.instance_id.upper()
        lines.append(f"#define {prefix}_RECORDED 1U")
        for axis, value in position.Dictionary_Get().items():
            lines.append(f"#define {prefix}_BODY_{axis.upper()}_M ({value!r})")
    return "\n".join([*lines, "#endif", ""])
