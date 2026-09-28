from __future__ import annotations

import math
import re
from dataclasses import dataclass

from silverstar_fccg.app.version import (
    SILVERSTAR_BUILD_ID,
    SILVERSTAR_CORE_COMPONENT_ID,
    SILVERSTAR_PLATFORM_VERSION,
)
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.hardware.platform import PlatformCompatibilityErrors_Get
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import SelectionKind
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve
from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LogPolicyLevel,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    ProjectModel,
    ProjectModel_Parse,
    ProjectModelError,
)
from silverstar_fccg.project.protocols import ProtocolResolution_Resolve
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get,
    ResourceAssignments_Resolve,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    level: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ProjectValidationResult:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)


def _ComponentType_Validate(
    catalog: PluginCatalog,
    component_id: str,
    expected_type: str,
    issues: list[ValidationIssue],
) -> None:
    try:
        manifest = catalog.Component_Get(component_id)
    except ValueError as error:
        issues.append(ValidationIssue("error", "missing_component", str(error)))
        return
    if manifest.component_type != expected_type:
        issues.append(
            ValidationIssue(
                "error",
                "component_type",
                f"{component_id} is {manifest.component_type}, expected {expected_type}",
            )
        )


def _Strategies_Validate(
    model: ProjectModel,
    catalog: PluginCatalog,
    issues: list[ValidationIssue],
) -> None:
    declared_slots = set(catalog.SelectionSlots_Get(SelectionKind.STRATEGY.value))
    selected_slots = set(model.strategies)
    for slot in sorted(selected_slots - declared_slots):
        issues.append(
            ValidationIssue(
                "error", "strategy_slot", f"Unknown strategy slot: {slot}"
            )
        )
    for slot in sorted(declared_slots - selected_slots):
        candidates = catalog.SelectionSlot_Get(slot)
        if any(
            component.selection is not None and component.selection.required
            for component in candidates
        ):
            issues.append(
                ValidationIssue(
                    "error", "strategy_required", f"Strategy slot {slot} is required"
                )
            )
    for slot, component_id in sorted(model.strategies.items()):
        candidates = catalog.SelectionSlot_Get(slot)
        if component_id is None:
            if not candidates or not all(
                component.selection is not None
                and component.selection.allow_none
                and not component.selection.required
                for component in candidates
            ):
                issues.append(
                    ValidationIssue(
                        "error",
                        "strategy_none",
                        f"Strategy slot {slot} does not allow None",
                    )
                )
            continue
        try:
            manifest = catalog.Component_Get(component_id)
        except ValueError as error:
            issues.append(ValidationIssue("error", "missing_component", str(error)))
            continue
        selection = manifest.selection
        if (
            selection is None
            or selection.kind != SelectionKind.STRATEGY
            or selection.slot != slot
        ):
            issues.append(
                ValidationIssue(
                    "error",
                    "strategy_component",
                    f"{component_id} does not implement strategy slot {slot}",
                )
            )


def _Modes_Validate(
    model: ProjectModel,
    catalog: PluginCatalog,
    issues: list[ValidationIssue],
) -> None:
    owners = {
        manifest.selection.slot: manifest
        for component_id in model.base_components
        for manifest in (catalog.Component_Get(component_id),)
        if manifest.selection is not None
        and manifest.selection.kind == SelectionKind.MODE
    }
    for slot in sorted(set(model.modes) - set(owners)):
        issues.append(
            ValidationIssue("error", "mode_slot", f"Unknown active mode slot: {slot}")
        )
    for slot, manifest in owners.items():
        selection = manifest.selection
        assert selection is not None
        values = model.modes.get(slot, [])
        unknown = set(values) - set(selection.options)
        if unknown:
            issues.append(
                ValidationIssue(
                    "error",
                    "mode_option",
                    f"Mode slot {slot} contains unknown options: {', '.join(sorted(unknown))}",
                )
            )
        if not selection.allow_multiple and len(values) > 1:
            issues.append(
                ValidationIssue(
                    "error", "mode_multiple", f"Mode slot {slot} is not multi-select"
                )
            )
        if not selection.allow_none and not values:
            issues.append(
                ValidationIssue(
                    "error", "mode_required", f"Mode slot {slot} requires a selection"
                )
            )
        selected_components = set(model.ComponentIds_Get())
        for option in values:
            requirements = selection.option_requirements.get(option)
            if requirements is None:
                continue
            missing_components = tuple(
                component_id
                for component_id in requirements.components
                if component_id not in selected_components
            )
            if missing_components:
                issues.append(
                    ValidationIssue(
                        "error",
                        "mode_component",
                        f"Mode option {slot}.{option} requires components: "
                        + ", ".join(missing_components),
                    )
                )


def _ModeParameters_Validate(
    model: ProjectModel,
    catalog: PluginCatalog,
    issues: list[ValidationIssue],
) -> None:
    owners = {
        manifest.selection.slot: manifest.selection
        for component_id in model.base_components
        for manifest in (catalog.Component_Get(component_id),)
        if manifest.selection is not None
        and manifest.selection.kind == SelectionKind.MODE
    }
    for slot in sorted(set(model.mode_parameters) - set(owners)):
        issues.append(
            ValidationIssue(
                "error",
                "mode_parameter_slot",
                f"Unknown mode parameter slot: {slot}",
            )
        )
    for slot, selection in owners.items():
        options = model.mode_parameters.get(slot, {})
        declared_options = set(selection.parameters)
        for option in sorted(set(options) - declared_options):
            issues.append(
                ValidationIssue(
                    "error",
                    "mode_parameter_option",
                    f"Unknown mode parameter option: {slot}.{option}",
                )
            )
        for option, definitions in selection.parameters.items():
            values = options.get(option, {})
            expected_ids = {definition.parameter_id for definition in definitions}
            if set(values) != expected_ids:
                issues.append(
                    ValidationIssue(
                        "error",
                        "mode_parameter_fields",
                        f"Mode parameters for {slot}.{option} have missing or unknown fields",
                    )
                )
                continue
            if option not in model.modes.get(slot, []):
                continue
            for definition in definitions:
                value = values[definition.parameter_id]
                if (
                    definition.value_type == "integer"
                    and not isinstance(value, int)
                ) or not (
                    math.isfinite(float(value))
                    and
                    float(definition.minimum)
                    <= float(value)
                    <= float(definition.maximum)
                ):
                    issues.append(
                        ValidationIssue(
                            "error",
                            "mode_parameter_range",
                            f"Mode parameter {slot}.{option}.{definition.parameter_id} "
                            f"must be in [{definition.minimum}, {definition.maximum}]",
                        )
                    )


def _ProtocolProfiles_Validate(
    model: ProjectModel,
    catalog: PluginCatalog,
    issues: list[ValidationIssue],
) -> None:
    for category, selected in sorted(model.protocols.items()):
        if selected is None:
            continue
        try:
            manifest = catalog.Component_Get(selected.component)
        except FccgError as error:
            issues.append(
                ValidationIssue("error", "protocol_component", str(error))
            )
            continue
        if manifest.component_type != "protocol":
            issues.append(
                ValidationIssue(
                    "error",
                    "protocol_component_type",
                    f"Protocol {category} selects non-Protocol component "
                    f"{selected.component}",
                )
            )
            continue
        contribution = manifest.protocol
        if contribution is None or contribution.category != category:
            issues.append(
                ValidationIssue(
                    "error",
                    "protocol_category",
                    f"Protocol {category} component {selected.component} "
                    "declares an incompatible category",
                )
            )
            continue
        if selected.version != manifest.version:
            issues.append(
                ValidationIssue(
                    "error",
                    "protocol_version_lock",
                    f"Protocol {category}/{selected.component} is locked to "
                    f"version {selected.version}, installed version is "
                    f"{manifest.version}",
                )
            )
        installed_hash = manifest.ManifestSha256_Get()
        if selected.manifest_sha256 != installed_hash:
            issues.append(
                ValidationIssue(
                    "error",
                    "protocol_manifest_lock",
                    f"Protocol {category}/{selected.component}/{selected.profile} "
                    "manifest SHA-256 does not match the project lock",
                )
            )
        profiles = contribution.profiles.get(category, ())
        if selected.profile not in {
            profile.profile_id for profile in profiles
        }:
            issues.append(
                ValidationIssue(
                    "error",
                    "protocol_profile",
                    f"Protocol {category}/{selected.component} does not provide "
                    f"Profile {selected.profile}",
                )
            )
    resolution = ProtocolResolution_Resolve(model, catalog)
    issues.extend(
        ValidationIssue("error", issue.code, issue.message)
        for issue in resolution.issues
    )


def _Hardware_Validate(
    model: ProjectModel,
    catalog: PluginCatalog,
    issues: list[ValidationIssue],
) -> None:
    def inventory_contracts_validate(inventory: dict) -> None:
        timebase = inventory.get("timebase", {})
        if (
            not isinstance(timebase, dict)
            or timebase.get("kind") != "tim"
            or timebase.get("errors")
            or not timebase.get("handle")
            or not timebase.get("instance")
            or timebase.get("counter_frequency_hz") != 1_000_000
            or timebase.get("period_counts") != 1_000
            or timebase.get("tick_frequency_hz") != 1_000
        ):
            detail = (
                "; ".join(str(value) for value in timebase.get("errors", ()))
                if isinstance(timebase, dict)
                else "missing inventory"
            )
            issues.append(
                ValidationIssue(
                    "error",
                    "hardware_timebase",
                    "CubeMX HAL TIM Timebase contract is invalid / "
                    f"CubeMX HAL TIM 时间基准合同无效: {detail or 'unproven'}",
                )
            )
        inventory_issues = inventory.get("issues", ())
        if isinstance(inventory_issues, (list, tuple)):
            for issue in inventory_issues:
                if str(issue).startswith("inventory.timebase_pwm_conflict"):
                    issues.append(
                        ValidationIssue(
                            "error", "hardware_timebase_pwm_conflict", str(issue)
                        )
                    )

    mcu = catalog.Component_Get(model.mcu)
    platform_lock = (
        model.hardware.platform_component,
        model.hardware.platform_version,
        model.hardware.platform_manifest_sha256,
    )
    if model.hardware.mode != "unselected" and not all(platform_lock):
        issues.append(
            ValidationIssue(
                "warning",
                "platform_lock",
                "Detected MCU/Platform plugin lock is incomplete; it will be "
                "filled by hardware reconciliation before the next save",
            )
        )
    elif all(platform_lock):
        if model.hardware.platform_component != model.mcu:
            issues.append(
                ValidationIssue(
                    "error",
                    "platform_lock_component",
                    "Hardware Platform lock does not match the selected MCU component",
                )
            )
        if model.hardware.platform_version != mcu.version:
            issues.append(
                ValidationIssue(
                    "error",
                    "platform_lock_version",
                    "Installed MCU/Platform plugin version differs from the project lock",
                )
            )
        if (
            model.hardware.platform_manifest_sha256
            != mcu.ManifestSha256_Get()
        ):
            issues.append(
                ValidationIssue(
                    "error",
                    "platform_lock_hash",
                    "Installed MCU/Platform manifest differs from the project lock",
                )
            )
    mcu_vendor = str(mcu.metadata.get("vendor", ""))
    if mcu_vendor.casefold() != "stm32":
        issues.append(
            ValidationIssue(
                "error",
                "mcu_scope",
                "FCCG v0.x exposes STM32 targets only",
            )
        )
    if model.hardware.mode == "unselected":
        issues.append(
            ValidationIssue(
                "error",
                "hardware_unselected",
                "A Board or imported STM32CubeMX hardware configuration is required",
            )
        )
        return
    if mcu.platform is None:
        issues.append(
            ValidationIssue(
                "error",
                "platform_contract",
                f"MCU component {mcu.component_id} has no Platform contract",
            )
        )
        return
    if model.build.target_profile != mcu.platform.build_target_profile:
        issues.append(
            ValidationIssue(
                "error",
                "target_profile_lock",
                f"Build Target Profile must match MCU Platform contract "
                f"{mcu.platform.build_target_profile!r}",
            )
        )
    for message in PlatformCompatibilityErrors_Get(
        mcu,
        cubemx_version=model.hardware.cubemx_version,
        firmware_package=model.hardware.firmware_package,
        source_policy=model.hardware.hal_cmsis_source_policy,
    ):
        issues.append(
            ValidationIssue("error", "platform_compatibility", message)
        )
    expected_policy = mcu.platform.compatibility.source_policy
    if model.hardware.hal_cmsis_source_policy != expected_policy:
        issues.append(
            ValidationIssue(
                "error",
                "hal_cmsis_source_policy",
                f"Platform {mcu.component_id} requires HAL/CMSIS source policy "
                f"{expected_policy}, got "
                f"{model.hardware.hal_cmsis_source_policy or 'missing'}",
            )
        )
    if model.hardware.mode == "board_plugin":
        board = catalog.Component_Get(model.board)
        if board.board is None:
            issues.append(
                ValidationIssue("error", "board_manifest", "Board metadata is missing")
            )
            return
        if model.mcu not in board.board.compatible_mcus:
            issues.append(
                ValidationIssue(
                    "error",
                    "board_mcu",
                    f"Board {model.board} is not compatible with MCU {model.mcu}",
                )
            )
        if board.board.source_kind != "verified_builtin":
            issues.append(
                ValidationIssue(
                    "warning",
                    "board_unverified",
                    f"Board {model.board} is not an official verified builtin",
                )
            )
        inventory = BoardHardwareInventory_Get(board)
        if inventory is None:
            issues.append(
                ValidationIssue(
                    (
                        "warning"
                        if board.board.source_kind == "third_party"
                        else "error"
                    ),
                    "board_ioc",
                    "Board plugin does not declare a CubeMX .ioc inventory",
                )
            )
        else:
            if model.hardware.cubemx_version != inventory.cubemx_version:
                issues.append(
                    ValidationIssue(
                        "error",
                        "board_cubemx_version",
                        "Board CubeMX version does not match persisted hardware facts",
                    )
                )
            if model.hardware.firmware_package != inventory.firmware_package:
                issues.append(
                    ValidationIssue(
                        "error",
                        "board_firmware_package",
                        "Board STM32Cube firmware package does not match persisted hardware facts",
                    )
                )
            expected_mcu = re.sub(
                r"[^A-Z0-9]", "", str(mcu.metadata.get("mcu_model", "")).upper()
            )
            actual_mcu = re.sub(r"[^A-Z0-9]", "", inventory.mcu_part.upper())
            if expected_mcu and actual_mcu != expected_mcu:
                issues.append(
                    ValidationIssue(
                        "error",
                        "board_ioc_mcu",
                        f"Board .ioc MCU {inventory.mcu_part} does not match {expected_mcu}",
                    )
                )
            for issue_code in inventory.issues:
                issues.append(
                    ValidationIssue(
                        (
                            "error"
                            if issue_code.startswith(
                                ("inventory.timebase:", "inventory.fatfs:")
                            )
                            else "warning"
                        ),
                        "board_ioc_inventory",
                        issue_code,
                    )
                )
            inventory_contracts_validate(inventory.Dictionary_Get())
        return
    if not (
        model.hardware.snapshot_id
        and model.hardware.ioc_file
        and model.hardware.mcu
        and model.hardware.source_digest
        and model.hardware.inventory
    ):
        issues.append(
            ValidationIssue(
                "error",
                "hardware_import_incomplete",
                "Custom STM32CubeMX hardware import metadata is incomplete",
            )
        )
        return
    provider = catalog.Component_Get(model.hardware.provider)
    if provider.hardware_provider is None:
        issues.append(
            ValidationIssue(
                "error", "hardware_provider", "Hardware provider metadata is missing"
            )
        )
        return
    if provider.hardware_provider.vendor != mcu_vendor:
        issues.append(
            ValidationIssue(
                "error",
                "hardware_vendor",
                f"Provider vendor {provider.hardware_provider.vendor} does not match MCU vendor {mcu_vendor}",
            )
        )
    expected_mcu = re.sub(
        r"[^A-Z0-9]", "", str(mcu.metadata.get("mcu_model", "")).upper()
    )
    imported_mcu = re.sub(r"[^A-Z0-9]", "", model.hardware.mcu.upper())
    if expected_mcu and not (
        imported_mcu == expected_mcu
        or (len(imported_mcu) >= 11 and expected_mcu.startswith(imported_mcu[:11]))
    ):
        issues.append(
            ValidationIssue(
                "error",
                "hardware_mcu",
                f"Imported CubeMX MCU {model.hardware.mcu} does not match {expected_mcu}",
            )
        )
    hardware_prefix = "HardwareGenerated/STM32CubeMX/"
    if any(
        not path.startswith(hardware_prefix)
        for path in (*model.hardware.build_sources, *model.hardware.asm_sources, *model.hardware.include_dirs)
    ):
        issues.append(
            ValidationIssue(
                "error",
                "hardware_path",
                "Custom hardware build paths must remain below HardwareGenerated/STM32CubeMX",
            )
        )
    inventory = model.hardware.inventory
    inventory_contracts_validate(inventory)
    if model.hardware.cubemx_version != str(
        inventory.get("cubemx_version", "")
    ) or model.hardware.firmware_package != str(
        inventory.get("firmware_package", "")
    ):
        issues.append(
            ValidationIssue(
                "error",
                "hardware_compatibility_facts",
                "Persisted CubeMX/HAL compatibility facts do not match the imported inventory",
            )
        )
    if model.hardware.hal_cmsis_source_policy == "plugin_payload_authoritative":
        allowed_source_prefixes = (
            hardware_prefix + "Core/Src/",
            hardware_prefix + "FATFS/App/",
            hardware_prefix + "FATFS/Target/",
        )
        invalid_build_paths = tuple(
            path
            for path in model.hardware.build_sources
            if not path.startswith(allowed_source_prefixes)
            or not path.casefold().endswith(".c")
        )
        allowed_include_paths = {
            hardware_prefix + "Core/Inc",
            hardware_prefix + "FATFS/App",
            hardware_prefix + "FATFS/Target",
        }
        invalid_include_paths = tuple(
            path
            for path in model.hardware.include_dirs
            if path not in allowed_include_paths
        )
        if (
            invalid_build_paths
            or invalid_include_paths
            or model.hardware.asm_sources
            or model.hardware.linker_script
        ):
            issues.append(
                ValidationIssue(
                    "error",
                    "hardware_source_policy",
                    "plugin_payload_authoritative permits only imported Core and "
                    "CubeMX FatFs App/Target glue; imported HAL/CMSIS, FatFs core, "
                    "startup and linker artifacts must not enter the source graph",
                )
            )
    if not model.hardware.risk_acknowledged:
        issues.append(
            ValidationIssue(
                "error",
                "hardware_risk",
                "Custom hardware risk acknowledgement is required",
            )
        )
    issues.append(
        ValidationIssue(
            "warning",
            "hardware_manual",
            "Custom hardware is not officially hardware-validated by SilverStar",
        )
    )
    if not model.hardware.inventory:
        issues.append(
            ValidationIssue(
                "error",
                "hardware_inventory",
                "Imported CubeMX hardware inventory is missing",
            )
        )


def Project_Validate(model: ProjectModel, catalog: PluginCatalog) -> ProjectValidationResult:
    issues: list[ValidationIssue] = []
    try:
        ProjectModel_Parse(model.Dictionary_Get())
    except ProjectModelError as error:
        return ProjectValidationResult(
            (ValidationIssue("error", "project_model", str(error)),)
        )
    try:
        catalog = catalog.ProjectView_Get(model)
    except ValueError as error:
        return ProjectValidationResult(
            (ValidationIssue("error", "device_variant", str(error)),)
        )
    if model.core == SILVERSTAR_CORE_COMPONENT_ID and (
        model.identity.firmware_version != SILVERSTAR_PLATFORM_VERSION
        or model.identity.build_target != SILVERSTAR_BUILD_ID
    ):
        issues.append(
            ValidationIssue(
                "error",
                "platform_identity",
                "Official SilverStar core and project version identity do not match",
            )
        )
    if "silverstar.core.0_0_9" in model.component_provenance:
        issues.append(
            ValidationIssue(
                "error",
                "pre_release_rebuild_required",
                "This 0.0.9 project contains project-owned pre-release payload; "
                "create a new 0.1.0 output directory instead of mixing payload trains",
            )
        )
    raw_components = [model.core, model.mcu, model.board, model.os]
    raw_components.extend(model.base_components)
    raw_components.extend(
        component_id
        for component_id in model.strategies.values()
        if component_id is not None
    )
    raw_components.extend(model.ProtocolComponentIds_Get())
    raw_components.append(model.development_environment)
    if model.hardware.mode == "custom":
        raw_components.append(model.hardware.provider)
    raw_components = [component_id for component_id in raw_components if component_id]
    if len(raw_components) != len(set(raw_components)):
        issues.append(
            ValidationIssue(
                "error", "duplicate_component", "A component is selected twice"
            )
        )

    for expected_type, component_id in (
        ("core", model.core),
        ("mcu", model.mcu),
        ("os", model.os),
        ("development_environment", model.development_environment),
    ):
        _ComponentType_Validate(catalog, component_id, expected_type, issues)
    if model.hardware.mode == "board_plugin":
        _ComponentType_Validate(catalog, model.board, "board", issues)
    elif model.hardware.mode == "custom":
        _ComponentType_Validate(
            catalog,
            model.hardware.provider,
            "hardware_configuration_provider",
            issues,
        )
    devices_by_class: dict[str, list[str]] = {}
    devices_by_plugin: dict[str, list[str]] = {}
    for instance in model.device_instances:
        _ComponentType_Validate(catalog, instance.plugin, "device", issues)
        try:
            manifest = catalog.Component_Get(instance.plugin)
        except ValueError:
            continue
        devices_by_class.setdefault(manifest.component_class, []).append(
            instance.instance_id
        )
        devices_by_plugin.setdefault(instance.plugin, []).append(
            instance.instance_id
        )
    for plugin_id, instance_ids in sorted(devices_by_plugin.items()):
        policy = catalog.Component_Get(plugin_id).instance_policy
        if len(instance_ids) > policy.plugin_max:
            issues.append(
                ValidationIssue(
                    "error",
                    "device_instance_limit",
                    f"Device plugin {plugin_id} allows at most "
                    f"{policy.plugin_max} instance(s)",
                )
            )
        if len(instance_ids) > 1 and not policy.same_plugin_multiple:
            issues.append(
                ValidationIssue(
                    "error",
                    "device_same_plugin_multiple",
                    f"Device plugin {plugin_id} cannot be instantiated twice",
                )
            )
        if len(instance_ids) > 1 and not policy.multi_instance_ready:
            issues.append(
                ValidationIssue(
                    "error",
                    "device_multi_instance_not_ready",
                    f"Device plugin {plugin_id} has no context-safe multi-instance driver",
                )
            )
    for component_class, instance_ids in sorted(devices_by_class.items()):
        selected_class_manifests = tuple(
            catalog.Component_Get(instance.plugin)
            for instance in model.device_instances
            if catalog.Component_Get(instance.plugin).component_class == component_class
        )
        if selected_class_manifests and all(
            manifest.metadata.get("independent_class_member") is True
            for manifest in selected_class_manifests
        ):
            continue
        class_limit = max(
            (
                manifest.instance_policy.class_max
                for manifest in catalog.Type_Get("device")
                if manifest.component_class == component_class
            ),
            default=1,
        )
        if len(instance_ids) > class_limit:
            issues.append(
                ValidationIssue(
                    "error",
                    "device_class_instance_limit",
                    f"Device class {component_class} allows at most "
                    f"{class_limit} instance(s)",
                )
            )
    for component_id in model.base_components:
        try:
            component_type = catalog.Component_Get(component_id).component_type
        except ValueError as error:
            issues.append(ValidationIssue("error", "missing_component", str(error)))
            continue
        if component_type not in {"algorithm", "flight_logic"}:
            issues.append(
                ValidationIssue(
                    "error",
                    "component_type",
                    f"{component_id} cannot be a base flight component",
                )
            )
    for component_id in model.ProtocolComponentIds_Get():
        _ComponentType_Validate(catalog, component_id, "protocol", issues)
    _Strategies_Validate(model, catalog, issues)
    _Modes_Validate(model, catalog, issues)
    _ModeParameters_Validate(model, catalog, issues)
    try:
        AlgorithmParameters_Resolve(model, catalog)
    except ValueError as error:
        issues.append(ValidationIssue("error", "algorithm_parameters", str(error)))
    _ProtocolProfiles_Validate(model, catalog, issues)
    try:
        mcu_manifest = catalog.Component_Get(model.mcu)
        environment_manifest = catalog.Component_Get(model.development_environment)
        supported_environments = tuple(
            mcu_manifest.metadata.get("supported_environments", [])
        )
        if (
            supported_environments
            and model.development_environment not in supported_environments
        ):
            issues.append(
                ValidationIssue(
                    "error",
                    "environment_mcu",
                    "Selected development environment is not supported by the MCU plugin",
                )
            )
        if environment_manifest.environment is None:
            issues.append(
                ValidationIssue(
                    "error",
                    "environment_manifest",
                    "Development environment renderer metadata is missing",
                )
            )
    except ValueError as error:
        issues.append(ValidationIssue("error", "environment_catalog", str(error)))
    try:
        _Hardware_Validate(model, catalog, issues)
    except ValueError as error:
        issues.append(ValidationIssue("error", "hardware_catalog", str(error)))

    component_ids = model.ComponentIds_Get()
    for error in catalog.DependencyErrors_Get(component_ids):
        issues.append(ValidationIssue("error", "dependency", error))
    for path, owners in catalog.PathConflicts_Get(component_ids).items():
        issues.append(
            ValidationIssue(
                "error", "payload_conflict", f"{path} is owned by {', '.join(owners)}"
            )
        )
    try:
        resource_result = ResourceAssignments_Resolve(model, catalog)
    except ValueError as error:
        issues.append(ValidationIssue("error", "resource_catalog", str(error)))
    else:
        for error in resource_result.errors:
            issues.append(ValidationIssue("error", "resource", error))

    try:
        capability_result = CapabilityResolution_Resolve(model, catalog)
    except ValueError as error:
        issues.append(ValidationIssue("error", "capability_catalog", str(error)))
    else:
        for requirement in capability_result.missing:
            issues.append(
                ValidationIssue(
                    "error",
                    "capability_missing",
                    f"{requirement.consumer_component} requires "
                    f"{requirement.capability} ({requirement.purpose})",
                )
            )
        for choice in capability_result.choices:
            if choice.requires_selection:
                issues.append(
                    ValidationIssue(
                        "error",
                        "capability_ambiguous",
                        f"Capability {choice.capability} has multiple providers",
                    )
                )
        for capability in capability_result.invalid_overrides:
            issues.append(
                ValidationIssue(
                    "error",
                    "capability_source_override",
                    f"Invalid or unnecessary capability source override: "
                    f"{capability}",
                )
            )
        for conflict in capability_result.source_conflicts:
            issues.append(ValidationIssue("error", "capability_source_conflict", conflict))
    if model.protocols.get("logging") is not None:
        log_sink_providers = tuple(
            instance.instance_id
            for instance in model.device_instances
            if "service.log_sink"
            in catalog.Component_Get(instance.plugin).provides
        )
        if len(log_sink_providers) != 1:
            issues.append(
                ValidationIssue(
                    "error",
                    "log_sink_cardinality",
                    "Exactly one physical Log Sink Device is required / "
                    "必须且只能选择一个物理日志接收设备: "
                    + (", ".join(log_sink_providers) or "none"),
                )
            )
        if not model.logging_streams:
            issues.append(
                ValidationIssue(
                    "error", "logging", "No SSLOG stream policy is configured"
                )
            )
        try:
            definitions = ProtocolLogDefinitions_Get(model, catalog)
        except ValueError as error:
            definitions = ()
            issues.append(ValidationIssue("error", "logging_metadata", str(error)))
        expected_records = tuple(definition.record for definition in definitions)
        actual_records = tuple(stream.record for stream in model.logging_streams)
        if definitions and actual_records != expected_records:
            issues.append(
                ValidationIssue(
                    "error",
                    "logging_records",
                    "The SSLOG record table must match the selected protocol bundle order",
                )
            )
        streams = {stream.record: stream for stream in model.logging_streams}
        for definition in definitions:
            stream = streams.get(definition.record)
            if stream is None:
                continue
            if stream.policy != definition.default_stream.policy or (
                definition.default_stream.policy == "EVERY"
                and (stream.decimation != 1 or stream.period_us != 0)
            ):
                issues.append(ValidationIssue(
                    "error", "logging_cadence",
                    f"Stream must preserve protocol cadence: {definition.record}",
                ))
            availability = LogAvailability_Get(definition, model, catalog)
            if not availability.available and stream.enabled:
                issues.append(
                    ValidationIssue(
                        "error",
                        "logging_unavailable",
                        f"Unavailable SSLOG record is enabled: {definition.record}",
                    )
                )
            if (
                availability.available
                and definition.level == LogPolicyLevel.REQUIRED
                and not stream.enabled
            ):
                issues.append(
                    ValidationIssue(
                        "error",
                        "logging_required",
                        f"Required SSLOG record cannot be disabled: {definition.record}",
                    )
                )
    from silverstar_fccg.project.air_link import (
        AirLinkIssues_Get, GroundTargetIssues_Get,
    )

    issues.extend(
        ValidationIssue("error", issue.code, issue.message)
        for issue in (
            GroundTargetIssues_Get(model, catalog)
            if model.ground_target.enabled else AirLinkIssues_Get(model, catalog)
        )
    )
    return ProjectValidationResult(tuple(issues))


def Project_EditValidate(
    model: ProjectModel, catalog: PluginCatalog
) -> ProjectValidationResult:
    """Validate an in-memory editing state without requiring finished hardware.

    Structural corruption remains an error. Expected intermediate states are surfaced as
    warnings so the GUI can keep accepting configuration changes safely.
    """

    issues: list[ValidationIssue] = []
    try:
        ProjectModel_Parse(model.Dictionary_Get())
    except ProjectModelError as error:
        return ProjectValidationResult(
            (ValidationIssue("error", "project_model", str(error)),)
        )
    try:
        catalog = catalog.ProjectView_Get(model)
    except ValueError as error:
        return ProjectValidationResult(
            (ValidationIssue("error", "device_variant", str(error)),)
        )

    if model.hardware.mode == "unselected":
        issues.append(
            ValidationIssue(
                "warning",
                "hardware_unselected",
                "Hardware has not been selected",
            )
        )
    elif model.hardware.mode == "custom" and not model.hardware.snapshot_id:
        issues.append(
            ValidationIssue(
                "warning",
                "hardware_import_pending",
                "A STM32CubeMX project still needs to be imported",
            )
        )

    expected_target = ""
    if model.mcu:
        try:
            mcu_manifest = catalog.Component_Get(model.mcu)
        except ValueError:
            pass
        else:
            if mcu_manifest.platform is not None:
                expected_target = mcu_manifest.platform.build_target_profile
    if model.build.target_profile != expected_target:
        issues.append(
            ValidationIssue(
                "warning",
                "target_profile_pending",
                "Build Target Profile will be synchronized from the selected MCU Platform",
            )
        )

    for slot in catalog.SelectionSlots_Get(SelectionKind.STRATEGY.value):
        manifests = catalog.SelectionSlot_Get(slot)
        required = any(
            manifest.selection is not None and manifest.selection.required
            for manifest in manifests
        )
        if required and not model.strategies.get(slot):
            issues.append(
                ValidationIssue(
                    "warning",
                    "strategy_pending",
                    f"Strategy slot {slot} needs a compatible selection",
                )
            )

    try:
        capability_result = CapabilityResolution_Resolve(model, catalog)
    except ValueError as error:
        issues.append(ValidationIssue("error", "capability_catalog", str(error)))
    else:
        for requirement in capability_result.missing:
            issues.append(
                ValidationIssue(
                    "warning",
                    "capability_pending",
                    f"{requirement.consumer_component} needs {requirement.capability}",
                )
            )
        for choice in capability_result.choices:
            if choice.requires_selection:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "capability_source_pending",
                        f"Capability {choice.capability} needs a provider selection",
                    )
                )

    try:
        resources = ResourceAssignments_Resolve(model, catalog)
    except ValueError as error:
        issues.append(ValidationIssue("error", "resource_catalog", str(error)))
    else:
        issues.extend(
            ValidationIssue("warning", "resource_pending", error)
            for error in resources.errors
        )
    return ProjectValidationResult(tuple(issues))
