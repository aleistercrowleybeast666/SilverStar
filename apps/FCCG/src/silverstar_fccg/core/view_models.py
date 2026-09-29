from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from silverstar_fccg.app.version import SILVERSTAR_PLATFORM_VERSION


class ComponentType(StrEnum):
    CORE = "core"
    PLATFORM_API = "platform_api"
    MCU_FAMILY = "mcu_family"
    MCU = "mcu"
    BOARD = "board"
    DEVICE = "device"
    ALGORITHM = "algorithm"
    FLIGHT_LOGIC = "flight_logic"
    OS = "os"
    PROTOCOL = "protocol"
    HARDWARE_CONFIGURATION_PROVIDER = "hardware_configuration_provider"
    DEVELOPMENT_ENVIRONMENT = "development_environment"


@dataclass(frozen=True, slots=True)
class ResourceRequirementView:
    kind: str
    name: str
    key: str = ""
    display_name: str = ""
    contract_summary: str = ""
    assignment: str = ""
    recommended_assignment: str = ""
    candidates: tuple[str, ...] = ()
    required: bool = True
    mode: str = "exclusive"
    fixed: bool = False
    physical_resource: str = ""
    physical_details: str = ""
    pending_hardware_confirmation: bool = False
    validation_error: str = ""


@dataclass(frozen=True, slots=True)
class ComponentView:
    component_id: str
    name: str
    component_type: ComponentType
    version: str
    component_class: str = ""
    description: str = ""
    source: str = ""
    status: str = "available"
    dependencies: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    requirements: tuple[ResourceRequirementView, ...] = ()
    options: dict[str, Any] = field(default_factory=dict)
    selection_kind: str = ""
    selection_slot: str = ""
    selection_options: tuple[str, ...] = ()
    selection_default: tuple[str, ...] = ()
    allow_none: bool = False
    allow_multiple: bool = False
    ui_order: int = 100
    board_source_kind: str = ""
    board_verified: bool = False
    compatible_mcus: tuple[str, ...] = ()
    cardinality: str = "single"
    project_max: int = 1
    plugin_max: int = 0
    class_max: int = 0
    same_plugin_multiple: bool = False
    multi_instance_ready: bool = False
    vendor: str = ""
    physical_vendor: str = ""
    physical_model: str = ""
    chipset: str = ""
    driver: str = ""


@dataclass(frozen=True, slots=True)
class DeviceInstanceView:
    instance_id: str
    plugin_id: str
    name: str
    component_class: str
    provides: tuple[str, ...]
    consumed: tuple[str, ...]
    unused: tuple[str, ...]
    enabled: tuple[str, ...] = ()
    unqualified: tuple[str, ...] = ()
    required: bool = False
    required_capabilities: tuple[str, ...] = ()
    project_max: int = 1
    plugin_max: int = 0
    class_max: int = 0
    same_plugin_multiple: bool = False
    multi_instance_ready: bool = False
    initialization: dict[str, Any] = field(default_factory=dict)
    runtime_defaults: dict[str, Any] = field(default_factory=dict)
    interface: str = ""
    profile: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityUsageView:
    capability: str
    kind: str = "raw_data"
    source_instance_id: str = ""
    source_name: str = ""
    used: bool = False
    missing: bool = False
    ambiguous: bool = False
    consumers: tuple[str, ...] = ()
    purposes: tuple[str, ...] = ()
    providers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class BoardCompatibilityView:
    component_id: str
    name: str
    compatible: bool
    missing_text: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ToolchainToolView:
    tool_id: str
    display_name: str
    command: str
    path: str = ""
    version: str = ""
    status: str = "not_checked"
    target: str = ""


@dataclass(frozen=True, slots=True)
class LoggingStreamView:
    stream_id: str
    name: str
    enabled: bool
    purpose: str
    decimation: int = 1
    cadence_kind: str = ""
    cadence_text: str = ""
    cadence_source: str = ""
    description: str = ""
    policy: str = ""
    period_us: int = 0
    level: str = "recommended"
    required: bool = False
    available: bool = True
    availability_reason: str = ""
    record_id: str = ""
    version: int = 0
    payload_size: int = 0


@dataclass(frozen=True, slots=True)
class ProtocolProfileView:
    component_id: str
    profile_id: str
    display_name: str
    component_name: str = ""
    version: str = ""
    available: bool = True
    availability_reason: str = ""


@dataclass(frozen=True, slots=True)
class PlatformMatchView:
    hardware_source: str = ""
    detected_part: str = ""
    detected_family: str = ""
    detected_package: str = ""
    detected_core: str = ""
    cubemx_version: str = ""
    firmware_package: str = ""
    source_policy: str = ""
    timebase_status: str = ""
    storage_status: str = ""
    i2c_status: str = ""
    pwm_status: str = ""
    can_status: str = ""
    component_id: str = ""
    component_name: str = ""
    reason: str = ""
    priority: int = 0
    specificity: int = 0
    verification: str = ""
    provenance: str = ""
    valid: bool = False
    error: str = ""


@dataclass(frozen=True, slots=True)
class I2cPullupEvidenceView:
    resource_id: str
    physical_resource: str
    pins_text: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class PlanOperationView:
    operation: str
    target: str
    detail: str = ""
    severity: str = "info"


@dataclass(slots=True)
class ProjectDraftView:
    name: str = ""
    output_directory: Path | None = None
    firmware_version: str = SILVERSTAR_PLATFORM_VERSION
    core_component_id: str = ""
    selected_component_ids: list[str] = field(default_factory=list)
    resource_assignments: dict[str, str] = field(default_factory=dict)
    logging: dict[str, dict[str, Any]] = field(default_factory=dict)
    toolchain: dict[str, str] = field(default_factory=dict)
    status: str = "not_created"
