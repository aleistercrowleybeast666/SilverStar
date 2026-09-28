from __future__ import annotations

from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Reconcile

from copy import deepcopy
from dataclasses import dataclass, replace

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import PluginManifest, SelectionKind
from silverstar_fccg.hardware.platform import (
    DetectedMcuFacts,
    DetectedMcuFacts_FromInventory,
    PlatformCompatibilityErrors_Get,
    PlatformMatch_Resolve,
)
from silverstar_fccg.project.capabilities import (
    CapabilityResolution,
    CapabilityResolution_Resolve,
    CapabilitySourceOverrides_Reconcile,
)
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.model import (
    PROTOCOL_CATEGORIES,
    DeviceInstance,
    HardwareConfiguration,
    ProjectModel,
    ProtocolSelection,
)
from silverstar_fccg.project.protocols import (
    ProtocolAutoManagedDevices_Reconcile,
    ProtocolProfileAvailabilities_Get,
)
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    ResourceAssignmentResult,
    ResourceAssignments_Resolve,
    ResourceRequirementOptions_Get,
)
from silverstar_fccg.generator.hardware_preparation import (
    HardwareAssignmentFingerprint_Get,
)
from silverstar_fccg.project.validation import (
    ProjectValidationResult,
    Project_EditValidate,
)


@dataclass(frozen=True, slots=True)
class SelectionAvailability:
    available: bool
    missing_capabilities: tuple[str, ...] = ()
    missing_components: tuple[str, ...] = ()
    reason_code: str = ""


@dataclass(frozen=True, slots=True)
class ConfigurationNotice:
    code: str
    slot: str = ""
    component_id: str = ""
    count: int = 0


@dataclass(frozen=True, slots=True)
class ProjectConfigurationResult:
    model: ProjectModel
    capability_resolution: CapabilityResolution
    resource_resolution: ResourceAssignmentResult
    strategy_availability: dict[str, SelectionAvailability]
    mode_availability: dict[tuple[str, str], SelectionAvailability]
    edit_validation: ProjectValidationResult
    notices: tuple[ConfigurationNotice, ...] = ()
    retained_assignments: int = 0
    cleared_assignments: int = 0
    pending_assignments: int = 0


def PhysicalCapabilities_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> frozenset[str]:
    return frozenset(
        capability
        for instance in model.device_instances
        for capability in catalog.Component_Get(instance.plugin).provides
    )


def _SelectedComponentIdsForStrategy_Get(
    model: ProjectModel, slot: str, component_id: str
) -> tuple[str, ...]:
    candidate = deepcopy(model)
    candidate.strategies[slot] = component_id
    return candidate.ComponentIds_Get()


def _LogicalCapabilities_Get(
    component_ids: tuple[str, ...], catalog: PluginCatalog
) -> frozenset[str]:
    return frozenset(
        capability
        for component_id in component_ids
        for capability in catalog.Component_Get(component_id).provides
    )


def _AutoSelectableCapabilities_Get(catalog: PluginCatalog) -> frozenset[str]:
    provider_counts: dict[str, int] = {}
    for manifest in catalog.Type_Get("device"):
        if manifest.metadata.get("auto_select_when_required") is not True:
            continue
        for capability in manifest.provides:
            provider_counts[capability] = provider_counts.get(capability, 0) + 1
    return frozenset(
        capability
        for capability, provider_count in provider_counts.items()
        if provider_count == 1
    )


def _ManifestAvailability_Get(
    manifest: PluginManifest,
    component_ids: tuple[str, ...],
    catalog: PluginCatalog,
    *,
    additional_capabilities: tuple[str, ...] = (),
    additional_components: tuple[str, ...] = (),
    allow_device_auto_selection: bool = True,
) -> SelectionAvailability:
    selected = set(component_ids)
    capabilities = set(_LogicalCapabilities_Get(component_ids, catalog))
    required_components = tuple(
        dict.fromkeys(
            (
                requirement.component_id
                for requirement in manifest.dependencies
                if not requirement.optional
            )
        )
    ) + tuple(additional_components)
    missing_components = tuple(
        component_id
        for component_id in dict.fromkeys(required_components)
        if component_id not in selected
    )
    required_capabilities = tuple(
        dict.fromkeys(
            (
                requirement.capability
                for requirement in manifest.capability_requirements
            )
        )
    ) + tuple(additional_capabilities)
    missing_capabilities = tuple(
        capability
        for capability in dict.fromkeys(required_capabilities)
        if capability not in capabilities
        and (
            not allow_device_auto_selection
            or capability not in _AutoSelectableCapabilities_Get(catalog)
        )
    )
    compatible_mcus = manifest.metadata.get("compatible_mcus", [])
    incompatible_mcu = (
        isinstance(compatible_mcus, list)
        and bool(compatible_mcus)
        and McuCompatibilityMissing_Is(component_ids, compatible_mcus)
    )
    if incompatible_mcu:
        missing_components = (*missing_components, "mcu.compatibility")
    if missing_capabilities:
        reason_code = "selection.unavailable.capability"
    elif missing_components:
        reason_code = "selection.unavailable.component"
    else:
        reason_code = ""
    return SelectionAvailability(
        available=not missing_capabilities and not missing_components,
        missing_capabilities=missing_capabilities,
        missing_components=missing_components,
        reason_code=reason_code,
    )


def McuCompatibilityMissing_Is(
    component_ids: tuple[str, ...], compatible_mcus: list[object]
) -> bool:
    compatible = {value for value in compatible_mcus if isinstance(value, str)}
    return not compatible.intersection(component_ids)


def StrategyAvailabilities_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> dict[str, SelectionAvailability]:
    values: dict[str, SelectionAvailability] = {}
    for slot in catalog.SelectionSlots_Get(SelectionKind.STRATEGY.value):
        for manifest in catalog.SelectionSlot_Get(slot):
            component_ids = _SelectedComponentIdsForStrategy_Get(
                model, slot, manifest.component_id
            )
            values[manifest.component_id] = _ManifestAvailability_Get(
                manifest, component_ids, catalog
            )
    return values


def ModeOptionAvailabilities_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> dict[tuple[str, str], SelectionAvailability]:
    component_ids = model.ComponentIds_Get()
    values: dict[tuple[str, str], SelectionAvailability] = {}
    for component_id in model.base_components:
        manifest = catalog.Component_Get(component_id)
        selection = manifest.selection
        if selection is None or selection.kind != SelectionKind.MODE:
            continue
        for option in selection.options:
            requirements = selection.option_requirements.get(option)
            values[(selection.slot, option)] = _ManifestAvailability_Get(
                manifest,
                component_ids,
                catalog,
                additional_capabilities=(
                    tuple(
                        requirement.capability
                        for requirement in requirements.capabilities
                    )
                    if requirements is not None
                    else ()
                ),
                additional_components=(
                    requirements.components if requirements is not None else ()
                ),
                allow_device_auto_selection=False,
            )
    return values


def _Strategies_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    notices: list[ConfigurationNotice] = []
    slot_count = len(catalog.SelectionSlots_Get(SelectionKind.STRATEGY.value))
    for _pass in range(max(1, slot_count + 1)):
        changed = False
        availability = StrategyAvailabilities_Get(model, catalog)
        for slot in catalog.SelectionSlots_Get(SelectionKind.STRATEGY.value):
            selected = model.strategies.get(slot)
            if selected is None:
                continue
            selected_availability = availability.get(selected)
            if selected_availability is not None and selected_availability.available:
                continue
            legal = [
                manifest.component_id
                for manifest in catalog.SelectionSlot_Get(slot)
                if availability.get(
                    manifest.component_id, SelectionAvailability(False)
                ).available
            ]
            if len(legal) == 1:
                model.strategies[slot] = legal[0]
                notices.append(
                    ConfigurationNotice(
                        "configuration.strategy_auto_selected",
                        slot=slot,
                        component_id=legal[0],
                    )
                )
            else:
                model.strategies[slot] = None
                notices.append(
                    ConfigurationNotice(
                        (
                            "configuration.strategy_reselect"
                            if legal
                            else "configuration.strategy_unsupported"
                        ),
                        slot=slot,
                        component_id=selected,
                    )
                )
            changed = True
        if not changed:
            break
    return tuple(notices)


def _Modes_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    availability = ModeOptionAvailabilities_Get(model, catalog)
    notices: list[ConfigurationNotice] = []
    for slot, values in tuple(model.modes.items()):
        retained = [
            option
            for option in values
            if availability.get((slot, option), SelectionAvailability(False)).available
        ]
        if retained != values:
            model.modes[slot] = retained
            notices.append(
                ConfigurationNotice(
                    "configuration.mode_options_removed",
                    slot=slot,
                    count=len(values) - len(retained),
                )
            )
    return tuple(notices)


def _ModeParameters_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> None:
    reconciled: dict[str, dict[str, dict[str, float | int]]] = {}
    for component_id in model.base_components:
        manifest = catalog.Component_Get(component_id)
        selection = manifest.selection
        if selection is None or selection.kind != SelectionKind.MODE:
            continue
        slot_values = model.mode_parameters.get(selection.slot, {})
        option_values: dict[str, dict[str, float | int]] = {}
        for option, definitions in selection.parameters.items():
            current = slot_values.get(option, {})
            option_values[option] = {
                definition.parameter_id: current.get(
                    definition.parameter_id, definition.default
                )
                for definition in definitions
            }
        if option_values:
            reconciled[selection.slot] = option_values
    model.mode_parameters = reconciled


def _ProtocolProfiles_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    notices: list[ConfigurationNotice] = []
    reconciled = {
        category: model.protocols.get(category)
        for category in PROTOCOL_CATEGORIES
    }
    for category in PROTOCOL_CATEGORIES:
        selected = reconciled[category]
        if selected is None:
            continue
        try:
            manifest = catalog.Component_Get(selected.component)
        except FccgError:
            reconciled[category] = None
            notices.append(
                ConfigurationNotice(
                    "configuration.protocol_cleared",
                    slot=category,
                    component_id=selected.component,
                )
            )
            continue
        protocol = manifest.protocol
        if protocol is None or protocol.category != category:
            reconciled[category] = None
            notices.append(
                ConfigurationNotice(
                    "configuration.protocol_cleared",
                    slot=category,
                    component_id=selected.component,
                )
            )
            continue
        profile_ids = {
            profile.profile_id
            for profile in protocol.profiles.get(category, ())
        }
        if selected.profile not in profile_ids:
            reconciled[category] = None
            notices.append(
                ConfigurationNotice(
                    "configuration.protocol_cleared",
                    slot=category,
                    component_id=selected.component,
                )
            )
            continue
        if (
            not selected.manifest_sha256
            or selected.version != manifest.version
        ):
            reconciled[category] = ProtocolSelection(
                component=selected.component,
                version=manifest.version,
                profile=selected.profile,
                manifest_sha256=manifest.ManifestSha256_Get(),
            )
    model.protocols = reconciled
    ProtocolAutoManagedDevices_Reconcile(model, catalog)
    availability = ProtocolProfileAvailabilities_Get(model, catalog)
    for category in PROTOCOL_CATEGORIES:
        selected = model.protocols[category]
        if selected is None:
            continue
        selected_availability = availability.get(
            (category, selected.component, selected.profile)
        )
        if selected_availability is not None and selected_availability.available:
            continue
        model.protocols[category] = None
        notices.append(
            ConfigurationNotice(
                "configuration.protocol_transport_removed",
                slot=category,
                component_id=selected.component,
            )
        )
    ProtocolAutoManagedDevices_Reconcile(model, catalog)
    return tuple(notices)


def _HardwareAssignmentConfirmation_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> None:
    fingerprint = model.hardware.assignment_fingerprint
    if fingerprint and fingerprint != HardwareAssignmentFingerprint_Get(
        model, catalog
    ):
        model.hardware = HardwareConfiguration(
            **{
                field_name: getattr(model.hardware, field_name)
                for field_name in model.hardware.__dataclass_fields__
                if field_name != "assignment_fingerprint"
            },
            assignment_fingerprint="",
        )


def _Hardware_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    if model.hardware.mode == "unselected":
        model.board = ""
        model.resource_assignments = {}
        model.build = replace(model.build, target_profile="")
        return ()
    reset = False
    if model.hardware.mode == "board_plugin":
        if not model.board:
            reset = True
        else:
            board = catalog.Component_Get(model.board)
            if board.board is None:
                reset = True
            else:
                inventory = BoardHardwareInventory_Get(board)
                if inventory is None:
                    raise FccgError(
                        "error.platform_match",
                        {},
                        f"Board {model.board} has no CubeMX inventory",
                    )
                provider_manifest = catalog.Component_Get(board.board.provider)
                provider = provider_manifest.hardware_provider
                if provider is None:
                    raise FccgError(
                        "error.platform_match",
                        {},
                        f"Board {model.board} has no hardware provider contract",
                    )
                matched = PlatformMatch_Resolve(
                    DetectedMcuFacts_FromInventory(
                        inventory,
                        vendor=provider.vendor,
                        provider=provider.handler,
                    ),
                    catalog,
                )
                model.mcu = matched.selected.component_id
                matched_manifest = catalog.Component_Get(model.mcu)
                model.hardware = replace(
                    model.hardware,
                    provider=board.board.provider,
                    ioc_file=board.board.ioc_file,
                    mcu=inventory.mcu_part,
                    platform_component=matched_manifest.component_id,
                    platform_version=matched_manifest.version,
                    platform_manifest_sha256=matched_manifest.ManifestSha256_Get(),
                    cubemx_version=inventory.cubemx_version,
                    firmware_package=inventory.firmware_package,
                    hal_cmsis_source_policy=(
                        matched_manifest.platform.compatibility.source_policy
                        if matched_manifest.platform is not None
                        else ""
                    ),
                    i2c_external_pullup_confirmations={},
                    capabilities=tuple(
                        sorted(
                            {
                                f"peripheral.{resource.kind}"
                                for resource in inventory.HardwareResources_Get()
                            }
                        )
                    ),
                    inventory=inventory.Dictionary_Get(),
                    source_label=board.name,
                )
                reset = model.mcu not in board.board.compatible_mcus
    elif model.hardware.mode == "custom":
        provider = (
            catalog.Component_Get(model.hardware.provider)
            if model.hardware.provider
            else None
        )
        reset = (
            provider is None
            or provider.hardware_provider is None
        )
        if not reset and model.hardware.snapshot_id:
            inventory = model.hardware.inventory
            matched = PlatformMatch_Resolve(
                DetectedMcuFacts(
                    vendor=provider.hardware_provider.vendor,
                    part=str(
                        inventory.get("mcu_part", model.hardware.mcu)
                    ),
                    family=str(inventory.get("mcu_family", "")),
                    package=str(inventory.get("package", "")),
                    core=str(inventory.get("core", "")),
                    provider=provider.hardware_provider.handler,
                ),
                catalog,
            )
            model.mcu = matched.selected.component_id
            matched_manifest = catalog.Component_Get(model.mcu)
            model.hardware = replace(
                model.hardware,
                platform_component=matched_manifest.component_id,
                platform_version=matched_manifest.version,
                platform_manifest_sha256=matched_manifest.ManifestSha256_Get(),
                cubemx_version=str(
                    inventory.get(
                        "cubemx_version", model.hardware.cubemx_version
                    )
                ),
                firmware_package=str(
                    inventory.get(
                        "firmware_package", model.hardware.firmware_package
                    )
                ),
                hal_cmsis_source_policy=(
                    matched_manifest.platform.compatibility.source_policy
                    if matched_manifest.platform is not None
                    else ""
                ),
                i2c_external_pullup_confirmations={
                    resource_id: binding
                    for resource_id, binding in (
                        model.hardware.i2c_external_pullup_confirmations.items()
                    )
                    if binding.get("source_digest")
                    == model.hardware.source_digest
                    and binding.get("snapshot_id")
                    == model.hardware.snapshot_id
                },
            )
    if not reset:
        platform_manifest = catalog.Component_Get(model.mcu)
        if platform_manifest.platform is None:
            raise FccgError(
                "error.platform_match",
                {},
                f"MCU {model.mcu} has no Platform contract",
            )
        model.build = replace(
            model.build,
            target_profile=platform_manifest.platform.build_target_profile,
        )
        return ()
    model.board = ""
    model.hardware = HardwareConfiguration()
    model.resource_assignments = {}
    model.build = replace(model.build, target_profile="")
    return (ConfigurationNotice("configuration.hardware_reset"),)


def _ResourceAssignments_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ResourceAssignmentResult, int, int, int]:
    previous = dict(model.resource_assignments)
    options = ResourceRequirementOptions_Get(model, catalog)
    valid_options = {option.key: option for option in options}
    if model.hardware.mode == "unselected":
        model.resource_assignments = {}
    else:
        retained: dict[str, str] = {}
        for key, assignment in previous.items():
            option = valid_options.get(key)
            if option is None or not assignment:
                continue
            if assignment not in option.candidates:
                continue
            retained[key] = assignment
        model.resource_assignments = retained
    result = ResourceAssignments_Resolve(model, catalog, auto_assign=True)
    retained_count = sum(
        1
        for key, assignment in previous.items()
        if model.resource_assignments.get(key) == assignment
    )
    cleared_count = sum(
        1
        for key, assignment in previous.items()
        if assignment and model.resource_assignments.get(key) != assignment
    )
    required_keys = {option.key for option in options if option.required}
    pending_count = sum(
        1 for key in required_keys if not model.resource_assignments.get(key)
    )
    return result, retained_count, cleared_count, pending_count


def _RequiredDependencies_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> None:
    """Retain non-selectable shared dependencies required by selected components."""
    while True:
        selected = set(model.ComponentIds_Get())
        additions: list[str] = []
        for component_id in tuple(selected):
            manifest = catalog.Component_Get(component_id)
            for requirement in manifest.dependencies:
                if requirement.optional or requirement.component_id in selected:
                    continue
                dependency = catalog.Component_Get(requirement.component_id)
                if dependency.selection is not None:
                    continue
                additions.append(requirement.component_id)
        additions = list(dict.fromkeys(additions))
        if not additions:
            return
        model.base_components.extend(additions)


def _DeviceInstanceId_Next(
    model: ProjectModel, preferred: str
) -> str:
    selected = {instance.instance_id for instance in model.device_instances}
    if preferred not in selected:
        return preferred
    suffix = 1
    while f"{preferred}_{suffix}" in selected:
        suffix += 1
    return f"{preferred}_{suffix}"


def _RequiredLogicalDevices_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    """Select a unique declarative device when a live requirement needs it."""
    notices: list[ConfigurationNotice] = []
    device_candidates = tuple(
        manifest
        for manifest in catalog.Type_Get("device")
        if manifest.metadata.get("auto_select_when_required") is True
    )
    for _pass in range(len(device_candidates) + 1):
        resolution = CapabilityResolution_Resolve(model, catalog)
        missing_capabilities = tuple(
            dict.fromkeys(requirement.capability for requirement in resolution.missing)
        )
        additions = []
        selected_plugins = set(model.DevicePluginIds_Get())
        for capability in missing_capabilities:
            providers = [
                manifest
                for manifest in device_candidates
                if capability in manifest.provides
                and manifest.component_id not in selected_plugins
            ]
            if len(providers) == 1:
                additions.append(providers[0])
                selected_plugins.add(providers[0].component_id)
        if not additions:
            break
        for manifest in additions:
            preferred = str(
                manifest.metadata.get(
                    "default_instance_id", manifest.component_class or "device0"
                )
            )
            model.device_instances.append(
                DeviceInstance(
                    _DeviceInstanceId_Next(model, preferred),
                    manifest.component_id,
                )
            )
            notices.append(
                ConfigurationNotice(
                    "configuration.logical_device_auto_selected",
                    component_id=manifest.component_id,
                )
            )
    return tuple(notices)


def _UnavailableOptionalDevices_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ConfigurationNotice, ...]:
    """Retain user-selected devices; strict validation reports incompatibility."""
    del model, catalog
    return ()


def _LegacyLandingStrategy_Reconcile(model: ProjectModel) -> None:
    legacy_component = "silverstar.flight_logic.landing.baro_imu_window"
    if model.strategies.get("landing") == legacy_component:
        model.strategies["landing"] = (
            "silverstar.flight_logic.landing.baro_imu_window_strategy"
        )


def ProjectConfiguration_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> ProjectConfigurationResult:
    candidate = deepcopy(model)
    _LegacyLandingStrategy_Reconcile(candidate)
    _RequiredDependencies_Reconcile(candidate, catalog)
    notices = [*_Hardware_Reconcile(candidate, catalog)]
    notices.extend(_UnavailableOptionalDevices_Reconcile(candidate, catalog))
    notices.extend(_Strategies_Reconcile(candidate, catalog))
    notices.extend(_Modes_Reconcile(candidate, catalog))
    _ModeParameters_Reconcile(candidate, catalog)
    AlgorithmParameters_Reconcile(candidate, catalog)
    notices.extend(_ProtocolProfiles_Reconcile(candidate, catalog))
    notices.extend(_RequiredLogicalDevices_Reconcile(candidate, catalog))
    capability_resolution = CapabilitySourceOverrides_Reconcile(candidate, catalog)
    (
        resource_resolution,
        retained,
        cleared,
        pending,
    ) = _ResourceAssignments_Reconcile(candidate, catalog)
    _HardwareAssignmentConfirmation_Reconcile(candidate, catalog)
    LoggingProfile_Reconcile(candidate, catalog)
    edit_validation = Project_EditValidate(candidate, catalog)
    return ProjectConfigurationResult(
        model=candidate,
        capability_resolution=capability_resolution,
        resource_resolution=resource_resolution,
        strategy_availability=StrategyAvailabilities_Get(candidate, catalog),
        mode_availability=ModeOptionAvailabilities_Get(candidate, catalog),
        edit_validation=edit_validation,
        notices=tuple(notices),
        retained_assignments=retained,
        cleared_assignments=cleared,
        pending_assignments=pending,
    )
