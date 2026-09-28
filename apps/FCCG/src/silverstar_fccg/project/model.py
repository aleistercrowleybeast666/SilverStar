from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from silverstar_fccg.app.version import (
    SILVERSTAR_BUILD_ID,
    SILVERSTAR_CORE_COMPONENT_ID,
    SILVERSTAR_PLATFORM_VERSION,
)
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.errors import FccgError


PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,79}$")
PROJECT_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
BUILD_TARGET_PROFILE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
COMPONENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
CONTAINER_PLUGIN_ID_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$"
)
SELECTION_SLOT_PATTERN = COMPONENT_ID_PATTERN
SELECTION_OPTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
FIRMWARE_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][0-9A-Za-z.-]+)?$"
)
LOG_RECORD_PATTERN = re.compile(r"^FLIGHT_LOG_RECORD_[A-Z0-9_]+$")
RESOURCE_KEY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*:[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
DEVICE_INSTANCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TOOLCHAIN_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_.+-]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RELATIVE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9_./+@ -]+$")

PROJECT_FORMAT_VERSION = 12
PROTOCOL_CATEGORIES = ("telemetry", "maintenance", "logging")
DEFAULT_PROTOCOL_PROFILES = {
    "telemetry": "air.m0",
    "maintenance": "maintenance.serial.0_0",
    "logging": "flight_log.0_0",
}
DEFAULT_PROTOCOL_COMPONENTS = {
    "telemetry": "silverstar.protocol.telemetry.air_m0",
    "maintenance": "silverstar.protocol.maintenance.serial_0_0",
    "logging": "silverstar.protocol.logging.sslog_0_0",
}
LEGACY_PROTOCOL_PROFILE_IDS = {
    "air.compact.v0": "air.m0",
    "maintenance.v0_0": "maintenance.serial.0_0",
    "sslog0": "flight_log.0_0",
}
DEFAULT_MODE_PARAMETERS = {
    "deployment": {
        "ApogeeVerticalVelocity": {
            "vertical_velocity_threshold": -2.0,
        },
        "Tilt": {
            "tilt_threshold": 45.0,
        },
        "Delay": {
            "delay": 60.0,
        },
    }
}
HARDWARE_MODES = frozenset({"unselected", "board_plugin", "custom"})
BOARD_SOURCE_KINDS = frozenset(
    {"unselected", "verified_builtin", "manual_import", "third_party"}
)


class ProjectModelError(FccgError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    name: str
    firmware_version: str = SILVERSTAR_PLATFORM_VERSION
    build_target: str = SILVERSTAR_BUILD_ID


@dataclass(frozen=True, slots=True)
class DeviceInstance:
    instance_id: str
    plugin: str


@dataclass(frozen=True, slots=True)
class BuildOptions:
    target_profile: str = ""
    make_command: str = "mingw32-make"
    toolchain_prefix: str = "arm-none-eabi-"
    gcc_path: str = ""
    flash_command: str = ""
    eide_mode: str = "native"
    tool_paths: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LogStreamConfig:
    record: str
    enabled: bool
    policy: str
    decimation: int = 1
    period_us: int = 0


@dataclass(frozen=True, slots=True)
class LogDecoderProfileReference:
    relative_path: str = ""
    package_schema: str = ""
    container_plugin_id: str = ""
    generation_profile_sha256: str = ""
    package_sha256: str = ""


@dataclass(frozen=True, slots=True)
class ProtocolSelection:
    component: str
    version: str
    profile: str
    manifest_sha256: str = ""


@dataclass(frozen=True, slots=True)
class HardwareResource:
    resource_id: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HardwareConfiguration:
    mode: str = "unselected"
    source_kind: str = "unselected"
    provider: str = ""
    snapshot_id: str = ""
    ioc_file: str = ""
    mcu: str = ""
    platform_component: str = ""
    platform_version: str = ""
    platform_manifest_sha256: str = ""
    cubemx_version: str = ""
    firmware_package: str = ""
    hal_cmsis_source_policy: str = ""
    i2c_external_pullup_confirmations: dict[str, dict[str, str]] = field(
        default_factory=dict
    )
    capabilities: tuple[str, ...] = ()
    inventory: dict[str, Any] = field(default_factory=dict)
    resources: tuple[HardwareResource, ...] = ()
    build_sources: tuple[str, ...] = ()
    asm_sources: tuple[str, ...] = ()
    include_dirs: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()
    linker_script: str = ""
    source_digest: str = ""
    source_label: str = ""
    risk_acknowledged: bool = False
    assignment_fingerprint: str = ""


@dataclass(slots=True)
class ProjectModel:
    identity: ProjectIdentity
    core: str
    mcu: str
    board: str
    os: str
    device_instances: list[DeviceInstance] = field(default_factory=list)
    base_components: list[str] = field(default_factory=list)
    strategies: dict[str, str | None] = field(default_factory=dict)
    modes: dict[str, list[str]] = field(default_factory=dict)
    algorithm_parameters: dict[str, dict[str, float | int]] = field(default_factory=dict)
    mode_parameters: dict[str, dict[str, dict[str, float | int]]] = field(
        default_factory=lambda: deepcopy(DEFAULT_MODE_PARAMETERS)
    )
    protocols: dict[str, ProtocolSelection | None] = field(
        default_factory=lambda: {
            category: None for category in PROTOCOL_CATEGORIES
        }
    )
    development_environment: str = ""
    hardware: HardwareConfiguration = field(default_factory=HardwareConfiguration)
    resource_assignments: dict[str, str] = field(default_factory=dict)
    capability_source_overrides: dict[str, str] = field(default_factory=dict)
    logging_streams: list[LogStreamConfig] = field(default_factory=list)
    log_decoder_profile: LogDecoderProfileReference = field(
        default_factory=LogDecoderProfileReference
    )
    build: BuildOptions = field(default_factory=BuildOptions)
    generated_glue: list[str] = field(
        default_factory=lambda: [
            "project_bindings",
            "project_capability_routes",
            "project_device_instances",
            "platform_resources",
            "project_resources",
            "project_storage_binding",
            "project_log_config",
            "project_metadata",
            "project_flight_config",
            "project_algorithm_parameters",
            "project_log_decoder_profile",
            "project_sources",
        ]
    )
    component_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    reference_provenance: dict[str, Any] = field(default_factory=dict)
    format_version: int = PROJECT_FORMAT_VERSION

    def ComponentIds_Get(self) -> tuple[str, ...]:
        ordered = [self.core, self.mcu, self.board, self.os]
        ordered.extend(self.DevicePluginIds_Get())
        ordered.extend(self.base_components)
        ordered.extend(
            component_id
            for _slot, component_id in sorted(self.strategies.items())
            if component_id is not None
        )
        ordered.extend(
            selection.component
            for _category, selection in sorted(self.protocols.items())
            if selection is not None
        )
        ordered.append(self.development_environment)
        if self.hardware.mode == "custom":
            ordered.append(self.hardware.provider)
        return tuple(dict.fromkeys(component_id for component_id in ordered if component_id))

    def DevicePluginIds_Get(self) -> tuple[str, ...]:
        return tuple(instance.plugin for instance in self.device_instances)

    def ProtocolComponentIds_Get(self) -> tuple[str, ...]:
        return tuple(
            selection.component
            for _category, selection in sorted(self.protocols.items())
            if selection is not None
        )

    def ProtocolProfiles_Get(self) -> dict[str, str]:
        return {
            category: selection.profile
            for category, selection in self.protocols.items()
            if selection is not None
        }

    def DeviceInstance_Get(self, instance_id: str) -> DeviceInstance | None:
        for instance in self.device_instances:
            if instance.instance_id == instance_id:
                return instance
        return None

    def Dictionary_Get(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "project": {
                "name": self.identity.name,
                "firmware_version": self.identity.firmware_version,
                "build_target": self.identity.build_target,
            },
            "components": {
                "core": self.core,
                "mcu": self.mcu,
                "board": self.board,
                "os": self.os,
                "devices": [
                    {
                        "instance_id": instance.instance_id,
                        "plugin": instance.plugin,
                    }
                    for instance in self.device_instances
                ],
                "base": list(self.base_components),
                "strategies": dict(sorted(self.strategies.items())),
                "development_environment": self.development_environment,
            },
            "modes": {
                slot: list(selection)
                for slot, selection in sorted(self.modes.items())
            },
            "algorithm_parameters": deepcopy(self.algorithm_parameters),
            "mode_parameters": {
                slot: {
                    option: dict(sorted(parameters.items()))
                    for option, parameters in sorted(options.items())
                }
                for slot, options in sorted(self.mode_parameters.items())
            },
            "protocols": {
                category: (
                    {
                        "component": selection.component,
                        "version": selection.version,
                        "profile": selection.profile,
                        "manifest_sha256": selection.manifest_sha256,
                    }
                    if selection is not None
                    else None
                )
                for category, selection in sorted(self.protocols.items())
            },
            "hardware": {
                "mode": self.hardware.mode,
                "source_kind": self.hardware.source_kind,
                "provider": self.hardware.provider,
                "snapshot_id": self.hardware.snapshot_id,
                "ioc_file": self.hardware.ioc_file,
                "mcu": self.hardware.mcu,
                "platform_component": self.hardware.platform_component,
                "platform_version": self.hardware.platform_version,
                "platform_manifest_sha256": self.hardware.platform_manifest_sha256,
                "cubemx_version": self.hardware.cubemx_version,
                "firmware_package": self.hardware.firmware_package,
                "hal_cmsis_source_policy": self.hardware.hal_cmsis_source_policy,
                "i2c_external_pullup_confirmations": {
                    resource_id: dict(sorted(binding.items()))
                    for resource_id, binding in sorted(
                        self.hardware.i2c_external_pullup_confirmations.items()
                    )
                },
                "capabilities": list(self.hardware.capabilities),
                "inventory": self.hardware.inventory,
                "resources": [
                    {
                        "id": resource.resource_id,
                        "kind": resource.kind,
                        "metadata": resource.metadata,
                    }
                    for resource in self.hardware.resources
                ],
                "build_sources": list(self.hardware.build_sources),
                "asm_sources": list(self.hardware.asm_sources),
                "include_dirs": list(self.hardware.include_dirs),
                "defines": list(self.hardware.defines),
                "linker_script": self.hardware.linker_script,
                "source_digest": self.hardware.source_digest,
                "source_label": self.hardware.source_label,
                "risk_acknowledged": self.hardware.risk_acknowledged,
                "assignment_fingerprint": self.hardware.assignment_fingerprint,
            },
            "resources": dict(sorted(self.resource_assignments.items())),
            "capability_sources": dict(
                sorted(self.capability_source_overrides.items())
            ),
            "logging": {
                "streams": [
                    {
                        "record": stream.record,
                        "enabled": stream.enabled,
                        "policy": stream.policy,
                        "decimation": stream.decimation,
                        "period_us": stream.period_us,
                    }
                    for stream in self.logging_streams
                ]
            },
            "log_decoder_profile": {
                "relative_path": self.log_decoder_profile.relative_path,
                "package_schema": self.log_decoder_profile.package_schema,
                "container_plugin_id": (
                    self.log_decoder_profile.container_plugin_id
                ),
                "generation_profile_sha256": (
                    self.log_decoder_profile.generation_profile_sha256
                ),
                "package_sha256": self.log_decoder_profile.package_sha256,
            },
            "build": {
                "target_profile": self.build.target_profile,
                "make_command": self.build.make_command,
                "toolchain_prefix": self.build.toolchain_prefix,
                "gcc_path": self.build.gcc_path,
                "flash_command": self.build.flash_command,
                "eide_mode": self.build.eide_mode,
                "tool_paths": dict(sorted(self.build.tool_paths.items())),
            },
            "generated_glue": list(self.generated_glue),
            "component_provenance": self.component_provenance,
            "reference_provenance": self.reference_provenance,
        }


def _Object_Require(data: Any, name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectModelError(f"{name} must be an object")
    return data


def _String_Require(
    data: dict[str, Any], name: str, *, allow_empty: bool = False
) -> str:
    value = data.get(name)
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ProjectModelError(f"{name} must be {qualifier}")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProjectModelError(f"{name} contains control characters")
    return value


def _StringList_Require(
    data: dict[str, Any], name: str, *, allow_empty_items: bool = False
) -> list[str]:
    value = data.get(name, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and (allow_empty_items or bool(item)) for item in value
    ):
        raise ProjectModelError(f"{name} must be an array of strings")
    if len(value) != len(set(value)):
        raise ProjectModelError(f"{name} contains duplicate values")
    return list(value)


def _ComponentId_Validate(value: str, name: str, *, allow_empty: bool = False) -> None:
    if value == "" and allow_empty:
        return
    if not COMPONENT_ID_PATTERN.fullmatch(value):
        raise ProjectModelError(f"Invalid {name}: {value!r}")


def _ProjectV0_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    components = _Object_Require(root.get("components"), "components")
    algorithms = list(components.get("algorithms", []))
    flight_logic = list(components.get("flight_logic", []))
    strategies: dict[str, str | None] = {}
    base: list[str] = [
        "silverstar.algorithm.common",
        "silverstar.algorithm.alignment.common",
    ]
    for component_id in algorithms:
        if ".alignment." in component_id:
            strategies["alignment"] = component_id
        elif ".ins." in component_id:
            strategies["ins"] = component_id
        elif ".estimator." in component_id:
            strategies["estimator"] = component_id
        else:
            base.append(component_id)
    for component_id in flight_logic:
        if ".landing." in component_id:
            strategies["landing"] = component_id
        else:
            base.append(component_id)
    migrated = {
        "format_version": 2,
        "project": root.get("project"),
        "components": {
            "core": components.get("core"),
            "mcu": components.get("mcu"),
            "board": components.get("board", ""),
            "os": components.get("os"),
            "devices": components.get("devices", []),
            "base": list(dict.fromkeys(base)),
            "strategies": strategies,
            "protocol_bundles": components.get("protocol_bundles", []),
            "development_environment": "silverstar.environment.vscode_eide_gcc",
        },
        "modes": {
            "calibration": ["Existing"],
            "deployment": ["ApogeeVerticalVelocity"],
        },
        "hardware": {
            "mode": "board_plugin",
            "source_kind": "verified_builtin",
            "provider": "",
            "snapshot_id": "",
            "ioc_file": "",
            "mcu": "",
            "capabilities": [],
            "inventory": {},
            "resources": [],
            "build_sources": [],
            "asm_sources": [],
            "include_dirs": [],
            "defines": [],
            "linker_script": "",
            "source_digest": "",
            "source_label": "",
            "risk_acknowledged": False,
        },
        "resources": root.get("resources", {}),
        "logging": root.get("logging", {"streams": []}),
        "build": dict(root.get("build", {})),
        "generated_glue": root.get("generated_glue", []),
        "component_provenance": root.get("component_provenance", {}),
        "reference_provenance": {},
    }
    migrated["build"]["eide_mode"] = "native"
    return migrated


def _ProjectV1_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    migrated["format_version"] = 2
    hardware = _Object_Require(migrated.get("hardware"), "hardware")
    hardware.setdefault("inventory", {})
    return migrated


def _LegacyDeviceClass_Get(plugin_id: str) -> str:
    marker = ".device."
    suffix = plugin_id.split(marker, 1)[1] if marker in plugin_id else "device"
    component_class = suffix.split(".", 1)[0]
    return "maintenance" if component_class == "console" else component_class


def _ProjectV2_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    components = _Object_Require(migrated.get("components"), "components")
    legacy_devices = components.get("devices", [])
    if not isinstance(legacy_devices, list) or not all(
        isinstance(plugin_id, str) and plugin_id for plugin_id in legacy_devices
    ):
        raise ProjectModelError("components.devices must be an array of component ids")
    class_counts: dict[str, int] = {}
    instance_by_plugin: dict[str, str] = {}
    instances: list[dict[str, str]] = []
    for plugin_id in legacy_devices:
        component_class = _LegacyDeviceClass_Get(plugin_id)
        index = class_counts.get(component_class, 0)
        class_counts[component_class] = index + 1
        instance_id = f"{component_class}{index}"
        instance_by_plugin[plugin_id] = instance_id
        instances.append({"instance_id": instance_id, "plugin": plugin_id})
    components["devices"] = instances
    resources = _Object_Require(migrated.get("resources"), "resources")
    migrated["resources"] = {
        (
            f"{instance_by_plugin[owner]}:{requirement}"
            if owner in instance_by_plugin
            else key
        ): resource_id
        for key, resource_id in resources.items()
        for owner, separator, requirement in (key.partition(":"),)
        if separator
    }
    generated_glue = migrated.get("generated_glue", [])
    if isinstance(generated_glue, list) and "project_capability_routes" not in generated_glue:
        generated_glue.append("project_capability_routes")
    migrated["capability_sources"] = {}
    migrated["format_version"] = 3
    return migrated


def _ProjectV3_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    migrated["capability_selections"] = {}
    migrated["format_version"] = 4
    return migrated


def _ProjectV4_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    migrated.pop("capability_selections", None)
    build = _Object_Require(migrated.get("build"), "build")
    build.pop("configuration", None)
    migrated["format_version"] = 5
    return migrated


def _ProjectV5_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    migrated["mode_parameters"] = deepcopy(DEFAULT_MODE_PARAMETERS)
    migrated["protocol_profiles"] = dict(DEFAULT_PROTOCOL_PROFILES)
    hardware = _Object_Require(migrated.get("hardware"), "hardware")
    hardware["assignment_fingerprint"] = ""
    generated_glue = migrated.get("generated_glue", [])
    if (
        isinstance(generated_glue, list)
        and "project_flight_config" not in generated_glue
    ):
        generated_glue.append("project_flight_config")
    migrated["format_version"] = 6
    return migrated


def _ProjectV6_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(root)
    project = _Object_Require(migrated.get("project"), "project")
    name = project.get("name")
    relative_path = f"{name}.ssdecoder" if isinstance(name, str) and name else ""
    migrated["log_decoder_profile"] = {
        "relative_path": relative_path,
        "package_schema": "1.0",
        "container_plugin_id": "silverstar.sslog.container/0.0",
        "generation_profile_sha256": "",
        "package_sha256": "",
    }
    generated_glue = migrated.get("generated_glue", [])
    if (
        isinstance(generated_glue, list)
        and "project_log_decoder_profile" not in generated_glue
    ):
        generated_glue.append("project_log_decoder_profile")
    migrated["format_version"] = 7
    return migrated


def _ProjectV7_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Migrate the former all-in-one Protocol Bundle to three locked slots."""
    migrated = deepcopy(root)
    components = _Object_Require(migrated.get("components"), "components")
    legacy_bundles = components.pop("protocol_bundles", [])
    if legacy_bundles not in (
        [],
        ["silverstar.protocol.reference_v0"],
    ):
        raise ProjectModelError(
            "Project format 7 contains an unsupported Protocol Bundle: "
            + ", ".join(str(value) for value in legacy_bundles)
        )
    legacy_profiles = _Object_Require(
        migrated.pop("protocol_profiles", {}), "protocol_profiles"
    )
    protocols: dict[str, dict[str, str]] = {}
    for category, component in DEFAULT_PROTOCOL_COMPONENTS.items():
        profile_value = legacy_profiles.get(
            category, DEFAULT_PROTOCOL_PROFILES[category]
        )
        if not isinstance(profile_value, str):
            raise ProjectModelError(
                f"Legacy protocol profile {category} must be a string"
            )
        protocols[category] = {
            "component": component,
            "version": "0.0",
            "profile": LEGACY_PROTOCOL_PROFILE_IDS.get(
                profile_value, profile_value
            ),
            # Filled deterministically from the installed manifest during
            # reconcile before a migrated project is saved again.
            "manifest_sha256": "",
        }
    migrated["protocols"] = protocols
    migrated["format_version"] = 8
    return migrated


def _ProjectV8_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Add auditable CubeMX/HAL compatibility facts and I2C evidence."""
    migrated = deepcopy(root)
    hardware = _Object_Require(migrated.get("hardware"), "hardware")
    inventory = _Object_Require(hardware.get("inventory", {}), "hardware inventory")
    hardware["cubemx_version"] = str(inventory.get("cubemx_version", ""))
    hardware["firmware_package"] = str(inventory.get("firmware_package", ""))
    # Reconcile fills this from the selected Platform contract.  Keeping it
    # empty here avoids inventing a source policy for third-party Platforms.
    hardware["hal_cmsis_source_policy"] = ""
    hardware["i2c_external_pullup_confirmations"] = {}
    migrated["format_version"] = 9
    return migrated


def _ProjectV9_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Move SS0.5 storage/log-sink ownership from Board to a Device."""
    migrated = deepcopy(root)
    components = _Object_Require(migrated.get("components"), "components")
    devices = components.get("devices")
    if not isinstance(devices, list):
        raise ProjectModelError("components.devices must be an array")
    storage_plugin = "silverstar.device.storage.sd_sdio_fatfs"
    board_plugin = "silverstar.board.silverstar_0_5"
    if components.get("board") == board_plugin and not any(
        isinstance(device, dict) and device.get("plugin") == storage_plugin
        for device in devices
    ):
        used_ids = {
            str(device.get("instance_id"))
            for device in devices
            if isinstance(device, dict)
        }
        instance_id = "storage0"
        suffix = 1
        while instance_id in used_ids:
            instance_id = f"storage0_{suffix}"
            suffix += 1
        devices.append({"instance_id": instance_id, "plugin": storage_plugin})
        resources = _Object_Require(migrated.get("resources"), "resources")
        storage_resource = resources.pop(
            f"{board_plugin}:storage",
            resources.pop("flight_controller_board:storage", "PLATFORM_SDIO_1"),
        )
        resources[f"{instance_id}:storage"] = storage_resource
        resources.setdefault(f"{instance_id}:time", "PLATFORM_TIME_1")
    generated_glue = migrated.get("generated_glue", [])
    if (
        isinstance(generated_glue, list)
        and "project_storage_binding" not in generated_glue
    ):
        generated_glue.append("project_storage_binding")
    migrated["format_version"] = 10
    return migrated


def _ProjectV10_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Allow each independently selected Protocol slot to be explicitly off."""
    migrated = deepcopy(root)
    protocols = _Object_Require(migrated.get("protocols"), "protocols")
    if set(protocols) != set(PROTOCOL_CATEGORIES):
        raise ProjectModelError(
            "protocols must contain exactly telemetry, maintenance and logging"
        )
    # Format 10 required all three selections, so preserving the objects is a
    # lossless migration.  Format 11 merely permits a slot to be null later.
    migrated["format_version"] = 11
    return migrated


def _CurrentPreRelease_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Upgrade only the exact official 0.0.9 pre-release identity."""

    migrated = deepcopy(root)
    if migrated.get("format_version") != PROJECT_FORMAT_VERSION:
        return migrated
    project = migrated.get("project")
    components = migrated.get("components")
    if not isinstance(project, dict) or not isinstance(components, dict):
        return migrated
    official_identity = (
        project.get("firmware_version") == "0.0.9"
        and project.get("build_target") == "SilverStar_0_0_9"
        and components.get("core") == "silverstar.core.0_0_9"
    )
    if not official_identity:
        return migrated

    project["firmware_version"] = SILVERSTAR_PLATFORM_VERSION
    project["build_target"] = SILVERSTAR_BUILD_ID
    components["core"] = SILVERSTAR_CORE_COMPONENT_ID

    modes = migrated.get("modes")
    if isinstance(modes, dict):
        calibration = modes.get("calibration")
        if isinstance(calibration, list):
            if len(calibration) != len(set(calibration)):
                raise ProjectModelError(
                    "modes.calibration contains duplicate values"
                )
            modes["calibration"] = [
                option for option in calibration if option != "Existing"
            ]

    provenance = migrated.get("component_provenance")
    if isinstance(provenance, dict) and "silverstar.core.0_0_9" in provenance:
        reference = migrated.get("reference_provenance")
        if isinstance(reference, dict):
            reference["pre_release_migration"] = {
                "from": "0.0.9",
                "to": SILVERSTAR_PLATFORM_VERSION,
                "requires_new_output_directory": True,
            }
    return migrated


def _OfficialCoreV10_Migrate(root: dict[str, Any]) -> dict[str, Any]:
    """Move only the exact official 0.0.10 format-12 identity to this release."""
    if root.get("format_version") != PROJECT_FORMAT_VERSION:
        return root
    project = root.get("project")
    components = root.get("components")
    if not isinstance(project, dict) or not isinstance(components, dict):
        return root
    if (
        project.get("firmware_version") != "0.0.10"
        or project.get("build_target") != "SilverStar_0_0_10"
        or components.get("core") != "silverstar.core.0_0_10"
    ):
        return root
    migrated = deepcopy(root)
    migrated["project"]["firmware_version"] = SILVERSTAR_PLATFORM_VERSION
    migrated["project"]["build_target"] = SILVERSTAR_BUILD_ID
    migrated["components"]["core"] = SILVERSTAR_CORE_COMPONENT_ID
    return migrated


def _LogDecoderProfile_Parse(value: Any) -> LogDecoderProfileReference:
    profile = _Object_Require(value, "log_decoder_profile")
    expected = {
        "relative_path",
        "package_schema",
        "container_plugin_id",
        "generation_profile_sha256",
        "package_sha256",
    }
    if set(profile) != expected:
        raise ProjectModelError(
            "log_decoder_profile has missing or unknown fields"
        )
    relative_path = _String_Require(
        profile, "relative_path", allow_empty=True
    )
    if relative_path:
        parts = relative_path.split("/")
        if (
            not RELATIVE_FILE_PATTERN.fullmatch(relative_path)
            or "\\" in relative_path
            or relative_path.startswith("/")
            or any(part in ("", ".", "..") for part in parts)
            or not relative_path.casefold().endswith(".ssdecoder")
        ):
            raise ProjectModelError(
                f"Invalid log decoder profile path: {relative_path!r}"
            )
    package_schema = _String_Require(
        profile, "package_schema", allow_empty=True
    )
    container_plugin_id = _String_Require(
        profile, "container_plugin_id", allow_empty=True
    )
    if package_schema and not FIRMWARE_VERSION_PATTERN.fullmatch(package_schema):
        raise ProjectModelError("log_decoder_profile package schema is invalid")
    if container_plugin_id and not CONTAINER_PLUGIN_ID_PATTERN.fullmatch(
        container_plugin_id
    ):
        raise ProjectModelError(
            "log_decoder_profile container plugin id is invalid"
        )
    generation_profile_sha256 = _String_Require(
        profile, "generation_profile_sha256", allow_empty=True
    )
    package_sha256 = _String_Require(
        profile, "package_sha256", allow_empty=True
    )
    if any(
        digest and not SHA256_PATTERN.fullmatch(digest)
        for digest in (generation_profile_sha256, package_sha256)
    ):
        raise ProjectModelError("log_decoder_profile hashes are invalid")
    if bool(generation_profile_sha256) != bool(package_sha256):
        raise ProjectModelError(
            "log_decoder_profile hashes must either both be present or both be empty"
        )
    if relative_path:
        if not package_schema or not container_plugin_id:
            raise ProjectModelError(
                "Active log_decoder_profile identity is incomplete"
            )
    elif any(
        (
            package_schema,
            container_plugin_id,
            generation_profile_sha256,
            package_sha256,
        )
    ):
        raise ProjectModelError(
            "Inactive log_decoder_profile must be completely empty"
        )
    return LogDecoderProfileReference(
        relative_path=relative_path,
        package_schema=package_schema,
        container_plugin_id=container_plugin_id,
        generation_profile_sha256=generation_profile_sha256,
        package_sha256=package_sha256,
    )


def _DeviceInstances_Parse(value: Any) -> list[DeviceInstance]:
    if not isinstance(value, list):
        raise ProjectModelError("components.devices must be an array")
    instances: list[DeviceInstance] = []
    instance_ids: set[str] = set()
    for entry_value in value:
        entry = _Object_Require(entry_value, "device instance")
        if set(entry) != {"instance_id", "plugin"}:
            raise ProjectModelError(
                "device instance must contain instance_id and plugin"
            )
        instance_id = _String_Require(entry, "instance_id")
        plugin = _String_Require(entry, "plugin")
        if not DEVICE_INSTANCE_ID_PATTERN.fullmatch(instance_id):
            raise ProjectModelError(f"Invalid device instance id: {instance_id!r}")
        _ComponentId_Validate(plugin, "device plugin")
        if instance_id in instance_ids:
            raise ProjectModelError(f"Duplicate device instance id: {instance_id}")
        instance_ids.add(instance_id)
        instances.append(DeviceInstance(instance_id, plugin))
    return instances


def _Components_Parse(data: Any) -> tuple[
    str,
    str,
    str,
    str,
    list[DeviceInstance],
    list[str],
    dict[str, str | None],
    str,
]:
    components = _Object_Require(data, "components")
    expected = {
        "core",
        "mcu",
        "board",
        "os",
        "devices",
        "base",
        "strategies",
        "development_environment",
    }
    if set(components) != expected:
        raise ProjectModelError("components has missing or unknown fields")
    core = _String_Require(components, "core")
    mcu = _String_Require(components, "mcu")
    board = _String_Require(components, "board", allow_empty=True)
    os_component = _String_Require(components, "os")
    device_instances = _DeviceInstances_Parse(components.get("devices"))
    base = _StringList_Require(components, "base")
    environment = _String_Require(components, "development_environment")
    for name, value, allow_empty in (
        ("core component", core, False),
        ("mcu component", mcu, False),
        ("board component", board, True),
        ("os component", os_component, False),
        ("development environment", environment, False),
    ):
        _ComponentId_Validate(value, name, allow_empty=allow_empty)
    for component_id in (
        *(instance.plugin for instance in device_instances),
        *base,
    ):
        _ComponentId_Validate(component_id, "component id")
    strategy_data = _Object_Require(components.get("strategies"), "strategies")
    strategies: dict[str, str | None] = {}
    for slot, component_id in strategy_data.items():
        if not isinstance(slot, str) or not SELECTION_SLOT_PATTERN.fullmatch(slot):
            raise ProjectModelError(f"Invalid strategy slot: {slot!r}")
        if component_id is not None:
            if not isinstance(component_id, str):
                raise ProjectModelError(f"Strategy {slot} must be a component id or null")
            _ComponentId_Validate(component_id, f"strategy {slot}")
        strategies[slot] = component_id
    return (
        core,
        mcu,
        board,
        os_component,
        device_instances,
        base,
        strategies,
        environment,
    )


def _Modes_Parse(value: Any) -> dict[str, list[str]]:
    data = _Object_Require(value, "modes")
    modes: dict[str, list[str]] = {}
    for slot, selection_value in data.items():
        if not isinstance(slot, str) or not SELECTION_SLOT_PATTERN.fullmatch(slot):
            raise ProjectModelError(f"Invalid mode slot: {slot!r}")
        wrapper = {"selection": selection_value}
        selection = _StringList_Require(wrapper, "selection")
        invalid = next(
            (
                option
                for option in selection
                if not SELECTION_OPTION_PATTERN.fullmatch(option)
            ),
            None,
        )
        if invalid is not None:
            raise ProjectModelError(f"Invalid mode option: {invalid!r}")
        modes[slot] = selection
    return modes


def _AlgorithmParameters_Parse(value: Any) -> dict[str, dict[str, float | int]]:
    data = _Object_Require(value, "algorithm_parameters")
    result = {}
    for component, parameters in data.items():
        if not isinstance(component, str) or not re.fullmatch(r"[a-z][a-z0-9_.]*", component):
            raise ProjectModelError("Invalid algorithm component id")
        result[component] = {}
        for key, number in _Object_Require(parameters, component).items():
            if (not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key)
                    or type(number) not in (float, int)
                    or (type(number) is float and not math.isfinite(number))):
                raise ProjectModelError("Algorithm parameters must be finite actual numbers")
            result[component][key] = number
    return result


def _ModeParameters_Parse(
    value: Any,
) -> dict[str, dict[str, dict[str, float | int]]]:
    data = _Object_Require(value, "mode_parameters")
    result: dict[str, dict[str, dict[str, float | int]]] = {}
    for slot, options_value in data.items():
        if not isinstance(slot, str) or not SELECTION_SLOT_PATTERN.fullmatch(slot):
            raise ProjectModelError(f"Invalid mode parameter slot: {slot!r}")
        options = _Object_Require(
            options_value, f"mode_parameters.{slot}"
        )
        normalized_options: dict[str, dict[str, float | int]] = {}
        for option, parameters_value in options.items():
            if (
                not isinstance(option, str)
                or not SELECTION_OPTION_PATTERN.fullmatch(option)
            ):
                raise ProjectModelError(
                    f"Invalid mode parameter option: {option!r}"
                )
            parameters = _Object_Require(
                parameters_value, f"mode_parameters.{slot}.{option}"
            )
            normalized_parameters: dict[str, float | int] = {}
            for parameter_id, parameter_value in parameters.items():
                if (
                    not isinstance(parameter_id, str)
                    or not COMPONENT_ID_PATTERN.fullmatch(parameter_id)
                ):
                    raise ProjectModelError(
                        f"Invalid mode parameter id: {parameter_id!r}"
                    )
                if (
                    isinstance(parameter_value, bool)
                    or not isinstance(parameter_value, (int, float))
                    or not math.isfinite(float(parameter_value))
                ):
                    raise ProjectModelError(
                        f"Mode parameter {slot}.{option}.{parameter_id} "
                        "must be a finite number"
                    )
                normalized_parameters[parameter_id] = parameter_value
            normalized_options[option] = normalized_parameters
        result[slot] = normalized_options
    return result


def _Protocols_Parse(value: Any) -> dict[str, ProtocolSelection | None]:
    data = _Object_Require(value, "protocols")
    if set(data) != set(PROTOCOL_CATEGORIES):
        raise ProjectModelError(
            "protocols must contain exactly telemetry, maintenance and logging"
        )
    result: dict[str, ProtocolSelection | None] = {}
    for category, selection_value in data.items():
        if selection_value is None:
            result[category] = None
            continue
        selection = _Object_Require(
            selection_value, f"protocols.{category}"
        )
        expected = {"component", "version", "profile", "manifest_sha256"}
        if set(selection) != expected:
            raise ProjectModelError(
                f"protocols.{category} has missing or unknown fields"
            )
        component = _String_Require(selection, "component")
        version = _String_Require(selection, "version")
        profile = _String_Require(selection, "profile")
        manifest_sha256 = _String_Require(
            selection, "manifest_sha256", allow_empty=True
        )
        _ComponentId_Validate(component, f"protocols.{category}.component")
        if not FIRMWARE_VERSION_PATTERN.fullmatch(version):
            raise ProjectModelError(
                f"protocols.{category}.version is invalid"
            )
        if not COMPONENT_ID_PATTERN.fullmatch(profile):
            raise ProjectModelError(
                f"protocols.{category}.profile is invalid"
            )
        if manifest_sha256 and not SHA256_PATTERN.fullmatch(manifest_sha256):
            raise ProjectModelError(
                f"protocols.{category}.manifest_sha256 is invalid"
            )
        result[category] = ProtocolSelection(
            component=component,
            version=version,
            profile=profile,
            manifest_sha256=manifest_sha256,
        )
    return result


def _Hardware_Parse(value: Any, *, board: str) -> HardwareConfiguration:
    data = _Object_Require(value, "hardware")
    expected = {
        "mode",
        "source_kind",
        "provider",
        "snapshot_id",
        "ioc_file",
        "mcu",
        "cubemx_version",
        "firmware_package",
        "hal_cmsis_source_policy",
        "i2c_external_pullup_confirmations",
        "capabilities",
        "inventory",
        "resources",
        "build_sources",
        "asm_sources",
        "include_dirs",
        "defines",
        "linker_script",
        "source_digest",
        "source_label",
        "risk_acknowledged",
        "assignment_fingerprint",
    }
    lock_fields = {
        "platform_component",
        "platform_version",
        "platform_manifest_sha256",
    }
    if not expected.issubset(data) or set(data) - expected - lock_fields:
        raise ProjectModelError("hardware has missing or unknown fields")
    mode = _String_Require(data, "mode")
    source_kind = _String_Require(data, "source_kind")
    provider = _String_Require(data, "provider", allow_empty=True)
    snapshot_id = _String_Require(data, "snapshot_id", allow_empty=True)
    ioc_file = _String_Require(data, "ioc_file", allow_empty=True)
    mcu = _String_Require(data, "mcu", allow_empty=True)
    platform_component = str(data.get("platform_component", ""))
    platform_version = str(data.get("platform_version", ""))
    platform_manifest_sha256 = str(data.get("platform_manifest_sha256", ""))
    cubemx_version = _String_Require(
        data, "cubemx_version", allow_empty=True
    )
    firmware_package = _String_Require(
        data, "firmware_package", allow_empty=True
    )
    hal_cmsis_source_policy = _String_Require(
        data, "hal_cmsis_source_policy", allow_empty=True
    )
    if hal_cmsis_source_policy not in {
        "",
        "plugin_payload_authoritative",
        "imported_tree_authoritative",
    }:
        raise ProjectModelError("hardware.hal_cmsis_source_policy is invalid")
    raw_pullup_confirmations = _Object_Require(
        data.get("i2c_external_pullup_confirmations"),
        "hardware.i2c_external_pullup_confirmations",
    )
    pullup_confirmations: dict[str, dict[str, str]] = {}
    for resource_id, raw_binding in raw_pullup_confirmations.items():
        if (
            not isinstance(resource_id, str)
            or RESOURCE_ID_PATTERN.fullmatch(resource_id) is None
        ):
            raise ProjectModelError(
                "hardware.i2c_external_pullup_confirmations has an invalid resource id"
            )
        binding = _Object_Require(
            raw_binding,
            f"hardware.i2c_external_pullup_confirmations.{resource_id}",
        )
        if set(binding) != {"source_digest", "snapshot_id"}:
            raise ProjectModelError(
                "I2C external pull-up confirmation must bind source_digest and snapshot_id"
            )
        source_binding = _String_Require(binding, "source_digest")
        snapshot_binding = _String_Require(binding, "snapshot_id")
        if not SHA256_PATTERN.fullmatch(source_binding) or not SHA256_PATTERN.fullmatch(
            snapshot_binding
        ):
            raise ProjectModelError(
                "I2C external pull-up confirmation contains an invalid digest"
            )
        pullup_confirmations[resource_id] = {
            "source_digest": source_binding,
            "snapshot_id": snapshot_binding,
        }
    _ComponentId_Validate(
        platform_component, "hardware platform_component", allow_empty=True
    )
    if platform_version and not FIRMWARE_VERSION_PATTERN.fullmatch(platform_version):
        raise ProjectModelError("hardware.platform_version is invalid")
    if platform_manifest_sha256 and not SHA256_PATTERN.fullmatch(
        platform_manifest_sha256
    ):
        raise ProjectModelError("hardware.platform_manifest_sha256 is invalid")
    if any((platform_component, platform_version, platform_manifest_sha256)) and not all(
        (platform_component, platform_version, platform_manifest_sha256)
    ):
        raise ProjectModelError("hardware Platform lock is incomplete")
    source_digest = _String_Require(data, "source_digest", allow_empty=True)
    source_label = _String_Require(data, "source_label", allow_empty=True)
    assignment_fingerprint = _String_Require(
        data, "assignment_fingerprint", allow_empty=True
    )
    capabilities = tuple(_StringList_Require(data, "capabilities"))
    inventory = _Object_Require(data.get("inventory"), "hardware inventory")
    resources_value = data.get("resources")
    if not isinstance(resources_value, list):
        raise ProjectModelError("hardware.resources must be an array")
    resources: list[HardwareResource] = []
    resource_ids: set[str] = set()
    for entry_value in resources_value:
        entry = _Object_Require(entry_value, "hardware resource")
        if set(entry) != {"id", "kind", "metadata"}:
            raise ProjectModelError("hardware resource has missing or unknown fields")
        resource_id = _String_Require(entry, "id")
        kind = _String_Require(entry, "kind")
        metadata = _Object_Require(entry.get("metadata"), "hardware resource metadata")
        if not RESOURCE_ID_PATTERN.fullmatch(resource_id):
            raise ProjectModelError(f"Invalid hardware resource id: {resource_id!r}")
        if not COMPONENT_ID_PATTERN.fullmatch(kind):
            raise ProjectModelError(f"Invalid hardware resource kind: {kind!r}")
        if resource_id in resource_ids:
            raise ProjectModelError(f"Duplicate hardware resource: {resource_id}")
        resource_ids.add(resource_id)
        resources.append(HardwareResource(resource_id, kind, dict(metadata)))
    build_sources = tuple(_StringList_Require(data, "build_sources"))
    asm_sources = tuple(_StringList_Require(data, "asm_sources"))
    include_dirs = tuple(_StringList_Require(data, "include_dirs"))
    defines = tuple(_StringList_Require(data, "defines"))
    linker_script = _String_Require(data, "linker_script", allow_empty=True)
    for field_name, paths in (
        ("hardware.build_sources", build_sources),
        ("hardware.asm_sources", asm_sources),
        ("hardware.include_dirs", include_dirs),
    ):
        for path in paths:
            if (
                not RELATIVE_FILE_PATTERN.fullmatch(path)
                or path.startswith("/")
                or ".." in Path(path).parts
            ):
                raise ProjectModelError(f"{field_name} contains an invalid path")
    if linker_script and (
        not RELATIVE_FILE_PATTERN.fullmatch(linker_script)
        or linker_script.startswith("/")
        or ".." in Path(linker_script).parts
    ):
        raise ProjectModelError("hardware.linker_script is invalid")
    if not all(
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_+.,:/()-]+)?", define)
        for define in defines
    ):
        raise ProjectModelError("hardware.defines contains an invalid token")
    risk_acknowledged = data.get("risk_acknowledged")
    if not isinstance(risk_acknowledged, bool):
        raise ProjectModelError("hardware.risk_acknowledged must be boolean")
    if mode not in HARDWARE_MODES:
        raise ProjectModelError("hardware.mode is invalid")
    if source_kind not in BOARD_SOURCE_KINDS:
        raise ProjectModelError("hardware.source_kind is invalid")
    _ComponentId_Validate(provider, "hardware provider", allow_empty=True)
    if snapshot_id and not SHA256_PATTERN.fullmatch(snapshot_id):
        raise ProjectModelError("hardware.snapshot_id is invalid")
    if source_digest and not SHA256_PATTERN.fullmatch(source_digest):
        raise ProjectModelError("hardware.source_digest is invalid")
    if assignment_fingerprint and not SHA256_PATTERN.fullmatch(
        assignment_fingerprint
    ):
        raise ProjectModelError("hardware.assignment_fingerprint is invalid")
    if ioc_file and (
        not RELATIVE_FILE_PATTERN.fullmatch(ioc_file)
        or ioc_file.startswith("/")
        or ".." in Path(ioc_file).parts
    ):
        raise ProjectModelError("hardware.ioc_file is invalid")
    if mode == "unselected":
        if (
            board
            or provider
            or snapshot_id
            or ioc_file
            or mcu
            or source_digest
            or platform_component
            or platform_version
            or platform_manifest_sha256
            or cubemx_version
            or firmware_package
            or hal_cmsis_source_policy
            or pullup_confirmations
        ):
            raise ProjectModelError("unselected hardware must not contain a selection")
        if source_kind != "unselected":
            raise ProjectModelError("unselected hardware requires unselected source_kind")
    if mode == "board_plugin" and not board:
        raise ProjectModelError("board_plugin hardware requires a board component")
    if mode == "custom":
        if board:
            raise ProjectModelError("custom hardware must not select a board plugin")
        if not provider:
            raise ProjectModelError("custom hardware requires a provider")
    return HardwareConfiguration(
        mode=mode,
        source_kind=source_kind,
        provider=provider,
        snapshot_id=snapshot_id,
        ioc_file=ioc_file,
        mcu=mcu,
        platform_component=platform_component,
        platform_version=platform_version,
        platform_manifest_sha256=platform_manifest_sha256,
        cubemx_version=cubemx_version,
        firmware_package=firmware_package,
        hal_cmsis_source_policy=hal_cmsis_source_policy,
        i2c_external_pullup_confirmations=pullup_confirmations,
        capabilities=capabilities,
        inventory=dict(inventory),
        resources=tuple(resources),
        build_sources=build_sources,
        asm_sources=asm_sources,
        include_dirs=include_dirs,
        defines=defines,
        linker_script=linker_script,
        source_digest=source_digest,
        source_label=source_label,
        risk_acknowledged=risk_acknowledged,
        assignment_fingerprint=assignment_fingerprint,
    )


def _Logging_Parse(value: Any) -> list[LogStreamConfig]:
    logging_data = _Object_Require(value, "logging")
    if set(logging_data) != {"streams"}:
        raise ProjectModelError("logging must contain only streams")
    streams_data = logging_data.get("streams", [])
    if not isinstance(streams_data, list):
        raise ProjectModelError("logging.streams must be an array")
    streams: list[LogStreamConfig] = []
    seen_records: set[str] = set()
    valid_policies = {"EVERY", "DECIMATION", "PERIODIC", "EVENT", "ONE_SHOT"}
    for entry_value in streams_data:
        entry = _Object_Require(entry_value, "logging stream")
        if set(entry) != {"record", "enabled", "policy", "decimation", "period_us"}:
            raise ProjectModelError("logging stream has missing or unknown fields")
        record = _String_Require(entry, "record")
        if not LOG_RECORD_PATTERN.fullmatch(record):
            raise ProjectModelError(f"Invalid logging record: {record!r}")
        if record in seen_records:
            raise ProjectModelError(f"Duplicate logging stream: {record}")
        seen_records.add(record)
        policy = _String_Require(entry, "policy")
        if policy not in valid_policies:
            raise ProjectModelError(f"Invalid logging policy for {record}: {policy}")
        decimation = entry.get("decimation")
        period_us = entry.get("period_us")
        if isinstance(decimation, bool) or not isinstance(decimation, int) or not 1 <= decimation <= 65535:
            raise ProjectModelError(f"Invalid decimation for {record}")
        if isinstance(period_us, bool) or not isinstance(period_us, int) or not 0 <= period_us <= 0xFFFFFFFF:
            raise ProjectModelError(f"Invalid period_us for {record}")
        enabled = entry.get("enabled")
        if not isinstance(enabled, bool):
            raise ProjectModelError(f"enabled must be boolean for {record}")
        streams.append(LogStreamConfig(record, enabled, policy, decimation, period_us))
    return streams


def _Build_Parse(value: Any) -> BuildOptions:
    data = _Object_Require(value, "build")
    expected = {
        "target_profile",
        "make_command",
        "toolchain_prefix",
        "gcc_path",
        "flash_command",
        "eide_mode",
        "tool_paths",
    }
    if set(data) != expected:
        raise ProjectModelError("build has missing or unknown fields")
    target_profile = _String_Require(
        data, "target_profile", allow_empty=True
    )
    if target_profile and not BUILD_TARGET_PROFILE_PATTERN.fullmatch(
        target_profile
    ):
        raise ProjectModelError(f"Invalid target profile: {target_profile!r}")
    toolchain_prefix = _String_Require(data, "toolchain_prefix")
    eide_mode = _String_Require(data, "eide_mode")
    if not TOOLCHAIN_PREFIX_PATTERN.fullmatch(toolchain_prefix):
        raise ProjectModelError("build.toolchain_prefix is invalid")
    if eide_mode != "native":
        raise ProjectModelError("Only EIDE native mode is supported")
    tool_paths = _Object_Require(data.get("tool_paths"), "build.tool_paths")
    allowed_tool_ids = {
        "compiler",
        "objcopy",
        "size",
        "make",
        "host_gcc",
        "debugger",
        "static_analyzer",
        "cubemx",
        "eide_builder",
    }
    if set(tool_paths) - allowed_tool_ids:
        raise ProjectModelError("build.tool_paths contains unknown tool ids")
    if not all(
        isinstance(path, str)
        and bool(path)
        and not any(ord(character) < 32 or ord(character) == 127 for character in path)
        for path in tool_paths.values()
    ):
        raise ProjectModelError("build.tool_paths must map tool ids to non-empty paths")
    return BuildOptions(
        target_profile=target_profile,
        make_command=_String_Require(data, "make_command"),
        toolchain_prefix=toolchain_prefix,
        gcc_path=_String_Require(data, "gcc_path", allow_empty=True),
        flash_command=_String_Require(data, "flash_command", allow_empty=True),
        eide_mode=eide_mode,
        tool_paths=dict(tool_paths),
    )


def _Provenance_Parse(value: Any) -> dict[str, dict[str, Any]]:
    provenance = _Object_Require(value, "component_provenance")
    for component_id, entry_value in provenance.items():
        if not isinstance(component_id, str) or not COMPONENT_ID_PATTERN.fullmatch(
            component_id
        ):
            raise ProjectModelError(
                "component_provenance contains an invalid component id"
            )
        entry = _Object_Require(entry_value, f"component_provenance.{component_id}")
        expected = {"version", "source", "manifest_id", "payload_digest", "files"}
        if set(entry) != expected or entry.get("manifest_id") != component_id:
            raise ProjectModelError(
                f"component_provenance.{component_id} has missing or invalid fields"
            )
        version = entry.get("version")
        digest = entry.get("payload_digest")
        if not isinstance(version, str) or not FIRMWARE_VERSION_PATTERN.fullmatch(version):
            raise ProjectModelError(
                f"component_provenance.{component_id} has an invalid version"
            )
        if entry.get("source") not in ("builtin", "installed"):
            raise ProjectModelError(
                f"component_provenance.{component_id} has an invalid source"
            )
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ProjectModelError(
                f"component_provenance.{component_id} has an invalid payload digest"
            )
        files = _Object_Require(entry.get("files"), f"component_provenance.{component_id}.files")
        if not all(
            isinstance(path, str)
            and bool(path)
            and isinstance(file_digest, str)
            and SHA256_PATTERN.fullmatch(file_digest)
            for path, file_digest in files.items()
        ):
            raise ProjectModelError(
                f"component_provenance.{component_id}.files is invalid"
            )
    return dict(provenance)


def ProjectModel_Parse(data: dict[str, Any]) -> ProjectModel:
    root = _Object_Require(data, "project file")
    if root.get("format_version") == 0:
        root = _ProjectV0_Migrate(root)
    if root.get("format_version") == 1:
        root = _ProjectV1_Migrate(root)
    if root.get("format_version") == 2:
        root = _ProjectV2_Migrate(root)
    if root.get("format_version") == 3:
        root = _ProjectV3_Migrate(root)
    if root.get("format_version") == 4:
        root = _ProjectV4_Migrate(root)
    if root.get("format_version") == 5:
        root = _ProjectV5_Migrate(root)
    if root.get("format_version") == 6:
        root = _ProjectV6_Migrate(root)
    if root.get("format_version") == 7:
        root = _ProjectV7_Migrate(root)
    if root.get("format_version") == 8:
        root = _ProjectV8_Migrate(root)
    if root.get("format_version") == 9:
        root = _ProjectV9_Migrate(root)
    if root.get("format_version") == 10:
        root = _ProjectV10_Migrate(root)
    if root.get("format_version") == 11:
        root = deepcopy(root)
        root["format_version"] = PROJECT_FORMAT_VERSION
        root["algorithm_parameters"] = {}
        if isinstance(root.get("generated_glue"), list):
            root["generated_glue"] = list(dict.fromkeys([*root["generated_glue"], "project_algorithm_parameters"]))
    root = _CurrentPreRelease_Migrate(root)
    root = _OfficialCoreV10_Migrate(root)
    required_root = {
        "format_version",
        "project",
        "components",
        "modes",
        "mode_parameters",
        "algorithm_parameters",
        "protocols",
        "hardware",
        "resources",
        "capability_sources",
        "logging",
        "log_decoder_profile",
        "build",
        "generated_glue",
        "component_provenance",
        "reference_provenance",
    }
    if set(root) != required_root:
        missing = required_root - set(root)
        unknown = set(root) - required_root
        details = [
            *(f"missing {name}" for name in sorted(missing)),
            *(f"unknown {name}" for name in sorted(unknown)),
        ]
        raise ProjectModelError("Project fields are invalid: " + ", ".join(details))
    if root.get("format_version") != PROJECT_FORMAT_VERSION:
        raise ProjectModelError(
            f"Only project format_version {PROJECT_FORMAT_VERSION} is supported"
        )
    project_data = _Object_Require(root.get("project"), "project")
    if set(project_data) != {"name", "firmware_version", "build_target"}:
        raise ProjectModelError(
            "project must contain name, firmware_version and build_target"
        )
    name = _String_Require(project_data, "name")
    firmware_version = _String_Require(project_data, "firmware_version")
    build_target = _String_Require(project_data, "build_target")
    if not PROJECT_NAME_PATTERN.fullmatch(name) or name.strip() != name:
        raise ProjectModelError(f"Invalid project name: {name!r}")
    if not FIRMWARE_VERSION_PATTERN.fullmatch(firmware_version):
        raise ProjectModelError(f"Invalid firmware version: {firmware_version!r}")
    if not PROJECT_TOKEN_PATTERN.fullmatch(build_target):
        raise ProjectModelError(f"Invalid build target: {build_target!r}")
    (
        core,
        mcu,
        board,
        os_component,
        device_instances,
        base,
        strategies,
        environment,
    ) = _Components_Parse(root.get("components"))
    modes = _Modes_Parse(root.get("modes"))
    algorithm_parameters = _AlgorithmParameters_Parse(root.get("algorithm_parameters"))
    mode_parameters = _ModeParameters_Parse(root.get("mode_parameters"))
    protocols = _Protocols_Parse(root.get("protocols"))
    hardware = _Hardware_Parse(root.get("hardware"), board=board)
    resources = _Object_Require(root.get("resources"), "resources")
    if not all(
        isinstance(key, str)
        and RESOURCE_KEY_PATTERN.fullmatch(key)
        and isinstance(resource_id, str)
        and RESOURCE_ID_PATTERN.fullmatch(resource_id)
        for key, resource_id in resources.items()
    ):
        raise ProjectModelError(
            "resources must map requirement keys to resource ids"
        )
    capability_sources = _Object_Require(
        root.get("capability_sources"), "capability_sources"
    )
    instance_ids = {instance.instance_id for instance in device_instances}
    if not all(
        isinstance(capability, str)
        and COMPONENT_ID_PATTERN.fullmatch(capability)
        and isinstance(instance_id, str)
        and instance_id in instance_ids
        for capability, instance_id in capability_sources.items()
    ):
        raise ProjectModelError(
            "capability_sources must map capabilities to selected device instances"
        )
    generated_wrapper = {"generated_glue": root.get("generated_glue")}
    generated_glue = _StringList_Require(generated_wrapper, "generated_glue")
    if any(not PROJECT_TOKEN_PATTERN.fullmatch(value) for value in generated_glue):
        raise ProjectModelError("generated_glue contains an invalid identifier")
    reference_provenance = _Object_Require(
        root.get("reference_provenance"), "reference_provenance"
    )
    return ProjectModel(
        identity=ProjectIdentity(name, firmware_version, build_target),
        core=core,
        mcu=mcu,
        board=board,
        os=os_component,
        device_instances=device_instances,
        base_components=base,
        strategies=strategies,
        modes=modes,
        mode_parameters=mode_parameters,
        algorithm_parameters=algorithm_parameters,
        protocols=protocols,
        development_environment=environment,
        hardware=hardware,
        resource_assignments=dict(resources),
        capability_source_overrides=dict(capability_sources),
        logging_streams=_Logging_Parse(root.get("logging")),
        log_decoder_profile=_LogDecoderProfile_Parse(
            root.get("log_decoder_profile")
        ),
        build=_Build_Parse(root.get("build")),
        generated_glue=generated_glue,
        component_provenance=_Provenance_Parse(root.get("component_provenance")),
        reference_provenance=dict(reference_provenance),
        format_version=PROJECT_FORMAT_VERSION,
    )


def ProjectModel_Load(path: Path) -> ProjectModel:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectModelError(f"Cannot read project file {path}: {error}") from error
    original_version = data.get("format_version")
    model = ProjectModel_Parse(data)
    if (
        isinstance(original_version, int)
        and original_version <= 9
        and model.hardware.mode == "custom"
    ):
        snapshot_root = path.parent / "HardwareGenerated" / "STM32CubeMX"
        ioc_path = snapshot_root.joinpath(*model.hardware.ioc_file.split("/"))
        if ioc_path.is_file() and not ioc_path.is_symlink():
            try:
                from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse

                generated_files = {
                    source.relative_to(snapshot_root).as_posix(): source.read_text(
                        encoding="utf-8-sig"
                    )
                    for relative_root in (
                        "Core/Src", "Core/Inc", "FATFS/App", "FATFS/Target"
                    )
                    for directory in (
                        snapshot_root.joinpath(*relative_root.split("/")),
                    )
                    if directory.is_dir() and not directory.is_symlink()
                    for source in sorted(directory.glob("*"))
                    if source.is_file()
                    and not source.is_symlink()
                    and source.suffix.casefold() in {".c", ".h"}
                }
                inventory = CubeMxInventory_Parse(
                    ioc_path.read_text(encoding="utf-8-sig"),
                    generated_files=generated_files,
                )
            except (OSError, UnicodeError):
                pass
            else:
                prefix = "HardwareGenerated/STM32CubeMX"
                build_sources = tuple(
                    f"{prefix}/{source.relative_to(snapshot_root).as_posix()}"
                    for relative_root in (
                        "Core/Src", "FATFS/App", "FATFS/Target"
                    )
                    for directory in (
                        snapshot_root.joinpath(*relative_root.split("/")),
                    )
                    if directory.is_dir() and not directory.is_symlink()
                    for source in sorted(directory.glob("*.c"))
                    if source.is_file()
                    and source.name.casefold() not in {"freertos.c", "sysmem.c"}
                )
                include_dirs = tuple(
                    f"{prefix}/{relative_root}"
                    for relative_root in (
                        "Core/Inc", "FATFS/App", "FATFS/Target"
                    )
                    if snapshot_root.joinpath(
                        *relative_root.split("/")
                    ).is_dir()
                )
                model.hardware = replace(
                    model.hardware,
                    cubemx_version=inventory.cubemx_version,
                    firmware_package=inventory.firmware_package,
                    inventory=inventory.Dictionary_Get(),
                    resources=inventory.HardwareResources_Get(),
                    build_sources=build_sources,
                    asm_sources=(),
                    include_dirs=include_dirs,
                    linker_script="",
                )
    return model


def ProjectModel_Save(model: ProjectModel, path: Path, policy: WorkspacePolicy) -> Path:
    serialized = json.dumps(
        model.Dictionary_Get(), ensure_ascii=False, indent=2, sort_keys=False
    ) + "\n"
    return policy.Text_AtomicWrite(path, serialized)
