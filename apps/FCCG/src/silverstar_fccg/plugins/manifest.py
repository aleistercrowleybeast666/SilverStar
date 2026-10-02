from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.workspace import (
    PortableRelativePath_Validate,
    WorkspacePolicyError,
)
from silverstar_fccg.plugins.algorithm_parameters import (
    AlgorithmParameterDefinition,
    AlgorithmParameters_Parse,
)
from silverstar_fccg.plugins.recommendations import SensorRecommendations_Parse

PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][0-9A-Za-z.-]+)?$")
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESOURCE_ROLE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*:[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)
BINDING_MACRO_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFINE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_+.,:/()|-]+)?$"
)
BUILD_TOKEN_PATTERN = re.compile(r"^[-A-Za-z0-9_+.,=:/]+$")
BUILD_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./+@-]+$")
TOOLCHAIN_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_.+-]*$")
SELECTION_OPTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
BUILD_TARGET_PROFILE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")

ALLOWED_PLUGIN_TYPES = frozenset(
    {
        "core",
        "mcu",
        "mcu_family",
        "platform_api",
        "board",
        "device",
        "algorithm",
        "flight_logic",
        "os",
        "protocol",
        "hardware_configuration_provider",
        "development_environment",
    }
)
UTILITY_PLUGIN_TYPES = frozenset(
    {"hardware_configuration_provider", "development_environment"}
)
ALLOWED_BOARD_SOURCE_KINDS = frozenset(
    {"verified_builtin", "manual_import", "third_party"}
)
ALLOWED_PROVIDER_HANDLERS = frozenset({"stm32_cubemx"})
ALLOWED_ENVIRONMENT_RENDERERS = frozenset({"vscode_eide_gcc"})
ALLOWED_DEVICE_CARDINALITIES = frozenset({"single", "multiple"})
ALLOWED_PROTOCOL_CATEGORIES = frozenset(
    {"telemetry", "maintenance", "logging"}
)
DEVICE_CATEGORY_PATTERN = re.compile(
    r"^(?:sensor|link|storage|actuator|indicator)\."
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*$"
)


class PluginManifestError(FccgError):
    pass


class ResourceMode(StrEnum):
    EXCLUSIVE = "exclusive"
    SHARED = "shared"


class SelectionKind(StrEnum):
    STRATEGY = "strategy"
    MODE = "mode"


@dataclass(frozen=True, slots=True)
class ComponentRequirement:
    component_id: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    capability: str
    purpose: str = "runtime"


@dataclass(frozen=True, slots=True)
class SelectionOptionRequirements:
    capabilities: tuple[CapabilityRequirement, ...] = ()
    components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModeParameterDefinition:
    parameter_id: str
    value_type: str
    default: float | int
    minimum: float | int
    maximum: float | int
    unit: str
    generated_symbol: str
    generated_scale: float = 1.0
    display_names: dict[str, str] = field(default_factory=dict)

    def DisplayName_Get(self, language: str) -> str:
        return self.display_names.get(
            language, self.parameter_id.replace("_", " ")
        )


@dataclass(frozen=True, slots=True)
class DeviceInstancePolicy:
    plugin_max: int = 1
    class_max: int = 1
    same_plugin_multiple: bool = False
    multi_instance_ready: bool = False

    @property
    def project_max(self) -> int:
        """Compatibility alias for pre-format plugin manifests and callers."""
        return self.class_max


@dataclass(frozen=True, slots=True)
class InstanceResourceField:
    requirement: str
    member: str


@dataclass(frozen=True, slots=True)
class InstanceResourceBinding:
    struct_type: str
    accessor: str
    count_symbol: str
    runtime_context_upper_bound: int
    fields: tuple[InstanceResourceField, ...]


@dataclass(frozen=True, slots=True)
class PhysicalDeviceContribution:
    vendor: str
    model: str
    chipset: str
    driver: str


@dataclass(frozen=True, slots=True)
class RadioContribution:
    technology: str
    family: str
    phy_modes: tuple[str, ...]
    frequency_min_hz: int
    frequency_max_hz: int
    bandwidths_hz: tuple[int, ...]
    spreading_factors: tuple[int, ...]
    coding_rates: tuple[str, ...]
    maximum_payload: int
    maximum_tx_power_dbm: int
    datasheet_capabilities: dict[str, Any]
    modules: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    name: str
    kind: str
    binding_macro: str = ""
    required: bool = True
    mode: ResourceMode = ResourceMode.EXCLUSIVE
    candidates: tuple[str, ...] = ()
    platform_capabilities: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    electrical_constraints: dict[str, Any] = field(default_factory=dict)
    display_names: dict[str, str] = field(default_factory=dict)

    def DisplayName_Get(self, language: str) -> str:
        localized = self.display_names.get(language)
        return localized if localized else self.name.replace("_", " ")


@dataclass(frozen=True, slots=True)
class ResourceProvision:
    resource_id: str
    kind: str
    capabilities: tuple[str, ...] = ()
    reserved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResourceRole:
    key: str
    kind: str
    default: str
    candidates: tuple[str, ...]
    fixed: bool = False


@dataclass(frozen=True, slots=True)
class ResourceConflict:
    resources: tuple[str, ...]
    message: str = ""


@dataclass(frozen=True, slots=True)
class SelectionContribution:
    kind: SelectionKind
    slot: str
    required: bool
    allow_none: bool
    allow_multiple: bool
    ui_order: int
    options: tuple[str, ...] = ()
    default: tuple[str, ...] = ()
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    option_requirements: dict[str, SelectionOptionRequirements] = field(
        default_factory=dict
    )
    parameters: dict[str, tuple[ModeParameterDefinition, ...]] = field(
        default_factory=dict
    )
    option_symbols: dict[str, str] = field(default_factory=dict)
    aggregate_symbol: str = ""
    none_defines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardContribution:
    source_kind: str
    compatible_mcus: tuple[str, ...]
    vendor: str
    provider: str
    verified: bool
    hardware_root: str
    ioc_file: str = ""
    connections_file: str = ""


@dataclass(frozen=True, slots=True)
class ProtocolTransportConstraint:
    capability: str
    kind: str
    minimum_mtu: int
    ordered: bool
    bidirectional: bool
    reliable: bool
    mode: str


@dataclass(frozen=True, slots=True)
class TransportContribution:
    capability: str
    kind: str
    mtu: int
    ordered: bool
    bidirectional: bool
    reliable: bool
    mode: str


@dataclass(frozen=True, slots=True)
class ProtocolProfileContribution:
    profile_id: str
    version: str
    display_names: dict[str, str] = field(default_factory=dict)
    service: str = ""
    slot: str = ""
    codec_sources: tuple[str, ...] = ()
    parser_sources: tuple[str, ...] = ()
    include_dirs: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()
    binding: str = ""
    transport_selection: str = "single"
    transport: ProtocolTransportConstraint | None = None
    decoder_metadata: str = ""
    documentation: tuple[str, ...] = ()
    host_tests: tuple[str, ...] = ()
    golden_tests: tuple[str, ...] = ()

    def DisplayName_Get(self, language: str) -> str:
        return self.display_names.get(language, self.profile_id)


@dataclass(frozen=True, slots=True)
class ProtocolContribution:
    category: str
    logging_metadata: str
    maintenance_protocol_version: str
    firmware_version: str
    documentation_version: str
    profiles: dict[str, tuple[ProtocolProfileContribution, ...]] = field(
        default_factory=dict
    )
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlatformMatchRule:
    vendor: str
    exact_part: str = ""
    family_pattern: str = ""
    package_pattern: str = ""
    core_pattern: str = ""
    priority: int = 0
    specificity: int = 0
    verification: str = "experimental"


@dataclass(frozen=True, slots=True)
class PlatformResourceBinding:
    kind: str
    collection: str
    include_header: str
    entry_kind: str
    id_type: str
    count_symbol: str
    table_symbol: str
    getter: str
    struct_type: str = ""


@dataclass(frozen=True, slots=True)
class PlatformBackendContribution:
    backend_id: str
    inventory_kinds: tuple[str, ...]
    sources: tuple[str, ...]
    provider_sources: tuple[str, ...]
    include_dirs: tuple[str, ...]
    defines: tuple[str, ...]
    capabilities: tuple[str, ...]
    ownership: str
    maturity: str


@dataclass(frozen=True, slots=True)
class PlatformModuleProviderContribution:
    provider_id: str
    inventory_modules: tuple[str, ...]
    init_sources: tuple[str, ...]
    provider_sources: tuple[str, ...]
    middleware_sources: tuple[str, ...]
    include_dirs: tuple[str, ...]
    defines: tuple[str, ...]
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    always: bool


@dataclass(frozen=True, slots=True)
class PlatformCompatibilityContribution:
    cubemx_versions: tuple[str, ...]
    firmware_packages: tuple[str, ...]
    source_policy: str


@dataclass(frozen=True, slots=True)
class PlatformContribution:
    abi_id: str
    abi_major: int
    abi_minor: int
    provider: str
    build_target_profile: str
    match_rules: tuple[PlatformMatchRule, ...]
    resource_header: str
    resource_bindings: dict[str, PlatformResourceBinding]
    resource_backends: dict[str, PlatformBackendContribution]
    module_providers: dict[str, PlatformModuleProviderContribution]
    compatibility: PlatformCompatibilityContribution
    support_level: str
    limitations: tuple[str, ...]


PROTOCOL_PROFILE_SLOTS = {
    "telemetry": "telemetry_protocol",
    "maintenance": "maintenance_protocol",
    "logging": "log_format",
}


@dataclass(frozen=True, slots=True)
class HardwareProviderContribution:
    vendor: str
    handler: str
    accepted_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentContribution:
    renderer: str
    toolchain: str
    outputs: tuple[str, ...]
    tasks: tuple[str, ...]
    eide_native: bool


@dataclass(frozen=True, slots=True)
class BuildContribution:
    sources: tuple[str, ...] = ()
    protocol_sources: dict[str, tuple[str, ...]] = field(default_factory=dict)
    strategy_sources: dict[str, dict[str, tuple[str, ...]]] = field(
        default_factory=dict
    )
    asm_sources: tuple[str, ...] = ()
    include_dirs: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()
    mcu_flags: tuple[str, ...] = ()
    specs: tuple[str, ...] = ()
    libraries: tuple[str, ...] = ()
    forced_includes: tuple[str, ...] = ()
    virtual_sources: tuple[str, ...] = ()
    exclude_sources: tuple[str, ...] = ()
    linker_script: str = ""
    toolchain_prefix: str = ""


@dataclass(frozen=True, slots=True)
class PluginManifest:
    schema_version: int
    component_id: str
    name: str
    component_type: str
    component_class: str
    version: str
    description: str
    dependencies: tuple[ComponentRequirement, ...]
    resource_requirements: tuple[ResourceRequirement, ...]
    resource_provisions: tuple[ResourceProvision, ...]
    resource_roles: tuple[ResourceRole, ...]
    resource_conflicts: tuple[ResourceConflict, ...]
    provides: tuple[str, ...]
    capability_requirements: tuple[CapabilityRequirement, ...]
    transports: tuple[TransportContribution, ...]
    build: BuildContribution
    payload_roots: tuple[str, ...]
    metadata: dict[str, Any]
    manifest_path: Path
    instance_policy: DeviceInstancePolicy = DeviceInstancePolicy()
    instance_resource_binding: InstanceResourceBinding | None = None
    physical_device: PhysicalDeviceContribution | None = None
    radio: RadioContribution | None = None
    selection: SelectionContribution | None = None
    board: BoardContribution | None = None
    protocol: ProtocolContribution | None = None
    platform: PlatformContribution | None = None
    hardware_provider: HardwareProviderContribution | None = None
    environment: EnvironmentContribution | None = None
    algorithm_parameters: tuple[AlgorithmParameterDefinition, ...] = ()
    source: str = "builtin"
    device_variants: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def capabilities_required(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                requirement.capability
                for requirement in self.capability_requirements
            )
        )

    @property
    def cardinality(self) -> str:
        return "multiple" if self.instance_policy.project_max > 1 else "single"

    @property
    def package_root(self) -> Path:
        return self.manifest_path.parent

    @property
    def payload_root(self) -> Path:
        return self.package_root / "payload"

    def DisplayName_Get(self, language: str) -> str:
        values = self.metadata.get("display_names", {})
        if isinstance(values, dict):
            localized = values.get(language)
            if isinstance(localized, str) and localized.strip():
                return localized
        return self.name

    def Description_Get(self, language: str) -> str:
        values = self.metadata.get("descriptions", {})
        if isinstance(values, dict):
            localized = values.get(language)
            if isinstance(localized, str) and localized.strip():
                return localized
        return self.description

    def PayloadFiles_Get(self) -> tuple[Path, ...]:
        files: list[Path] = []
        for root_name in self.payload_roots:
            root = self.payload_root.joinpath(*root_name.split("/"))
            if root.is_symlink():
                raise PluginManifestError(
                    f"Plugin payload root is a symlink: {root_name}"
                )
            if root.is_file():
                if not PayloadCachePath_Is(root.relative_to(self.payload_root)):
                    files.append(root)
            elif root.is_dir():
                for path in sorted(root.rglob("*")):
                    if path.is_symlink():
                        raise PluginManifestError(
                            f"Plugin payload contains a symlink: {path}"
                        )
                    if path.is_file() and not PayloadCachePath_Is(path.relative_to(self.payload_root)):
                        files.append(path)
            else:
                raise PluginManifestError(f"Missing payload root: {root_name}")
        unique = {
            path.relative_to(self.payload_root).as_posix(): path for path in files
        }
        return tuple(unique[name] for name in sorted(unique))

    def ManifestSha256_Get(self) -> str:
        return hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()


def PayloadCachePath_Is(relative: str | Path) -> bool:
    """Only Python cache artifacts; unsafe ownership paths are never ignored."""
    text = str(relative).replace("\\", "/")
    portable = PurePosixPath(text)
    if portable.is_absolute() or any(part == ".." or ":" in part for part in portable.parts):
        return False
    return "__pycache__" in portable.parts or portable.suffix.casefold() in {".pyc", ".pyo"}


def _StringTuple_Get(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and bool(item) for item in value
    ):
        raise PluginManifestError(f"{field_name} must be an array of strings")
    if len(value) != len(set(value)):
        raise PluginManifestError(f"{field_name} contains duplicate values")
    return tuple(value)


def _Boolean_Get(data: dict[str, Any], field_name: str, default: bool) -> bool:
    if field_name not in data:
        return default
    value = data[field_name]
    if not isinstance(value, bool):
        raise PluginManifestError(f"{field_name} must be a boolean")
    return value


def _CapabilityTuple_Validate(values: tuple[str, ...], field_name: str) -> None:
    invalid = [value for value in values if not PLUGIN_ID_PATTERN.fullmatch(value)]
    if invalid:
        raise PluginManifestError(
            f"{field_name} contains invalid capability: {invalid[0]!r}"
        )


def _CapabilityRequirements_Parse(value: Any) -> tuple[CapabilityRequirement, ...]:
    if not isinstance(value, list):
        raise PluginManifestError("requires.capabilities must be an array")
    requirements: list[CapabilityRequirement] = []
    identities: set[tuple[str, str]] = set()
    for entry in value:
        if isinstance(entry, str):
            capability = entry
            purpose = "runtime"
        elif isinstance(entry, dict) and set(entry) == {"capability", "purpose"}:
            capability = entry.get("capability")
            purpose = entry.get("purpose")
        else:
            raise PluginManifestError(
                "requires.capabilities entries must be strings or "
                "capability/purpose objects"
            )
        if not isinstance(capability, str) or not PLUGIN_ID_PATTERN.fullmatch(
            capability
        ):
            raise PluginManifestError(
                f"requires.capabilities contains invalid capability: {capability!r}"
            )
        if not isinstance(purpose, str) or not PLUGIN_ID_PATTERN.fullmatch(purpose):
            raise PluginManifestError(
                f"requires.capabilities contains invalid purpose: {purpose!r}"
            )
        identity = (capability, purpose)
        if identity in identities:
            raise PluginManifestError(
                "requires.capabilities contains duplicate capability/purpose"
            )
        identities.add(identity)
        requirements.append(CapabilityRequirement(capability, purpose))
    return tuple(requirements)


def _InstancePolicy_Parse(
    value: Any, *, component_type: str, legacy_cardinality: Any
) -> DeviceInstancePolicy:
    if component_type != "device":
        if value is not None or legacy_cardinality is not None:
            raise PluginManifestError(
                "only device plugins may declare instance_policy/cardinality"
            )
        return DeviceInstancePolicy()
    if value is not None and legacy_cardinality is not None:
        raise PluginManifestError(
            "device plugin cannot declare both instance_policy and cardinality"
        )
    if value is None:
        if legacy_cardinality is None:
            raise PluginManifestError(
                "device plugin must declare instance_policy"
            )
        if legacy_cardinality not in ALLOWED_DEVICE_CARDINALITIES:
            raise PluginManifestError("cardinality must be single or multiple")
        return DeviceInstancePolicy(
            plugin_max=1,
            class_max=16 if legacy_cardinality == "multiple" else 1,
            same_plugin_multiple=False,
            multi_instance_ready=False,
        )
    if not isinstance(value, dict) or set(value) not in (
        {"project_max", "same_plugin_multiple"},
        {"project_max", "same_plugin_multiple", "multi_instance_ready"},
        {"plugin_max", "class_max", "same_plugin_multiple"},
        {
            "plugin_max",
            "class_max",
            "same_plugin_multiple",
            "multi_instance_ready",
        },
    ):
        raise PluginManifestError(
            "instance_policy must contain plugin_max, class_max, "
            "same_plugin_multiple and optionally multi_instance_ready"
        )
    legacy_project_max = value.get("project_max")
    same_plugin_multiple = value.get("same_plugin_multiple")
    multi_instance_ready = value.get("multi_instance_ready", False)
    plugin_max = (
        legacy_project_max if same_plugin_multiple else 1
    ) if legacy_project_max is not None else value.get("plugin_max")
    class_max = (
        legacy_project_max
        if legacy_project_max is not None
        else value.get("class_max")
    )
    if any(
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 64
        for limit in (plugin_max, class_max)
    ):
        raise PluginManifestError(
            "instance_policy plugin_max/class_max must be integers from 1 to 64"
        )
    if not isinstance(same_plugin_multiple, bool):
        raise PluginManifestError(
            "instance_policy.same_plugin_multiple must be boolean"
        )
    if not isinstance(multi_instance_ready, bool):
        raise PluginManifestError(
            "instance_policy.multi_instance_ready must be boolean"
        )
    assert isinstance(plugin_max, int)
    assert isinstance(class_max, int)
    if plugin_max > class_max:
        raise PluginManifestError(
            "instance_policy.plugin_max cannot exceed class_max"
        )
    if plugin_max == 1 and same_plugin_multiple:
        raise PluginManifestError(
            "same_plugin_multiple cannot be true when plugin_max is 1"
        )
    if plugin_max > 1 and not same_plugin_multiple:
        raise PluginManifestError(
            "plugin_max greater than 1 requires same_plugin_multiple"
        )
    if same_plugin_multiple and not multi_instance_ready:
        raise PluginManifestError(
            "same_plugin_multiple requires multi_instance_ready"
        )
    if class_max == 1 and multi_instance_ready:
        raise PluginManifestError(
            "multi_instance_ready cannot be true when class_max is 1"
        )
    return DeviceInstancePolicy(
        plugin_max, class_max, same_plugin_multiple, multi_instance_ready
    )


def _InstanceResourceBinding_Parse(
    value: Any,
    *,
    component_type: str,
    requirements: tuple[ResourceRequirement, ...],
    instance_policy: DeviceInstancePolicy,
) -> InstanceResourceBinding | None:
    if value is None:
        return None
    if component_type != "device":
        raise PluginManifestError(
            "only device plugins may declare metadata.instance_resource_binding"
        )
    required_fields = {
        "struct_type",
        "accessor",
        "count_symbol",
        "runtime_context_upper_bound",
        "fields",
    }
    if not isinstance(value, dict) or set(value) != required_fields:
        raise PluginManifestError(
            "metadata.instance_resource_binding has invalid fields"
        )
    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    macro = re.compile(r"^[A-Z][A-Z0-9_]*$")
    struct_type = value.get("struct_type")
    accessor = value.get("accessor")
    count_symbol = value.get("count_symbol")
    upper_bound = value.get("runtime_context_upper_bound")
    if (
        not isinstance(struct_type, str)
        or identifier.fullmatch(struct_type) is None
        or not isinstance(accessor, str)
        or identifier.fullmatch(accessor) is None
        or not isinstance(count_symbol, str)
        or macro.fullmatch(count_symbol) is None
        or isinstance(upper_bound, bool)
        or not isinstance(upper_bound, int)
        or upper_bound != instance_policy.plugin_max
    ):
        raise PluginManifestError(
            "metadata.instance_resource_binding contains unsafe C tokens or bounds"
        )
    fields_value = value.get("fields")
    if not isinstance(fields_value, list) or not fields_value:
        raise PluginManifestError(
            "metadata.instance_resource_binding.fields must be non-empty"
        )
    requirement_names = {requirement.name for requirement in requirements}
    fields: list[InstanceResourceField] = []
    seen_requirements: set[str] = set()
    seen_members: set[str] = set()
    for entry in fields_value:
        if not isinstance(entry, dict) or set(entry) != {"requirement", "member"}:
            raise PluginManifestError(
                "metadata.instance_resource_binding field is invalid"
            )
        requirement = entry.get("requirement")
        member = entry.get("member")
        if (
            not isinstance(requirement, str)
            or requirement not in requirement_names
            or requirement in seen_requirements
            or not isinstance(member, str)
            or identifier.fullmatch(member) is None
            or member in seen_members
        ):
            raise PluginManifestError(
                "metadata.instance_resource_binding field is invalid"
            )
        seen_requirements.add(requirement)
        seen_members.add(member)
        fields.append(InstanceResourceField(requirement, member))
    if seen_requirements != requirement_names:
        raise PluginManifestError(
            "metadata.instance_resource_binding must map every resource requirement"
        )
    return InstanceResourceBinding(
        struct_type=struct_type,
        accessor=accessor,
        count_symbol=count_symbol,
        runtime_context_upper_bound=upper_bound,
        fields=tuple(fields),
    )


def _PhysicalDevice_Parse(
    value: Any, *, component_type: str
) -> PhysicalDeviceContribution | None:
    if value is None:
        if component_type == "device":
            raise PluginManifestError(
                "device plugin must declare physical_device"
            )
        return None
    if component_type != "device":
        raise PluginManifestError("only device plugins may declare physical_device")
    if not isinstance(value, dict) or set(value) != {
        "vendor",
        "model",
        "chipset",
        "driver",
    }:
        raise PluginManifestError(
            "physical_device must contain vendor, model, chipset and driver"
        )
    fields = tuple(value.get(name) for name in ("vendor", "model", "chipset", "driver"))
    if not all(isinstance(field_value, str) and field_value.strip() for field_value in fields):
        raise PluginManifestError("physical_device fields must be non-empty strings")
    return PhysicalDeviceContribution(*fields)


def _BuildTokens_Validate(
    values: tuple[str, ...], field_name: str, pattern: re.Pattern[str]
) -> None:
    invalid = [value for value in values if not pattern.fullmatch(value)]
    if invalid:
        raise PluginManifestError(
            f"{field_name} contains an unsafe token: {invalid[0]!r}"
        )


def _RelativePaths_Validate(paths: tuple[str, ...], field_name: str) -> None:
    for value in paths:
        try:
            PortableRelativePath_Validate(value)
        except WorkspacePolicyError as error:
            raise PluginManifestError(
                f"Invalid {field_name} path {value!r}"
            ) from error


def _Dependencies_Parse(requires: dict[str, Any]) -> tuple[ComponentRequirement, ...]:
    dependencies: list[ComponentRequirement] = []
    for entry in requires.get("components", []):
        if not isinstance(entry, dict) or set(entry) - {"id", "optional"}:
            raise PluginManifestError(
                "requires.components entries must contain id/optional"
            )
        dependency_id = entry.get("id")
        if not isinstance(dependency_id, str) or not PLUGIN_ID_PATTERN.fullmatch(
            dependency_id
        ):
            raise PluginManifestError(f"Invalid dependency id: {dependency_id!r}")
        dependencies.append(
            ComponentRequirement(
                dependency_id, _Boolean_Get(entry, "optional", False)
            )
        )
    ids = [dependency.component_id for dependency in dependencies]
    if len(ids) != len(set(ids)):
        raise PluginManifestError("requires.components contains duplicate ids")
    return tuple(dependencies)


def _PositiveInteger_Validate(value: Any, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PluginManifestError(f"{field_name} must be a positive integer")


def _Number_Validate(
    value: Any, field_name: str, *, minimum: float = 0.0
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
    ):
        raise PluginManifestError(
            f"{field_name} must be a finite number >= {minimum:g}"
        )


def _PositiveIntegerList_Validate(value: Any, field_name: str) -> None:
    if not isinstance(value, list) or not value:
        raise PluginManifestError(f"{field_name} must be a non-empty array")
    for entry in value:
        _PositiveInteger_Validate(entry, field_name)
    if len(value) != len(set(value)):
        raise PluginManifestError(f"{field_name} contains duplicate values")


def _BusConstraints_Validate(
    name: str, kind: str, constraints: dict[str, Any]
) -> None:
    legacy_fields = {
        "baud_rate",
        "mode",
        "signals",
        "dma_rx_required",
        "dma_tx_required",
        "irq_required",
        "pin_label",
    }
    typed_fields = {"uart", "spi", "i2c", "can", "pwm", "storage"}
    unknown = set(constraints) - legacy_fields - typed_fields
    if unknown:
        raise PluginManifestError(
            f"Resource constraints for {name} contain unknown fields: "
            + ", ".join(sorted(unknown))
        )
    typed = set(constraints).intersection(typed_fields)
    if len(typed) > 1:
        raise PluginManifestError(
            f"Resource constraints for {name} declare multiple bus types"
        )
    typed_kind = next(iter(typed), "")
    kind_matches = (
        not typed
        or kind == typed_kind
        or (typed_kind == "can" and kind in {"can_classic", "can_fd"})
        or (typed_kind == "storage" and kind == "sdio")
    )
    if not kind_matches:
        raise PluginManifestError(
            f"Resource constraints for {name} declare {next(iter(typed))} "
            f"for a {kind} requirement"
        )
    baud_rate = constraints.get("baud_rate")
    if baud_rate is not None:
        _PositiveInteger_Validate(
            baud_rate, f"Resource baud_rate constraint for {name}"
        )
    constraint_mode = constraints.get("mode")
    pin_label = constraints.get("pin_label")
    if pin_label is not None and (
        kind not in {"gpio_input", "gpio_interrupt", "gpio_output"}
        or not isinstance(pin_label, str)
        or not pin_label.strip()
    ):
        raise PluginManifestError(
            f"Resource pin_label constraint for {name} requires a non-empty GPIO net label"
        )
    if constraint_mode is not None and (
        not isinstance(constraint_mode, str) or not constraint_mode
    ):
        raise PluginManifestError(
            f"Resource mode constraint for {name} must be a non-empty string"
        )
    signals = constraints.get("signals")
    if signals is not None:
        _StringTuple_Get(signals, f"resource signals for {name}")
        if len(signals) != len(set(signals)):
            raise PluginManifestError(
                f"Resource signal constraints for {name} contain duplicates"
            )
    for flag in ("dma_rx_required", "dma_tx_required", "irq_required"):
        if flag in constraints and not isinstance(constraints[flag], bool):
            raise PluginManifestError(
                f"Resource {flag} constraint for {name} must be a boolean"
            )
    if not typed:
        return
    bus_name = next(iter(typed))
    bus = constraints[bus_name]
    if not isinstance(bus, dict):
        raise PluginManifestError(
            f"Resource {bus_name} constraints for {name} must be an object"
        )
    allowed_fields = {
        "uart": {
            "baud",
            "word_length",
            "parity",
            "stop_bits",
            "rx_dma",
            "tx_dma",
            "irq",
        },
        "spi": {
            "mode",
            "cpol",
            "cpha",
            "data_bits",
            "bit_order",
            "minimum_clock_hz",
            "maximum_clock_hz",
            "dma",
            "irq",
        },
        "i2c": {
            "maximum_bus_frequency_hz",
            "allowed_rates_hz",
            "address_mode",
            "address_7bit",
            "composite_device",
            "requires_repeated_start",
            "required_pullup",
            "dma",
            "irq",
        },
        "can": {
            "minimum_nominal_bitrate",
            "maximum_nominal_bitrate",
            "allowed_nominal_bitrates",
            "frame_format",
            "mode",
            "irq",
        },
        "pwm": {
            "frequency_hz",
            "minimum_frequency_hz",
            "maximum_frequency_hz",
            "minimum_resolution_bits",
            "channel",
            "safe_state",
        },
        "storage": {
            "fatfs",
            "dma_rx",
            "dma_tx",
            "irq",
            "sdio_only",
        },
    }[bus_name]
    unknown_bus_fields = set(bus) - allowed_fields
    if unknown_bus_fields:
        raise PluginManifestError(
            f"Resource {bus_name} constraints for {name} contain unknown fields: "
            + ", ".join(sorted(unknown_bus_fields))
        )
    if bus_name == "uart":
        baud = bus.get("baud")
        if not isinstance(baud, dict) or set(baud) - {
            "exact",
            "allowed_values",
            "configurable",
        }:
            raise PluginManifestError(
                f"Resource UART baud constraint for {name} is invalid"
            )
        if "exact" not in baud and "allowed_values" not in baud:
            raise PluginManifestError(
                f"Resource UART baud constraint for {name} needs exact or allowed_values"
            )
        if "exact" in baud:
            _PositiveInteger_Validate(baud["exact"], f"UART baud.exact for {name}")
        if "allowed_values" in baud:
            _PositiveIntegerList_Validate(
                baud["allowed_values"], f"UART baud.allowed_values for {name}"
            )
        if "configurable" in baud and not isinstance(baud["configurable"], bool):
            raise PluginManifestError(
                f"UART baud.configurable for {name} must be a boolean"
            )
        if "word_length" in bus:
            _PositiveInteger_Validate(bus["word_length"], f"UART word_length for {name}")
        if "stop_bits" in bus:
            _Number_Validate(bus["stop_bits"], f"UART stop_bits for {name}", minimum=0.5)
    elif bus_name == "spi":
        for field_name in ("data_bits", "minimum_clock_hz", "maximum_clock_hz"):
            if field_name in bus:
                _PositiveInteger_Validate(bus[field_name], f"SPI {field_name} for {name}")
        if (
            "minimum_clock_hz" in bus
            and "maximum_clock_hz" in bus
            and bus["minimum_clock_hz"] > bus["maximum_clock_hz"]
        ):
            raise PluginManifestError(f"SPI clock range for {name} is reversed")
    elif bus_name == "i2c":
        if "maximum_bus_frequency_hz" in bus:
            _PositiveInteger_Validate(
                bus["maximum_bus_frequency_hz"],
                f"I2C maximum_bus_frequency_hz for {name}",
            )
        if "allowed_rates_hz" in bus:
            _PositiveIntegerList_Validate(
                bus["allowed_rates_hz"], f"I2C allowed_rates_hz for {name}"
            )
        if "address_7bit" in bus and (
            not isinstance(bus["address_7bit"], int)
            or isinstance(bus["address_7bit"], bool)
            or not 0x08 <= bus["address_7bit"] <= 0x77
        ):
            raise PluginManifestError(
                f"I2C address_7bit for {name} must be between 0x08 and 0x77"
            )
        if bus.get("address_mode", "7bit") != "7bit":
            raise PluginManifestError(
                f"I2C address_mode for {name} must be 7bit"
            )
        composite_device = bus.get("composite_device")
        if composite_device is not None and (
            not isinstance(composite_device, str)
            or PLUGIN_ID_PATTERN.fullmatch(composite_device) is None
        ):
            raise PluginManifestError(
                f"I2C composite_device for {name} must be a lower-case identifier"
            )
    elif bus_name == "can":
        for field_name in (
            "minimum_nominal_bitrate",
            "maximum_nominal_bitrate",
        ):
            if field_name in bus:
                _PositiveInteger_Validate(bus[field_name], f"CAN {field_name} for {name}")
        if "allowed_nominal_bitrates" in bus:
            _PositiveIntegerList_Validate(
                bus["allowed_nominal_bitrates"],
                f"CAN allowed_nominal_bitrates for {name}",
            )
        if (
            "minimum_nominal_bitrate" in bus
            and "maximum_nominal_bitrate" in bus
            and bus["minimum_nominal_bitrate"] > bus["maximum_nominal_bitrate"]
        ):
            raise PluginManifestError(f"CAN bitrate range for {name} is reversed")
        expected_format = "classic" if kind == "can_classic" else "fd"
        if bus.get("frame_format", expected_format) != expected_format:
            raise PluginManifestError(
                f"CAN frame_format for {name} must be {expected_format}"
            )
    elif bus_name == "pwm":
        for field_name in (
            "frequency_hz",
            "minimum_frequency_hz",
            "maximum_frequency_hz",
            "minimum_resolution_bits",
            "channel",
        ):
            if field_name in bus:
                _PositiveInteger_Validate(bus[field_name], f"PWM {field_name} for {name}")
        if (
            "minimum_frequency_hz" in bus
            and "maximum_frequency_hz" in bus
            and bus["minimum_frequency_hz"] > bus["maximum_frequency_hz"]
        ):
            raise PluginManifestError(f"PWM frequency range for {name} is reversed")
    for field_name, field_value in bus.items():
        if field_name in {"baud", "word_length", "stop_bits"}:
            continue
        if field_name in {
            "rx_dma",
            "tx_dma",
            "irq",
            "dma",
            "required_pullup",
            "requires_repeated_start",
            "fatfs",
            "dma_rx",
            "dma_tx",
            "sdio_only",
        } and not isinstance(field_value, bool):
            raise PluginManifestError(
                f"Resource {bus_name}.{field_name} for {name} must be a boolean"
            )
        if field_name in {
            "parity",
            "mode",
            "cpol",
            "cpha",
            "bit_order",
            "address_mode",
            "composite_device",
            "frame_format",
            "safe_state",
        } and (not isinstance(field_value, str) or not field_value):
            raise PluginManifestError(
                f"Resource {bus_name}.{field_name} for {name} must be text"
            )


def _ElectricalConstraints_Validate(
    name: str, electrical: dict[str, Any]
) -> None:
    allowed = {
        "mode",
        "output_type",
        "pull",
        "allowed_pulls",
        "speed",
        "safe_initial_level",
        "active_polarity",
        "exti_trigger",
        "alternate_function",
        "irq",
        "maximum_irq_priority",
        "startup_glitch_free",
    }
    unknown = set(electrical) - allowed
    if unknown:
        raise PluginManifestError(
            f"Electrical constraints for {name} contain unknown fields: "
            + ", ".join(sorted(unknown))
        )
    allowed_values = {
        "mode": {"gpio_output", "gpio_input", "gpio_interrupt", "alternate_function"},
        "output_type": {"push_pull", "open_drain"},
        "pull": {"none", "up", "down"},
        "speed": {"low", "medium", "high", "very_high"},
        "safe_initial_level": {"inactive", "active", "low", "high"},
        "active_polarity": {"low", "high"},
        "exti_trigger": {"rising", "falling", "both"},
    }
    for field_name, accepted in allowed_values.items():
        if field_name in electrical and electrical[field_name] not in accepted:
            raise PluginManifestError(
                f"Electrical {field_name} for {name} is invalid"
            )
    if "allowed_pulls" in electrical:
        pulls = electrical["allowed_pulls"]
        if (
            "pull" in electrical
            or not isinstance(pulls, list)
            or not pulls
            or any(not isinstance(value, str) for value in pulls)
            or len(pulls) != len(set(pulls))
            or any(value not in allowed_values["pull"] for value in pulls)
        ):
            raise PluginManifestError(
                f"Electrical allowed_pulls for {name} must be distinct valid pulls without pull"
            )
    for flag in ("irq", "startup_glitch_free"):
        if flag in electrical and not isinstance(electrical[flag], bool):
            raise PluginManifestError(
                f"Electrical {flag} for {name} must be a boolean"
            )
    if "maximum_irq_priority" in electrical:
        value = electrical["maximum_irq_priority"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PluginManifestError(
                f"Electrical maximum_irq_priority for {name} must be a non-negative integer"
            )
    if "alternate_function" in electrical and (
        not isinstance(electrical["alternate_function"], str)
        or not electrical["alternate_function"]
    ):
        raise PluginManifestError(
            f"Electrical alternate_function for {name} must be text"
        )


def _ResourceRequirements_Parse(
    requires: dict[str, Any],
) -> tuple[ResourceRequirement, ...]:
    requirements: list[ResourceRequirement] = []
    for entry in requires.get("resources", []):
        if not isinstance(entry, dict):
            raise PluginManifestError("requires.resources entries must be objects")
        if set(entry) - {
            "name",
            "kind",
            "binding_macro",
            "required",
            "mode",
            "candidates",
            "platform_capabilities",
            "constraints",
            "electrical_constraints",
            "display_names",
        }:
            raise PluginManifestError("resource requirement contains unknown fields")
        name = entry.get("name")
        kind = entry.get("kind")
        if not isinstance(name, str) or not PLUGIN_ID_PATTERN.fullmatch(name):
            raise PluginManifestError(
                f"Invalid resource requirement name: {name!r}"
            )
        if not isinstance(kind, str) or not PLUGIN_ID_PATTERN.fullmatch(kind):
            raise PluginManifestError(f"Invalid resource kind: {kind!r}")
        try:
            mode = ResourceMode(entry.get("mode", "exclusive"))
        except ValueError as error:
            raise PluginManifestError(f"Invalid resource mode for {name}") from error
        candidates = _StringTuple_Get(
            entry.get("candidates", []), "resource candidates"
        )
        _BuildTokens_Validate(candidates, "resource candidates", RESOURCE_ID_PATTERN)
        platform_capabilities = _StringTuple_Get(
            entry.get("platform_capabilities", []),
            "resource platform_capabilities",
        )
        if any(
            PLUGIN_ID_PATTERN.fullmatch(capability) is None
            for capability in platform_capabilities
        ):
            raise PluginManifestError(
                f"Invalid resource platform capability for {name}"
            )
        if kind in {"i2c", "can_classic", "can_fd", "pwm"} and not (
            platform_capabilities
        ):
            raise PluginManifestError(
                f"Resource {name} ({kind}) must declare platform_capabilities; "
                "hardware inventory alone does not prove backend support"
            )
        binding_macro = entry.get("binding_macro", "")
        if not isinstance(binding_macro, str) or (
            binding_macro and not BINDING_MACRO_PATTERN.fullmatch(binding_macro)
        ):
            raise PluginManifestError(
                f"Invalid resource binding_macro for {name}: {binding_macro!r}"
            )
        constraints = entry.get("constraints", {})
        if not isinstance(constraints, dict):
            raise PluginManifestError(
                f"Resource constraints for {name} must be an object"
            )
        _BusConstraints_Validate(name, kind, constraints)
        electrical_constraints = entry.get("electrical_constraints", {})
        if not isinstance(electrical_constraints, dict):
            raise PluginManifestError(
                f"Electrical constraints for {name} must be an object"
            )
        _ElectricalConstraints_Validate(name, electrical_constraints)
        display_names = entry.get("display_names", {})
        if not isinstance(display_names, dict) or not all(
            isinstance(language, str)
            and bool(language)
            and isinstance(display_name, str)
            and bool(display_name.strip())
            for language, display_name in display_names.items()
        ):
            raise PluginManifestError(
                f"Resource display_names for {name} must map languages to text"
            )
        requirements.append(
            ResourceRequirement(
                name=name,
                kind=kind,
                binding_macro=binding_macro,
                required=_Boolean_Get(entry, "required", True),
                mode=mode,
                candidates=candidates,
                platform_capabilities=platform_capabilities,
                constraints=dict(constraints),
                electrical_constraints=dict(electrical_constraints),
                display_names=dict(display_names),
            )
        )
    names = [requirement.name for requirement in requirements]
    if len(names) != len(set(names)):
        raise PluginManifestError("requires.resources contains duplicate names")
    return tuple(requirements)


def _Resources_Parse(
    data: Any,
) -> tuple[
    tuple[ResourceProvision, ...],
    tuple[ResourceRole, ...],
    tuple[ResourceConflict, ...],
]:
    resources = data if data is not None else {}
    if not isinstance(resources, dict) or set(resources) - {
        "provides",
        "roles",
        "conflicts",
    }:
        raise PluginManifestError(
            "resources must contain only provides, roles and conflicts"
        )
    provisions: list[ResourceProvision] = []
    for entry in resources.get("provides", []):
        if not isinstance(entry, dict):
            raise PluginManifestError("resources.provides entries must be objects")
        if set(entry) - {"id", "kind", "capabilities", "reserved", "metadata"}:
            raise PluginManifestError("provided resource contains unknown fields")
        resource_id = entry.get("id")
        kind = entry.get("kind")
        if not isinstance(resource_id, str) or not RESOURCE_ID_PATTERN.fullmatch(
            resource_id
        ):
            raise PluginManifestError(
                f"Invalid provided resource id: {resource_id!r}"
            )
        if not isinstance(kind, str) or not PLUGIN_ID_PATTERN.fullmatch(kind):
            raise PluginManifestError(f"Invalid provided resource kind: {kind!r}")
        metadata = entry.get("metadata", {})
        if not isinstance(metadata, dict):
            raise PluginManifestError("resource metadata must be an object")
        capabilities = _StringTuple_Get(
            entry.get("capabilities", []), "resource capabilities"
        )
        _CapabilityTuple_Validate(capabilities, "resource capabilities")
        provisions.append(
            ResourceProvision(
                resource_id=resource_id,
                kind=kind,
                capabilities=capabilities,
                reserved=_Boolean_Get(entry, "reserved", False),
                metadata=dict(metadata),
            )
        )
    provision_ids = [provision.resource_id for provision in provisions]
    if len(provision_ids) != len(set(provision_ids)):
        raise PluginManifestError("resources.provides contains duplicate ids")

    roles: list[ResourceRole] = []
    for entry in resources.get("roles", []):
        if not isinstance(entry, dict) or set(entry) - {
            "key",
            "kind",
            "default",
            "candidates",
            "fixed",
        }:
            raise PluginManifestError("resource role contains unknown fields")
        key = entry.get("key")
        kind = entry.get("kind")
        default = entry.get("default", "")
        candidates = _StringTuple_Get(
            entry.get("candidates", []), "resource role candidates"
        )
        if not isinstance(key, str) or not RESOURCE_ROLE_PATTERN.fullmatch(key):
            raise PluginManifestError(f"Invalid resource role key: {key!r}")
        if not isinstance(kind, str) or not PLUGIN_ID_PATTERN.fullmatch(kind):
            raise PluginManifestError(f"Invalid resource role kind: {kind!r}")
        if not isinstance(default, str) or (
            default and not RESOURCE_ID_PATTERN.fullmatch(default)
        ):
            raise PluginManifestError(f"Invalid resource role default: {default!r}")
        _BuildTokens_Validate(
            candidates, "resource role candidates", RESOURCE_ID_PATTERN
        )
        fixed = _Boolean_Get(entry, "fixed", False)
        if default and candidates and default not in candidates:
            raise PluginManifestError(
                f"Resource role {key} default is not in candidates"
            )
        if fixed and not default:
            raise PluginManifestError(
                f"Fixed resource role {key} must declare a default"
            )
        roles.append(ResourceRole(key, kind, default, candidates, fixed))
    role_keys = [role.key for role in roles]
    if len(role_keys) != len(set(role_keys)):
        raise PluginManifestError("resources.roles contains duplicate keys")

    conflicts: list[ResourceConflict] = []
    for entry in resources.get("conflicts", []):
        if not isinstance(entry, dict) or set(entry) - {"resources", "message"}:
            raise PluginManifestError("resource conflict contains unknown fields")
        conflict_resources = _StringTuple_Get(
            entry.get("resources", []), "resource conflict resources"
        )
        if len(conflict_resources) < 2:
            raise PluginManifestError(
                "resource conflict must contain at least two resources"
            )
        _BuildTokens_Validate(
            conflict_resources, "resource conflict resources", RESOURCE_ID_PATTERN
        )
        message = entry.get("message", "")
        if not isinstance(message, str):
            raise PluginManifestError("resource conflict message must be a string")
        conflicts.append(ResourceConflict(conflict_resources, message))
    return tuple(provisions), tuple(roles), tuple(conflicts)


def _Selection_Parse(value: Any) -> SelectionContribution | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {
        "kind",
        "slot",
        "required",
        "allow_none",
        "allow_multiple",
        "ui_order",
        "options",
        "default",
        "labels",
        "option_requirements",
        "parameters",
        "option_symbols",
        "aggregate_symbol",
        "none_defines",
    }:
        raise PluginManifestError("selection contains unknown fields")
    try:
        kind = SelectionKind(value.get("kind"))
    except (TypeError, ValueError) as error:
        raise PluginManifestError("selection.kind is invalid") from error
    slot = value.get("slot")
    if not isinstance(slot, str) or not PLUGIN_ID_PATTERN.fullmatch(slot):
        raise PluginManifestError("selection.slot is invalid")
    ui_order = value.get("ui_order", 100)
    if (
        isinstance(ui_order, bool)
        or not isinstance(ui_order, int)
        or not 0 <= ui_order <= 10000
    ):
        raise PluginManifestError(
            "selection.ui_order must be an integer from 0 to 10000"
        )
    options = _StringTuple_Get(value.get("options", []), "selection.options")
    invalid_option = next(
        (option for option in options if not SELECTION_OPTION_PATTERN.fullmatch(option)),
        None,
    )
    if invalid_option is not None:
        raise PluginManifestError(f"Invalid selection option: {invalid_option!r}")
    default_value = value.get("default", [])
    if isinstance(default_value, str):
        default = (default_value,) if default_value else ()
    else:
        default = _StringTuple_Get(default_value, "selection.default")
    if any(option not in options for option in default):
        raise PluginManifestError("selection.default contains an unknown option")
    required = _Boolean_Get(value, "required", kind == SelectionKind.STRATEGY)
    allow_none = _Boolean_Get(value, "allow_none", not required)
    allow_multiple = _Boolean_Get(value, "allow_multiple", False)
    if kind == SelectionKind.STRATEGY and (options or default or allow_multiple):
        raise PluginManifestError(
            "strategy selection cannot declare options/default/allow_multiple"
        )
    if kind == SelectionKind.MODE and not options:
        raise PluginManifestError("mode selection must declare options")
    if not allow_multiple and len(default) > 1:
        raise PluginManifestError("single selection has more than one default")
    if not allow_none and not default and kind == SelectionKind.MODE:
        raise PluginManifestError(
            "mode selection that disallows none needs a default"
        )
    labels = value.get("labels", {})
    if not isinstance(labels, dict):
        raise PluginManifestError("selection.labels must be an object")
    normalized_labels: dict[str, dict[str, str]] = {}
    for language, language_values in labels.items():
        if not isinstance(language, str) or not isinstance(language_values, dict):
            raise PluginManifestError("selection.labels entries must be objects")
        if set(language_values) - set(options) or not all(
            isinstance(label, str) and bool(label.strip())
            for label in language_values.values()
        ):
            raise PluginManifestError("selection.labels contains invalid options")
        normalized_labels[language] = dict(language_values)
    option_requirements_value = value.get("option_requirements", {})
    if not isinstance(option_requirements_value, dict):
        raise PluginManifestError("selection.option_requirements must be an object")
    option_requirements: dict[str, SelectionOptionRequirements] = {}
    for option, requirements_value in option_requirements_value.items():
        if option not in options or not isinstance(requirements_value, dict):
            raise PluginManifestError(
                "selection.option_requirements contains an invalid option"
            )
        if set(requirements_value) - {"capabilities", "components"}:
            raise PluginManifestError(
                "selection.option_requirements contains unknown fields"
            )
        components = _StringTuple_Get(
            requirements_value.get("components", []),
            f"selection.option_requirements.{option}.components",
        )
        _BuildTokens_Validate(
            components,
            f"selection.option_requirements.{option}.components",
            PLUGIN_ID_PATTERN,
        )
        option_requirements[option] = SelectionOptionRequirements(
            capabilities=_CapabilityRequirements_Parse(
                requirements_value.get("capabilities", [])
            ),
            components=components,
        )
    parameters_value = value.get("parameters", {})
    if not isinstance(parameters_value, dict):
        raise PluginManifestError("selection.parameters must be an object")
    parameters: dict[str, tuple[ModeParameterDefinition, ...]] = {}
    for option, definitions_value in parameters_value.items():
        if option not in options or not isinstance(definitions_value, list):
            raise PluginManifestError(
                "selection.parameters contains an invalid option"
            )
        definitions: list[ModeParameterDefinition] = []
        seen_parameter_ids: set[str] = set()
        for definition_value in definitions_value:
            if not isinstance(definition_value, dict) or set(definition_value) - {
                "id",
                "type",
                "default",
                "minimum",
                "maximum",
                "unit",
                "generated_symbol",
                "generated_scale",
                "display_names",
            }:
                raise PluginManifestError(
                    f"selection parameter for {option} has unknown fields"
                )
            parameter_id = definition_value.get("id")
            value_type = definition_value.get("type")
            unit = definition_value.get("unit", "")
            generated_symbol = definition_value.get("generated_symbol")
            if (
                not isinstance(parameter_id, str)
                or not PLUGIN_ID_PATTERN.fullmatch(parameter_id)
                or parameter_id in seen_parameter_ids
            ):
                raise PluginManifestError(
                    f"selection parameter id for {option} is invalid"
                )
            if value_type not in {"float", "integer"}:
                raise PluginManifestError(
                    f"selection parameter {parameter_id} has an invalid type"
                )
            if not isinstance(unit, str) or not unit:
                raise PluginManifestError(
                    f"selection parameter {parameter_id} needs a unit"
                )
            if (
                not isinstance(generated_symbol, str)
                or not BINDING_MACRO_PATTERN.fullmatch(generated_symbol)
            ):
                raise PluginManifestError(
                    f"selection parameter {parameter_id} has an invalid generated symbol"
                )
            numeric_values = tuple(
                definition_value.get(name)
                for name in ("default", "minimum", "maximum")
            )
            if not all(
                not isinstance(number, bool)
                and isinstance(number, (int, float))
                and math.isfinite(float(number))
                for number in numeric_values
            ):
                raise PluginManifestError(
                    f"selection parameter {parameter_id} bounds must be finite numbers"
                )
            parameter_default, minimum, maximum = numeric_values
            if float(minimum) > float(maximum) or not (
                float(minimum) <= float(parameter_default) <= float(maximum)
            ):
                raise PluginManifestError(
                    f"selection parameter {parameter_id} default is outside its range"
                )
            if value_type == "integer" and not all(
                isinstance(number, int) for number in numeric_values
            ):
                raise PluginManifestError(
                    f"integer selection parameter {parameter_id} needs integer bounds"
                )
            generated_scale = definition_value.get("generated_scale", 1.0)
            if (
                isinstance(generated_scale, bool)
                or not isinstance(generated_scale, (int, float))
                or not math.isfinite(float(generated_scale))
                or float(generated_scale) <= 0.0
            ):
                raise PluginManifestError(
                    f"selection parameter {parameter_id} generated_scale is invalid"
                )
            display_names = definition_value.get("display_names", {})
            if not isinstance(display_names, dict) or not all(
                isinstance(language, str)
                and bool(language)
                and isinstance(display_name, str)
                and bool(display_name.strip())
                for language, display_name in display_names.items()
            ):
                raise PluginManifestError(
                    f"selection parameter {parameter_id} display_names are invalid"
                )
            seen_parameter_ids.add(parameter_id)
            definitions.append(
                ModeParameterDefinition(
                    parameter_id=parameter_id,
                    value_type=value_type,
                    default=parameter_default,
                    minimum=minimum,
                    maximum=maximum,
                    unit=unit,
                    generated_symbol=generated_symbol,
                    generated_scale=float(generated_scale),
                    display_names=dict(display_names),
                )
            )
        parameters[option] = tuple(definitions)
    option_symbols_value = value.get("option_symbols", {})
    if not isinstance(option_symbols_value, dict) or any(
        option not in options
        or not isinstance(symbol, str)
        or not BINDING_MACRO_PATTERN.fullmatch(symbol)
        for option, symbol in option_symbols_value.items()
    ):
        raise PluginManifestError("selection.option_symbols is invalid")
    aggregate_symbol = value.get("aggregate_symbol", "")
    if not isinstance(aggregate_symbol, str) or (
        aggregate_symbol
        and not BINDING_MACRO_PATTERN.fullmatch(aggregate_symbol)
    ):
        raise PluginManifestError("selection.aggregate_symbol is invalid")
    if option_symbols_value and not aggregate_symbol:
        raise PluginManifestError(
            "selection.aggregate_symbol is required with option_symbols"
        )
    none_defines = _StringTuple_Get(
        value.get("none_defines", []), "selection.none_defines"
    )
    _BuildTokens_Validate(none_defines, "selection.none_defines", DEFINE_PATTERN)
    return SelectionContribution(
        kind=kind,
        slot=slot,
        required=required,
        allow_none=allow_none,
        allow_multiple=allow_multiple,
        ui_order=ui_order,
        options=options,
        default=default,
        labels=normalized_labels,
        option_requirements=option_requirements,
        parameters=parameters,
        option_symbols=dict(option_symbols_value),
        aggregate_symbol=aggregate_symbol,
        none_defines=none_defines,
    )


def _Board_Parse(value: Any) -> BoardContribution | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {
        "source_kind",
        "compatible_mcus",
        "vendor",
        "provider",
        "verified",
        "hardware_root",
        "ioc_file",
        "connections_file",
    }:
        raise PluginManifestError("board contains unknown fields")
    source_kind = value.get("source_kind")
    if source_kind not in ALLOWED_BOARD_SOURCE_KINDS:
        raise PluginManifestError("board.source_kind is invalid")
    compatible_mcus = _StringTuple_Get(
        value.get("compatible_mcus", []), "board.compatible_mcus"
    )
    if not compatible_mcus or any(
        not PLUGIN_ID_PATTERN.fullmatch(item) for item in compatible_mcus
    ):
        raise PluginManifestError("board.compatible_mcus is invalid")
    vendor = value.get("vendor", "")
    provider = value.get("provider", "")
    hardware_root = value.get("hardware_root", "")
    ioc_file = value.get("ioc_file", "")
    connections_file = value.get("connections_file", "")
    if not isinstance(vendor, str) or not vendor:
        raise PluginManifestError("board.vendor must be a non-empty string")
    if not isinstance(provider, str) or (
        provider and not PLUGIN_ID_PATTERN.fullmatch(provider)
    ):
        raise PluginManifestError("board.provider is invalid")
    if not isinstance(hardware_root, str):
        raise PluginManifestError("board.hardware_root must be a string")
    if hardware_root:
        _RelativePaths_Validate((hardware_root,), "board.hardware_root")
    for field_name, relative_path in (
        ("board.ioc_file", ioc_file),
        ("board.connections_file", connections_file),
    ):
        if not isinstance(relative_path, str):
            raise PluginManifestError(f"{field_name} must be a string")
        if relative_path:
            _RelativePaths_Validate((relative_path,), field_name)
    return BoardContribution(
        source_kind=source_kind,
        compatible_mcus=compatible_mcus,
        vendor=vendor,
        provider=provider,
        verified=_Boolean_Get(value, "verified", False),
        hardware_root=hardware_root,
        ioc_file=ioc_file,
        connections_file=connections_file,
    )


def _Platform_Parse(value: Any) -> PlatformContribution | None:
    if value is None:
        return None
    required_fields = {
        "abi",
        "provider",
        "build_target",
        "match_rules",
        "resource_binding",
        "resource_backends",
        "compatibility",
        "support",
    }
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or set(value) - (required_fields | {"module_providers"})
    ):
        raise PluginManifestError(
            "platform must contain abi, provider, build_target, match_rules, "
            "resource_binding, resource_backends, compatibility and support"
        )
    abi = value["abi"]
    if (
        not isinstance(abi, dict)
        or set(abi) != {"id", "major", "minor"}
        or not isinstance(abi.get("id"), str)
        or not PLUGIN_ID_PATTERN.fullmatch(abi["id"])
        or not isinstance(abi.get("major"), int)
        or isinstance(abi.get("major"), bool)
        or not isinstance(abi.get("minor"), int)
        or isinstance(abi.get("minor"), bool)
        or not 0 <= abi["major"] <= 0xFFFF
        or not 0 <= abi["minor"] <= 0xFFFF
    ):
        raise PluginManifestError("platform.abi is invalid")
    provider = value["provider"]
    if not isinstance(provider, str) or not PLUGIN_ID_PATTERN.fullmatch(provider):
        raise PluginManifestError("platform.provider is invalid")
    build_target = value["build_target"]
    if (
        not isinstance(build_target, dict)
        or set(build_target) != {"profile"}
        or not isinstance(build_target.get("profile"), str)
        or BUILD_TARGET_PROFILE_PATTERN.fullmatch(build_target["profile"]) is None
    ):
        raise PluginManifestError("platform.build_target.profile is invalid")

    raw_rules = value["match_rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PluginManifestError("platform.match_rules must be non-empty")
    match_rules: list[PlatformMatchRule] = []
    pattern_re = re.compile(r"^[A-Za-z0-9*?_. -]+$")
    verification_values = {"experimental", "supported", "verified"}
    for index, entry in enumerate(raw_rules):
        if not isinstance(entry, dict) or set(entry) - {
            "vendor",
            "exact_part",
            "family_pattern",
            "package_pattern",
            "core_pattern",
            "priority",
            "specificity",
            "verification",
        }:
            raise PluginManifestError(
                f"platform.match_rules[{index}] contains invalid fields"
            )
        vendor = entry.get("vendor")
        exact_part = entry.get("exact_part", "")
        family_pattern = entry.get("family_pattern", "")
        package_pattern = entry.get("package_pattern", "")
        core_pattern = entry.get("core_pattern", "")
        if not isinstance(vendor, str) or not vendor.strip():
            raise PluginManifestError(
                f"platform.match_rules[{index}].vendor is required"
            )
        for field_name, field_value in (
            ("exact_part", exact_part),
            ("family_pattern", family_pattern),
            ("package_pattern", package_pattern),
            ("core_pattern", core_pattern),
        ):
            if not isinstance(field_value, str) or (
                field_value and pattern_re.fullmatch(field_value) is None
            ):
                raise PluginManifestError(
                    f"platform.match_rules[{index}].{field_name} is invalid"
                )
        if not exact_part and not family_pattern:
            raise PluginManifestError(
                f"platform.match_rules[{index}] needs exact_part or family_pattern"
            )
        priority = entry.get("priority", 0)
        specificity = entry.get("specificity", 0)
        if any(
            not isinstance(number, int)
            or isinstance(number, bool)
            or not 0 <= number <= 10000
            for number in (priority, specificity)
        ):
            raise PluginManifestError(
                f"platform.match_rules[{index}] priority/specificity is invalid"
            )
        verification = entry.get("verification", "experimental")
        if verification not in verification_values:
            raise PluginManifestError(
                f"platform.match_rules[{index}].verification is invalid"
            )
        match_rules.append(
            PlatformMatchRule(
                vendor=vendor.strip(),
                exact_part=exact_part,
                family_pattern=family_pattern,
                package_pattern=package_pattern,
                core_pattern=core_pattern,
                priority=priority,
                specificity=specificity,
                verification=verification,
            )
        )

    resource_binding = value["resource_binding"]
    if (
        not isinstance(resource_binding, dict)
        or set(resource_binding) != {"header", "bindings"}
    ):
        raise PluginManifestError("platform.resource_binding is invalid")
    resource_header = resource_binding.get("header")
    if (
        not isinstance(resource_header, str)
        or re.fullmatch(r"[A-Za-z0-9_./-]+\.h", resource_header) is None
        or ".." in Path(resource_header).parts
    ):
        raise PluginManifestError("platform.resource_binding.header is unsafe")
    raw_bindings = resource_binding.get("bindings")
    if not isinstance(raw_bindings, dict) or not raw_bindings:
        raise PluginManifestError(
            "platform.resource_binding.bindings must be non-empty"
        )
    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    resource_bindings: dict[str, PlatformResourceBinding] = {}
    for kind, entry in raw_bindings.items():
        if (
            not isinstance(kind, str)
            or not PLUGIN_ID_PATTERN.fullmatch(kind)
            or not isinstance(entry, dict)
            or set(entry)
            != {
                "collection",
                "include_header",
                "entry_kind",
                "id_type",
                "count_symbol",
                "table_symbol",
                "getter",
                "struct_type",
            }
        ):
            raise PluginManifestError(
                f"platform resource binding {kind!r} has invalid fields"
            )
        collection = entry["collection"]
        include_header = entry["include_header"]
        entry_kind = entry["entry_kind"]
        struct_type = entry["struct_type"]
        if (
            not isinstance(collection, str)
            or not PLUGIN_ID_PATTERN.fullmatch(collection)
            or not isinstance(include_header, str)
            or re.fullmatch(r"[A-Za-z0-9_./-]+\.h", include_header) is None
            or ".." in Path(include_header).parts
            or entry_kind not in {"handle", "gpio", "pwm", "timebase", "systick"}
            or not isinstance(struct_type, str)
            or (struct_type and identifier.fullmatch(struct_type) is None)
            or (entry_kind != "handle" and not struct_type)
            or any(
                not isinstance(entry[field], str)
                or identifier.fullmatch(entry[field]) is None
                for field in (
                    "id_type",
                    "count_symbol",
                    "table_symbol",
                    "getter",
                )
            )
        ):
            raise PluginManifestError(
                f"platform resource binding {kind} contains unsafe C tokens"
            )
        resource_bindings[kind] = PlatformResourceBinding(
            kind=kind,
            collection=collection,
            include_header=include_header,
            entry_kind=entry_kind,
            id_type=entry["id_type"],
            count_symbol=entry["count_symbol"],
            table_symbol=entry["table_symbol"],
            getter=entry["getter"],
            struct_type=struct_type,
        )

    raw_backends = value["resource_backends"]
    if not isinstance(raw_backends, dict):
        raise PluginManifestError("platform.resource_backends must be an object")
    ownership_values = {
        "shared",
        "shared_bus_unique_address",
        "single_owner",
        "exclusive_channel_shared_timer",
    }
    resource_backends: dict[str, PlatformBackendContribution] = {}
    backend_kind_owners: dict[str, str] = {}
    for backend_id, entry in raw_backends.items():
        if (
            not isinstance(backend_id, str)
            or not PLUGIN_ID_PATTERN.fullmatch(backend_id)
            or not isinstance(entry, dict)
            or set(entry)
            != {
                "inventory_kinds",
                "sources",
                "provider_sources",
                "include_dirs",
                "defines",
                "capabilities",
                "ownership",
                "maturity",
            }
        ):
            raise PluginManifestError(
                f"platform.resource_backends.{backend_id} is invalid"
            )
        inventory_kinds = _StringTuple_Get(
            entry["inventory_kinds"],
            f"platform.resource_backends.{backend_id}.inventory_kinds",
        )
        sources = _StringTuple_Get(
            entry["sources"], f"platform.resource_backends.{backend_id}.sources"
        )
        provider_sources = _StringTuple_Get(
            entry["provider_sources"],
            f"platform.resource_backends.{backend_id}.provider_sources",
        )
        include_dirs = _StringTuple_Get(
            entry["include_dirs"],
            f"platform.resource_backends.{backend_id}.include_dirs",
        )
        defines = _StringTuple_Get(
            entry["defines"], f"platform.resource_backends.{backend_id}.defines"
        )
        capabilities = _StringTuple_Get(
            entry["capabilities"],
            f"platform.resource_backends.{backend_id}.capabilities",
        )
        ownership = entry["ownership"]
        maturity = entry["maturity"]
        if (
            not inventory_kinds
            or not sources
            or ownership not in ownership_values
            or maturity not in {"reserved", "experimental", "supported", "verified"}
        ):
            raise PluginManifestError(
                f"platform.resource_backends.{backend_id} is incomplete"
            )
        _BuildTokens_Validate(
            (*sources, *provider_sources, *include_dirs),
            f"platform.resource_backends.{backend_id} paths",
            BUILD_PATH_PATTERN,
        )
        _RelativePaths_Validate(
            (*sources, *provider_sources, *include_dirs),
            f"platform.resource_backends.{backend_id}",
        )
        _BuildTokens_Validate(
            defines,
            f"platform.resource_backends.{backend_id}.defines",
            DEFINE_PATTERN,
        )
        if any(
            not PLUGIN_ID_PATTERN.fullmatch(item)
            for item in (*inventory_kinds, *capabilities)
        ):
            raise PluginManifestError(
                f"platform.resource_backends.{backend_id} identifiers are invalid"
            )
        for inventory_kind in inventory_kinds:
            previous = backend_kind_owners.get(inventory_kind)
            if previous is not None:
                raise PluginManifestError(
                    f"platform resource kind {inventory_kind} belongs to both "
                    f"{previous} and {backend_id}"
                )
            binding_kind = (
                "gpio" if inventory_kind.startswith("gpio_") else inventory_kind
            )
            if binding_kind not in resource_bindings:
                raise PluginManifestError(
                    f"platform backend {backend_id} has no resource binding for "
                    f"{inventory_kind}"
                )
            backend_kind_owners[inventory_kind] = backend_id
        resource_backends[backend_id] = PlatformBackendContribution(
            backend_id=backend_id,
            inventory_kinds=inventory_kinds,
            sources=sources,
            provider_sources=provider_sources,
            include_dirs=include_dirs,
            defines=defines,
            capabilities=capabilities,
            ownership=ownership,
            maturity=maturity,
        )

    raw_module_providers = value.get("module_providers", {})
    if not isinstance(raw_module_providers, dict):
        raise PluginManifestError("platform.module_providers must be an object")
    module_providers: dict[str, PlatformModuleProviderContribution] = {}
    module_pattern = re.compile(r"^[A-Za-z0-9_*?.-]+$")
    for provider_id, entry in raw_module_providers.items():
        expected_fields = {
            "inventory_modules",
            "init_sources",
            "provider_sources",
            "middleware_sources",
            "include_dirs",
            "defines",
            "capabilities",
            "limitations",
            "always",
        }
        if (
            not isinstance(provider_id, str)
            or not PLUGIN_ID_PATTERN.fullmatch(provider_id)
            or not isinstance(entry, dict)
            or set(entry) != expected_fields
            or not isinstance(entry.get("always"), bool)
        ):
            raise PluginManifestError(
                f"platform.module_providers.{provider_id} is invalid"
            )
        inventory_modules = _StringTuple_Get(
            entry["inventory_modules"],
            f"platform.module_providers.{provider_id}.inventory_modules",
        )
        init_sources = _StringTuple_Get(
            entry["init_sources"],
            f"platform.module_providers.{provider_id}.init_sources",
        )
        provider_sources = _StringTuple_Get(
            entry["provider_sources"],
            f"platform.module_providers.{provider_id}.provider_sources",
        )
        middleware_sources = _StringTuple_Get(
            entry["middleware_sources"],
            f"platform.module_providers.{provider_id}.middleware_sources",
        )
        include_dirs = _StringTuple_Get(
            entry["include_dirs"],
            f"platform.module_providers.{provider_id}.include_dirs",
        )
        defines = _StringTuple_Get(
            entry["defines"],
            f"platform.module_providers.{provider_id}.defines",
        )
        capabilities = _StringTuple_Get(
            entry["capabilities"],
            f"platform.module_providers.{provider_id}.capabilities",
        )
        limitations = _StringTuple_Get(
            entry["limitations"],
            f"platform.module_providers.{provider_id}.limitations",
        )
        if (
            not entry["always"]
            and not inventory_modules
            and not init_sources
        ):
            raise PluginManifestError(
                f"platform.module_providers.{provider_id} has no activation rule"
            )
        if any(module_pattern.fullmatch(item) is None for item in inventory_modules):
            raise PluginManifestError(
                f"platform.module_providers.{provider_id}.inventory_modules is invalid"
            )
        _BuildTokens_Validate(
            (*init_sources, *provider_sources, *middleware_sources, *include_dirs),
            f"platform.module_providers.{provider_id} paths",
            BUILD_PATH_PATTERN,
        )
        _RelativePaths_Validate(
            (*init_sources, *provider_sources, *middleware_sources, *include_dirs),
            f"platform.module_providers.{provider_id}",
        )
        _BuildTokens_Validate(
            defines,
            f"platform.module_providers.{provider_id}.defines",
            DEFINE_PATTERN,
        )
        if any(not PLUGIN_ID_PATTERN.fullmatch(item) for item in capabilities):
            raise PluginManifestError(
                f"platform.module_providers.{provider_id}.capabilities is invalid"
            )
        module_providers[provider_id] = PlatformModuleProviderContribution(
            provider_id=provider_id,
            inventory_modules=inventory_modules,
            init_sources=init_sources,
            provider_sources=provider_sources,
            middleware_sources=middleware_sources,
            include_dirs=include_dirs,
            defines=defines,
            capabilities=capabilities,
            limitations=limitations,
            always=entry["always"],
        )

    compatibility = value["compatibility"]
    if (
        not isinstance(compatibility, dict)
        or set(compatibility)
        != {"cubemx_versions", "firmware_packages", "source_policy"}
    ):
        raise PluginManifestError("platform.compatibility is invalid")
    cubemx_versions = _StringTuple_Get(
        compatibility["cubemx_versions"],
        "platform.compatibility.cubemx_versions",
    )
    firmware_packages = _StringTuple_Get(
        compatibility["firmware_packages"],
        "platform.compatibility.firmware_packages",
    )
    if (
        not cubemx_versions
        or not firmware_packages
        or any(not item.strip() for item in (*cubemx_versions, *firmware_packages))
        or compatibility["source_policy"]
        not in {"plugin_payload_authoritative", "imported_tree_authoritative"}
    ):
        raise PluginManifestError("platform.compatibility is incomplete")

    support = value["support"]
    if (
        not isinstance(support, dict)
        or set(support) != {"level", "limitations"}
        or support.get("level") not in verification_values
    ):
        raise PluginManifestError("platform.support is invalid")
    limitations = _StringTuple_Get(
        support.get("limitations"), "platform.support.limitations"
    )
    return PlatformContribution(
        abi_id=abi["id"],
        abi_major=abi["major"],
        abi_minor=abi["minor"],
        provider=provider,
        build_target_profile=build_target["profile"],
        match_rules=tuple(match_rules),
        resource_header=resource_header,
        resource_bindings=resource_bindings,
        resource_backends=resource_backends,
        module_providers=module_providers,
        compatibility=PlatformCompatibilityContribution(
            cubemx_versions=cubemx_versions,
            firmware_packages=firmware_packages,
            source_policy=compatibility["source_policy"],
        ),
        support_level=support["level"],
        limitations=limitations,
    )


def _Protocol_Parse(value: Any) -> ProtocolContribution | None:
    if value is None:
        return None
    required = {
        "category",
        "logging_metadata",
        "maintenance_protocol_version",
        "firmware_version",
        "documentation_version",
    }
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or set(value) - {*required, "profiles", "extensions"}
    ):
        raise PluginManifestError(
            "protocol must contain logging metadata and explicit version fields"
        )
    category = value.get("category")
    if category not in ALLOWED_PROTOCOL_CATEGORIES:
        raise PluginManifestError(
            "protocol.category must be one of telemetry, maintenance or logging"
        )
    extensions = value.get("extensions", {})
    if not isinstance(extensions, dict) or any(
        not isinstance(key, str)
        or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", key)
        or not isinstance(extension, dict)
        for key, extension in extensions.items()
    ):
        raise PluginManifestError(
            "protocol.extensions must use reverse-domain keys with object values"
        )
    metadata_path = value.get("logging_metadata")
    if not isinstance(metadata_path, str) or not metadata_path:
        raise PluginManifestError("protocol.logging_metadata must be a path")
    _RelativePaths_Validate((metadata_path,), "protocol.logging_metadata")
    versions = tuple(
        value.get(field_name)
        for field_name in (
            "maintenance_protocol_version",
            "firmware_version",
            "documentation_version",
        )
    )
    if not all(
        isinstance(version, str) and VERSION_PATTERN.fullmatch(version)
        for version in versions
    ):
        raise PluginManifestError("protocol version fields are invalid")
    profiles_value = value.get("profiles", {})
    if not isinstance(profiles_value, dict):
        raise PluginManifestError("protocol.profiles must be an object")
    profiles: dict[str, tuple[ProtocolProfileContribution, ...]] = {}
    for category, entries_value in profiles_value.items():
        if (
            not isinstance(category, str)
            or not PLUGIN_ID_PATTERN.fullmatch(category)
            or not isinstance(entries_value, list)
            or not entries_value
        ):
            raise PluginManifestError("protocol.profiles category is invalid")
        entries: list[ProtocolProfileContribution] = []
        seen_ids: set[str] = set()
        for entry_value in entries_value:
            profile_fields = {
                "id",
                "version",
                "display_names",
                "service",
                "slot",
                "codec_sources",
                "parser_sources",
                "include_dirs",
                "defines",
                "binding",
                "transport_selection",
                "transport",
                "decoder_metadata",
                "documentation",
                "host_tests",
                "golden_tests",
            }
            if not isinstance(entry_value, dict) or set(entry_value) != profile_fields:
                raise PluginManifestError(
                    f"protocol profile in {category} is invalid"
                )
            profile_id = entry_value.get("id")
            profile_version = entry_value.get("version")
            display_names = entry_value.get("display_names")
            service = entry_value.get("service")
            slot = entry_value.get("slot")
            binding = entry_value.get("binding")
            transport_selection = entry_value.get("transport_selection")
            decoder_metadata = entry_value.get("decoder_metadata")
            if (
                not isinstance(profile_id, str)
                or not PLUGIN_ID_PATTERN.fullmatch(profile_id)
                or profile_id in seen_ids
                or not isinstance(profile_version, str)
                or not VERSION_PATTERN.fullmatch(profile_version)
                or not isinstance(display_names, dict)
                or not all(
                    isinstance(language, str)
                    and bool(language)
                    and isinstance(display_name, str)
                    and bool(display_name.strip())
                    for language, display_name in display_names.items()
                )
                or not isinstance(service, str)
                or service
                not in {
                    "telemetry_service",
                    "maintenance_service",
                    "flight_log_service",
                }
                or slot != PROTOCOL_PROFILE_SLOTS.get(category)
                or not isinstance(binding, str)
                or not PLUGIN_ID_PATTERN.fullmatch(binding)
                or transport_selection not in {"single", "ordered_failover"}
                or not isinstance(decoder_metadata, str)
                or not decoder_metadata
            ):
                raise PluginManifestError(
                    f"protocol profile in {category} is invalid"
                )
            codec_sources = _StringTuple_Get(
                entry_value.get("codec_sources"),
                f"protocol.profiles.{category}.codec_sources",
            )
            parser_sources = _StringTuple_Get(
                entry_value.get("parser_sources"),
                f"protocol.profiles.{category}.parser_sources",
            )
            include_dirs = _StringTuple_Get(
                entry_value.get("include_dirs"),
                f"protocol.profiles.{category}.include_dirs",
            )
            defines = _StringTuple_Get(
                entry_value.get("defines"),
                f"protocol.profiles.{category}.defines",
            )
            documentation = _StringTuple_Get(
                entry_value.get("documentation"),
                f"protocol.profiles.{category}.documentation",
            )
            host_tests = _StringTuple_Get(
                entry_value.get("host_tests"),
                f"protocol.profiles.{category}.host_tests",
            )
            golden_tests = _StringTuple_Get(
                entry_value.get("golden_tests"),
                f"protocol.profiles.{category}.golden_tests",
            )
            if not all(
                (
                    codec_sources,
                    parser_sources,
                    include_dirs,
                    documentation,
                    host_tests,
                    golden_tests,
                )
            ):
                raise PluginManifestError(
                    f"protocol profile {profile_id} has an incomplete implementation contribution"
                )
            _RelativePaths_Validate(
                (
                    *codec_sources,
                    *parser_sources,
                    *include_dirs,
                    decoder_metadata,
                    *documentation,
                    *host_tests,
                    *golden_tests,
                ),
                f"protocol profile {profile_id}",
            )
            _BuildTokens_Validate(
                defines, f"protocol profile {profile_id} defines", DEFINE_PATTERN
            )
            transport_value = entry_value.get("transport")
            transport_fields = {
                "capability",
                "kind",
                "minimum_mtu",
                "ordered",
                "bidirectional",
                "reliable",
                "mode",
            }
            if (
                not isinstance(transport_value, dict)
                or set(transport_value) != transport_fields
            ):
                raise PluginManifestError(
                    f"protocol profile {profile_id} transport is invalid"
                )
            transport_capability = transport_value.get("capability")
            transport_kind = transport_value.get("kind")
            minimum_mtu = transport_value.get("minimum_mtu")
            transport_mode = transport_value.get("mode")
            if (
                not isinstance(transport_capability, str)
                or not PLUGIN_ID_PATTERN.fullmatch(transport_capability)
                or not isinstance(transport_kind, str)
                or not PLUGIN_ID_PATTERN.fullmatch(transport_kind)
                or isinstance(minimum_mtu, bool)
                or not isinstance(minimum_mtu, int)
                or minimum_mtu < 1
                or transport_mode not in {"stream", "datagram", "file"}
                or not all(
                    isinstance(transport_value.get(flag), bool)
                    for flag in ("ordered", "bidirectional", "reliable")
                )
            ):
                raise PluginManifestError(
                    f"protocol profile {profile_id} transport constraint is invalid"
                )
            seen_ids.add(profile_id)
            entries.append(
                ProtocolProfileContribution(
                    profile_id=profile_id,
                    version=profile_version,
                    display_names=dict(display_names),
                    service=service,
                    slot=slot,
                    codec_sources=codec_sources,
                    parser_sources=parser_sources,
                    include_dirs=include_dirs,
                    defines=defines,
                    binding=binding,
                    transport_selection=transport_selection,
                    transport=ProtocolTransportConstraint(
                        capability=transport_capability,
                        kind=transport_kind,
                        minimum_mtu=minimum_mtu,
                        ordered=transport_value["ordered"],
                        bidirectional=transport_value["bidirectional"],
                        reliable=transport_value["reliable"],
                        mode=transport_mode,
                    ),
                    decoder_metadata=decoder_metadata,
                    documentation=documentation,
                    host_tests=host_tests,
                    golden_tests=golden_tests,
                )
            )
        profiles[category] = tuple(entries)
    if set(profiles) != {category}:
        raise PluginManifestError(
            "protocol.profiles must contain only protocol.category"
        )
    return ProtocolContribution(
        category,
        metadata_path,
        *versions,
        profiles=profiles,
        extensions=dict(extensions),
    )


def _Transports_Parse(
    value: Any, provides: tuple[str, ...]
) -> tuple[TransportContribution, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginManifestError("transports must be an array")
    entries: list[TransportContribution] = []
    expected_fields = {
        "capability",
        "kind",
        "mtu",
        "ordered",
        "bidirectional",
        "reliable",
        "mode",
    }
    seen_capabilities: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise PluginManifestError("transport contribution is invalid")
        capability = entry.get("capability")
        kind = entry.get("kind")
        mtu = entry.get("mtu")
        mode = entry.get("mode")
        if (
            not isinstance(capability, str)
            or not PLUGIN_ID_PATTERN.fullmatch(capability)
            or capability not in provides
            or capability in seen_capabilities
            or not isinstance(kind, str)
            or not PLUGIN_ID_PATTERN.fullmatch(kind)
            or isinstance(mtu, bool)
            or not isinstance(mtu, int)
            or mtu < 1
            or mode not in {"stream", "datagram", "file"}
            or not all(
                isinstance(entry.get(flag), bool)
                for flag in ("ordered", "bidirectional", "reliable")
            )
        ):
            raise PluginManifestError("transport contribution is invalid")
        seen_capabilities.add(capability)
        entries.append(
            TransportContribution(
                capability=capability,
                kind=kind,
                mtu=mtu,
                ordered=entry["ordered"],
                bidirectional=entry["bidirectional"],
                reliable=entry["reliable"],
                mode=mode,
            )
        )
    return tuple(entries)


def _HardwareProvider_Parse(value: Any) -> HardwareProviderContribution | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {
        "vendor",
        "handler",
        "accepted_inputs",
    }:
        raise PluginManifestError("hardware_provider contains unknown fields")
    vendor = value.get("vendor")
    handler = value.get("handler")
    accepted_inputs = _StringTuple_Get(
        value.get("accepted_inputs", []), "hardware_provider.accepted_inputs"
    )
    if not isinstance(vendor, str) or not vendor:
        raise PluginManifestError(
            "hardware_provider.vendor must be a non-empty string"
        )
    if handler not in ALLOWED_PROVIDER_HANDLERS:
        raise PluginManifestError("hardware_provider.handler is not trusted")
    if not accepted_inputs:
        raise PluginManifestError(
            "hardware_provider.accepted_inputs must not be empty"
        )
    return HardwareProviderContribution(vendor, handler, accepted_inputs)


def _Environment_Parse(value: Any) -> EnvironmentContribution | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {
        "renderer",
        "toolchain",
        "outputs",
        "tasks",
        "eide_native",
    }:
        raise PluginManifestError("environment contains unknown fields")
    renderer = value.get("renderer")
    toolchain = value.get("toolchain")
    if renderer not in ALLOWED_ENVIRONMENT_RENDERERS:
        raise PluginManifestError("environment.renderer is not supported")
    if not isinstance(toolchain, str) or not toolchain:
        raise PluginManifestError(
            "environment.toolchain must be a non-empty string"
        )
    outputs = _StringTuple_Get(value.get("outputs", []), "environment.outputs")
    tasks = _StringTuple_Get(value.get("tasks", []), "environment.tasks")
    _RelativePaths_Validate(outputs, "environment.outputs")
    return EnvironmentContribution(
        renderer=renderer,
        toolchain=toolchain,
        outputs=outputs,
        tasks=tasks,
        eide_native=_Boolean_Get(value, "eide_native", False),
    )


def _Build_Parse(value: Any) -> BuildContribution:
    data = value if value is not None else {}
    if not isinstance(data, dict) or set(data) - {
        "sources",
        "protocol_sources",
        "strategy_sources",
        "asm_sources",
        "include_dirs",
        "defines",
        "mcu_flags",
        "specs",
        "libraries",
        "forced_includes",
        "virtual_sources",
        "exclude_sources",
        "linker_script",
        "toolchain_prefix",
    }:
        raise PluginManifestError("build contains unknown fields")
    sources = _StringTuple_Get(data.get("sources", []), "build.sources")
    protocol_sources_value = data.get("protocol_sources", {})
    if (
        not isinstance(protocol_sources_value, dict)
        or any(
            category not in ALLOWED_PROTOCOL_CATEGORIES
            for category in protocol_sources_value
        )
    ):
        raise PluginManifestError(
            "build.protocol_sources must map valid Protocol categories"
        )
    protocol_sources = {
        category: _StringTuple_Get(
            values, f"build.protocol_sources.{category}"
        )
        for category, values in protocol_sources_value.items()
    }
    strategy_sources_value = data.get("strategy_sources", {})
    if not isinstance(strategy_sources_value, dict):
        raise PluginManifestError("build.strategy_sources must be an object")
    strategy_sources: dict[str, dict[str, tuple[str, ...]]] = {}
    for slot, variants_value in strategy_sources_value.items():
        if not isinstance(slot, str) or not PLUGIN_ID_PATTERN.fullmatch(slot):
            raise PluginManifestError(
                f"build.strategy_sources slot is invalid: {slot!r}"
            )
        if (
            not isinstance(variants_value, dict)
            or not variants_value
            or set(variants_value) - {"selected", "none"}
        ):
            raise PluginManifestError(
                f"build.strategy_sources.{slot} must define selected and/or none"
            )
        variants: dict[str, tuple[str, ...]] = {}
        for state, state_sources in variants_value.items():
            variants[state] = _StringTuple_Get(
                state_sources, f"build.strategy_sources.{slot}.{state}"
            )
        strategy_sources[slot] = variants
    asm_sources = _StringTuple_Get(data.get("asm_sources", []), "build.asm_sources")
    include_dirs = _StringTuple_Get(data.get("include_dirs", []), "build.include_dirs")
    defines = _StringTuple_Get(data.get("defines", []), "build.defines")
    mcu_flags = _StringTuple_Get(data.get("mcu_flags", []), "build.mcu_flags")
    specs = _StringTuple_Get(data.get("specs", []), "build.specs")
    libraries = _StringTuple_Get(data.get("libraries", []), "build.libraries")
    forced_includes = _StringTuple_Get(
        data.get("forced_includes", []), "build.forced_includes"
    )
    virtual_sources = _StringTuple_Get(
        data.get("virtual_sources", []), "build.virtual_sources"
    )
    exclude_sources = _StringTuple_Get(
        data.get("exclude_sources", []), "build.exclude_sources"
    )
    linker_script = data.get("linker_script", "")
    toolchain_prefix = data.get("toolchain_prefix", "")
    if not isinstance(linker_script, str):
        raise PluginManifestError("build.linker_script must be a string")
    if not isinstance(toolchain_prefix, str) or not TOOLCHAIN_PREFIX_PATTERN.fullmatch(
        toolchain_prefix
    ):
        raise PluginManifestError("build.toolchain_prefix is invalid")
    path_groups = {
        "build.sources": sources,
        **{
            f"build.protocol_sources.{category}": values
            for category, values in protocol_sources.items()
        },
        **{
            f"build.strategy_sources.{slot}.{state}": values
            for slot, variants in strategy_sources.items()
            for state, values in variants.items()
        },
        "build.asm_sources": asm_sources,
        "build.include_dirs": include_dirs,
        "build.forced_includes": forced_includes,
        "build.virtual_sources": virtual_sources,
        "build.exclude_sources": exclude_sources,
    }
    path_values = tuple(
        value
        for values in path_groups.values()
        for value in values
    )
    _BuildTokens_Validate(path_values, "build paths", BUILD_PATH_PATTERN)
    _BuildTokens_Validate(defines, "build.defines", DEFINE_PATTERN)
    _BuildTokens_Validate(mcu_flags, "build.mcu_flags", BUILD_TOKEN_PATTERN)
    _BuildTokens_Validate(specs, "build.specs", BUILD_TOKEN_PATTERN)
    _BuildTokens_Validate(libraries, "build.libraries", BUILD_TOKEN_PATTERN)
    for field_name, values in path_groups.items():
        _RelativePaths_Validate(values, field_name)
    if linker_script:
        _RelativePaths_Validate((linker_script,), "build.linker_script")
        _BuildTokens_Validate(
            (linker_script,), "build.linker_script", BUILD_PATH_PATTERN
        )
    return BuildContribution(
        sources=sources,
        protocol_sources=protocol_sources,
        strategy_sources=strategy_sources,
        asm_sources=asm_sources,
        include_dirs=include_dirs,
        defines=defines,
        mcu_flags=mcu_flags,
        specs=specs,
        libraries=libraries,
        forced_includes=forced_includes,
        virtual_sources=virtual_sources,
        exclude_sources=exclude_sources,
        linker_script=linker_script,
        toolchain_prefix=toolchain_prefix,
    )


def PluginManifest_Parse(
    data: dict[str, Any], manifest_path: Path, *, source: str
) -> PluginManifest:
    if not isinstance(data, dict):
        raise PluginManifestError("plugin.json must contain a JSON object")
    required_fields = ("schema_version", "id", "name", "type", "version", "payload")
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise PluginManifestError(f"Missing manifest fields: {', '.join(missing)}")
    if data["schema_version"] != 0:
        raise PluginManifestError("Only plugin schema_version 0 is supported")
    allowed_top_level = {
        "schema_version",
        "id",
        "name",
        "type",
        "class",
        "version",
        "description",
        "requires",
        "resources",
        "provides",
        "build",
        "payload",
        "metadata",
        "selection",
        "algorithm_parameters",
        "board",
        "hardware_provider",
        "environment",
        "cardinality",
        "instance_policy",
        "physical_device",
        "radio",
        "platform",
        "protocol",
        "transports",
        "device_variants",
    }
    unknown = set(data) - allowed_top_level
    if unknown:
        raise PluginManifestError(
            f"Unknown manifest fields: {', '.join(sorted(unknown))}"
        )
    component_id = data["id"]
    if not isinstance(component_id, str) or not PLUGIN_ID_PATTERN.fullmatch(
        component_id
    ):
        raise PluginManifestError(f"Invalid plugin id: {component_id!r}")
    component_type = data["type"]
    if component_type not in ALLOWED_PLUGIN_TYPES:
        raise PluginManifestError(f"Unsupported plugin type: {component_type!r}")
    device_variants = data.get("device_variants", {})
    if not isinstance(device_variants, dict) or (device_variants and component_type != "device"):
        raise PluginManifestError("device_variants is only valid on Device plugins")
    for variant_id, variant in device_variants.items():
        if not isinstance(variant_id, str) or not SELECTION_OPTION_PATTERN.fullmatch(variant_id):
            raise PluginManifestError("device variant id is invalid")
        if not isinstance(variant, dict) or set(variant) != {"interface", "profile", "overrides"}:
            raise PluginManifestError("device variant needs interface, profile and overrides")
        if any(not isinstance(variant[key], str) or not SELECTION_OPTION_PATTERN.fullmatch(variant[key]) for key in ("interface", "profile")):
            raise PluginManifestError("device variant interface or profile is invalid")
        overrides = variant["overrides"]
        if not isinstance(overrides, dict) or set(overrides) - {
            "name", "description", "requires", "build", "payload", "metadata",
            "provides",
        }:
            raise PluginManifestError("device variant overrides unsupported common fields")
        if "provides" in overrides and not set(data.get("provides", [])).issubset(overrides["provides"]):
            raise PluginManifestError("device variant cannot remove common capabilities")
    version = data["version"]
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise PluginManifestError(f"Invalid plugin version: {version!r}")
    for field_name in ("name", "description", "class"):
        if field_name in data and not isinstance(data[field_name], str):
            raise PluginManifestError(f"{field_name} must be a string")
    if not data["name"].strip():
        raise PluginManifestError("name must not be empty")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise PluginManifestError("metadata must be an object")
    try:
        SensorRecommendations_Parse(metadata.get("sensor_recommendations"))
    except ValueError as error:
        raise PluginManifestError(str(error)) from error
    for metadata_field in ("display_names", "descriptions"):
        localized_values = metadata.get(metadata_field, {})
        if not isinstance(localized_values, dict) or not all(
            isinstance(language, str)
            and bool(language)
            and isinstance(localized, str)
            and bool(localized.strip())
            for language, localized in localized_values.items()
        ):
            raise PluginManifestError(
                f"metadata.{metadata_field} must map languages to non-empty strings"
            )
    record_fragments = _StringTuple_Get(
        metadata.get("record_catalog_fragments", []),
        "metadata.record_catalog_fragments",
    )
    if record_fragments and component_type not in {"device", "algorithm"}:
        raise PluginManifestError(
            "Only Device and Algorithm plugins may contribute Record Catalog fragments"
        )
    _RelativePaths_Validate(record_fragments, "metadata.record_catalog_fragments")
    _BuildTokens_Validate(
        record_fragments,
        "metadata.record_catalog_fragments",
        BUILD_PATH_PATTERN,
    )
    auto_managed_category = metadata.get("auto_managed_protocol_category")
    if auto_managed_category is not None:
        if (
            component_type != "device"
            or auto_managed_category not in ALLOWED_PROTOCOL_CATEGORIES
            or metadata.get("internal") is not True
        ):
            raise PluginManifestError(
                "metadata.auto_managed_protocol_category requires an internal "
                "Device and a valid protocol category"
            )

    requires = data.get("requires", {})
    if not isinstance(requires, dict) or set(requires) - {
        "components",
        "resources",
        "capabilities",
    }:
        raise PluginManifestError("requires contains unknown fields")
    dependencies = _Dependencies_Parse(requires)
    resource_requirements = _ResourceRequirements_Parse(requires)
    resource_provisions, resource_roles, resource_conflicts = _Resources_Parse(
        data.get("resources", {})
    )
    capability_requirements = _CapabilityRequirements_Parse(
        requires.get("capabilities", [])
    )
    provides = _StringTuple_Get(data.get("provides", []), "provides")
    _CapabilityTuple_Validate(provides, "provides")
    transports = _Transports_Parse(data.get("transports"), provides)
    build = _Build_Parse(data.get("build", {}))
    selection = _Selection_Parse(data.get("selection"))
    try:
        if "algorithm_parameters" in data and data["algorithm_parameters"] is None:
            raise ValueError("algorithm_parameters must be an object")
        algorithm_parameters = AlgorithmParameters_Parse(data.get("algorithm_parameters"))
        if "algorithm_parameters" in data and data["type"] != "algorithm":
            raise ValueError("Only algorithm plugins may declare algorithm_parameters")
    except ValueError as error:
        raise PluginManifestError(str(error)) from error
    board = _Board_Parse(data.get("board"))
    hardware_provider = _HardwareProvider_Parse(data.get("hardware_provider"))
    environment = _Environment_Parse(data.get("environment"))
    protocol = _Protocol_Parse(data.get("protocol"))
    platform = _Platform_Parse(data.get("platform"))
    instance_policy = _InstancePolicy_Parse(
        data.get("instance_policy"),
        component_type=component_type,
        legacy_cardinality=data.get("cardinality"),
    )
    instance_resource_binding = _InstanceResourceBinding_Parse(
        metadata.get("instance_resource_binding"),
        component_type=component_type,
        requirements=resource_requirements,
        instance_policy=instance_policy,
    )
    physical_device = _PhysicalDevice_Parse(
        data.get("physical_device"), component_type=component_type
    )
    radio_data = data.get("radio")
    radio = None
    if radio_data is not None:
        expected_radio = {
            "technology", "family", "phy_modes", "frequency_min_hz",
            "frequency_max_hz", "bandwidths_hz", "spreading_factors",
            "coding_rates", "maximum_payload", "maximum_tx_power_dbm",
            "datasheet_capabilities", "modules",
        }
        if component_type != "device" or not isinstance(radio_data, dict) or set(radio_data) != expected_radio:
            raise PluginManifestError("radio metadata requires a Device and complete fields")
        for field_name in ("technology", "family"):
            if not isinstance(radio_data[field_name], str) or not PLUGIN_ID_PATTERN.fullmatch(radio_data[field_name]):
                raise PluginManifestError(f"radio.{field_name} is invalid")
        for field_name in ("phy_modes", "coding_rates"):
            if not isinstance(radio_data[field_name], list) or not radio_data[field_name] or any(not isinstance(item, str) or not item for item in radio_data[field_name]):
                raise PluginManifestError(f"radio.{field_name} is invalid")
        for field_name in ("frequency_min_hz", "frequency_max_hz", "maximum_payload", "maximum_tx_power_dbm"):
            if type(radio_data[field_name]) is not int:
                raise PluginManifestError(f"radio.{field_name} must be integer")
        for field_name in ("bandwidths_hz", "spreading_factors"):
            if not isinstance(radio_data[field_name], list) or not radio_data[field_name] or any(type(item) is not int or item <= 0 for item in radio_data[field_name]):
                raise PluginManifestError(f"radio.{field_name} is invalid")
        if (radio_data["frequency_min_hz"] <= 0 or radio_data["frequency_max_hz"] < radio_data["frequency_min_hz"] or radio_data["maximum_payload"] <= 0):
            raise PluginManifestError("radio frequency range or payload is invalid")
        datasheet = radio_data["datasheet_capabilities"]
        if (
            not isinstance(datasheet, dict)
            or set(datasheet) != {
                "frequency_min_hz", "frequency_max_hz", "maximum_tx_power_dbm", "source"
            }
            or any(type(datasheet[key]) is not int for key in (
                "frequency_min_hz", "frequency_max_hz", "maximum_tx_power_dbm"
            ))
            or datasheet["frequency_min_hz"] <= 0
            or datasheet["frequency_min_hz"] > radio_data["frequency_min_hz"]
            or datasheet["frequency_max_hz"] < radio_data["frequency_max_hz"]
            or datasheet["maximum_tx_power_dbm"] < radio_data["maximum_tx_power_dbm"]
            or not isinstance(datasheet["source"], str)
            or not datasheet["source"].startswith("https://")
        ):
            raise PluginManifestError("radio.datasheet_capabilities is invalid")
        modules = radio_data["modules"]
        if not isinstance(modules, dict) or not modules or any(
            not isinstance(module_id, str) or not PLUGIN_ID_PATTERN.fullmatch(module_id)
            or not isinstance(module, dict) or set(module) != {
                "model", "tx_power_limit_dbm", "supported_tx_powers_dbm",
                "validated_frequency_min_hz", "validated_frequency_max_hz",
            }
            or not isinstance(module["model"], str) or type(module["tx_power_limit_dbm"]) is not int
            or module["tx_power_limit_dbm"] > datasheet["maximum_tx_power_dbm"]
            or not isinstance(module["supported_tx_powers_dbm"], list)
            or not module["supported_tx_powers_dbm"]
            or any(type(power) is not int or power > module["tx_power_limit_dbm"]
                   or power > radio_data["maximum_tx_power_dbm"]
                   for power in module["supported_tx_powers_dbm"])
            or type(module["validated_frequency_min_hz"]) is not int
            or type(module["validated_frequency_max_hz"]) is not int
            or module["validated_frequency_min_hz"] < radio_data["frequency_min_hz"]
            or module["validated_frequency_max_hz"] > radio_data["frequency_max_hz"]
            or module["validated_frequency_min_hz"] > module["validated_frequency_max_hz"]
            for module_id, module in modules.items()
        ):
            raise PluginManifestError("radio.modules is invalid")
        radio = RadioContribution(
            technology=radio_data["technology"], family=radio_data["family"],
            phy_modes=tuple(radio_data["phy_modes"]),
            frequency_min_hz=radio_data["frequency_min_hz"],
            frequency_max_hz=radio_data["frequency_max_hz"],
            bandwidths_hz=tuple(radio_data["bandwidths_hz"]),
            spreading_factors=tuple(radio_data["spreading_factors"]),
            coding_rates=tuple(radio_data["coding_rates"]),
            maximum_payload=radio_data["maximum_payload"],
            maximum_tx_power_dbm=radio_data["maximum_tx_power_dbm"],
            datasheet_capabilities=dict(datasheet),
            modules=dict(modules),
        )

    if (component_type == "board") != (board is not None):
        raise PluginManifestError("board plugins must declare exactly one board block")
    if (component_type == "hardware_configuration_provider") != (
        hardware_provider is not None
    ):
        raise PluginManifestError(
            "hardware configuration provider plugins must declare hardware_provider"
        )
    if (component_type == "development_environment") != (environment is not None):
        raise PluginManifestError(
            "development environment plugins must declare environment"
        )
    if (component_type == "protocol") != (protocol is not None):
        raise PluginManifestError(
            "protocol plugins must declare exactly one protocol block"
        )
    if component_type == "protocol" and protocol.category not in ALLOWED_PROTOCOL_CATEGORIES:
        raise PluginManifestError(
            "protocol plugins must declare one strict protocol.category"
        )
    if (component_type in {"mcu", "mcu_family"}) != (platform is not None):
        raise PluginManifestError(
            "MCU and MCU family plugins must declare a platform contract"
        )
    if component_type == "device":
        device_category = metadata.get("device_category")
        if (
            not isinstance(device_category, str)
            or DEVICE_CATEGORY_PATTERN.fullmatch(device_category) is None
        ):
            raise PluginManifestError(
                "metadata.device_category is invalid; expected one of "
                "sensor.*, link.*, storage.*, actuator.* or indicator.*"
            )
    if selection is not None and component_type not in {"algorithm", "flight_logic"}:
        raise PluginManifestError(
            "only algorithm/flight_logic plugins may select strategy/mode"
        )

    payload = data["payload"]
    if not isinstance(payload, dict) or set(payload) != {"roots"}:
        raise PluginManifestError("payload must contain only roots")
    payload_roots = _StringTuple_Get(payload.get("roots", []), "payload.roots")
    source_free_build = (
        not build.sources
        and not build.protocol_sources
        and not build.strategy_sources
        and not build.asm_sources
        and not build.virtual_sources
        and not build.include_dirs
        and not build.forced_includes
        and not build.linker_script
    )
    declarative_component = source_free_build and (
        selection is not None or metadata.get("declarative") is True
    )
    if (
        not payload_roots
        and component_type not in UTILITY_PLUGIN_TYPES
        and not declarative_component
    ):
        raise PluginManifestError("payload.roots must not be empty")
    _RelativePaths_Validate(payload_roots, "payload")
    _BuildTokens_Validate(payload_roots, "payload.roots", BUILD_PATH_PATTERN)

    manifest = PluginManifest(
        schema_version=0,
        component_id=component_id,
        name=data["name"],
        component_type=component_type,
        component_class=str(data.get("class", "")),
        version=version,
        description=str(data.get("description", "")),
        dependencies=dependencies,
        resource_requirements=resource_requirements,
        resource_provisions=resource_provisions,
        resource_roles=resource_roles,
        resource_conflicts=resource_conflicts,
        provides=provides,
        capability_requirements=capability_requirements,
        transports=transports,
        build=build,
        payload_roots=payload_roots,
        metadata=dict(metadata),
        manifest_path=manifest_path.resolve(),
        instance_policy=instance_policy,
        instance_resource_binding=instance_resource_binding,
        physical_device=physical_device,
        radio=radio,
        selection=selection,
        algorithm_parameters=algorithm_parameters,
        board=board,
        protocol=protocol,
        platform=platform,
        hardware_provider=hardware_provider,
        environment=environment,
        source=source,
        device_variants=dict(device_variants),
    )
    payload_files = {
        path.relative_to(manifest.payload_root).as_posix()
        for path in manifest.PayloadFiles_Get()
    }
    conditional_sources = tuple(
        source
        for variants in build.strategy_sources.values()
        for state_sources in variants.values()
        for source in state_sources
    )
    protocol_conditional_sources = tuple(
        source
        for category_sources in build.protocol_sources.values()
        for source in category_sources
    )
    for build_path in (
        *build.sources,
        *conditional_sources,
        *protocol_conditional_sources,
        *build.asm_sources,
        *build.virtual_sources,
    ):
        if build_path not in payload_files:
            raise PluginManifestError(
                f"Build source is not supplied by payload roots: {build_path}"
            )
    for include_path in build.include_dirs:
        if not (manifest.payload_root / include_path).is_dir():
            raise PluginManifestError(
                f"Build include directory is missing: {include_path}"
            )
    for forced_include in build.forced_includes:
        if forced_include not in payload_files:
            raise PluginManifestError(
                f"Forced include is missing from payload: {forced_include}"
            )
    if build.linker_script and build.linker_script not in payload_files:
        raise PluginManifestError(
            f"Linker script is missing from payload: {build.linker_script}"
        )
    if protocol is not None and protocol.logging_metadata not in payload_files:
        raise PluginManifestError(
            "Protocol logging metadata is missing from payload: "
            f"{protocol.logging_metadata}"
        )
    if board is not None:
        for field_name, relative_path in (
            ("board.ioc_file", board.ioc_file),
            ("board.connections_file", board.connections_file),
        ):
            if not relative_path:
                continue
            target = manifest.package_root.joinpath(*relative_path.split("/"))
            try:
                target.relative_to(manifest.package_root)
            except ValueError as error:
                raise PluginManifestError(f"{field_name} leaves the plugin") from error
            if not target.is_file() or target.is_symlink():
                raise PluginManifestError(f"{field_name} is missing or unsafe")
    return manifest


def PluginManifest_Load(path: Path, *, source: str = "builtin") -> PluginManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PluginManifestError(
            f"Cannot read plugin manifest {path}: {error}"
        ) from error
    if data.get("type") == "mcu":
        family_id = data.get("metadata", {}).get("platform_family_id")
        if family_id:
            if not isinstance(family_id, str) or not PLUGIN_ID_PATTERN.fullmatch(family_id):
                raise PluginManifestError("MCU platform family id is invalid")
            family_path = path.parent.parent / family_id.replace(".", "_") / "plugin.json"
            try:
                family_data = json.loads(family_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise PluginManifestError(
                    f"MCU family backend is unavailable: {family_id}"
                ) from error
            if (family_data.get("id") != family_id
                    or family_data.get("type") != "mcu_family"
                    or not isinstance(family_data.get("platform"), dict)
                    or not isinstance(data.get("platform"), dict)
                    or not {"match_rules"}.issubset(data["platform"])
                    or set(data["platform"]) - {"match_rules", "build_target"}):
                raise PluginManifestError("MCU family platform contract is invalid")
            data = {
                **data,
                "platform": {**family_data["platform"], **data["platform"]},
            }
    manifest = PluginManifest_Parse(data, path, source=source)
    for variant_id in manifest.device_variants:
        PluginManifest_VariantResolve(manifest, variant_id)
    return manifest


def _VariantOverlay_Apply(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _VariantOverlay_Apply(base[key], value)
        else:
            base[key] = deepcopy(value)


def PluginManifest_VariantResolve(manifest: PluginManifest, variant_id: str) -> PluginManifest:
    variant = manifest.device_variants.get(variant_id)
    if variant is None:
        raise PluginManifestError(f"Unknown variant {variant_id} for {manifest.component_id}")
    data = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    data.pop("device_variants", None)
    _VariantOverlay_Apply(data, variant["overrides"])
    return PluginManifest_Parse(data, manifest.manifest_path, source=manifest.source)
