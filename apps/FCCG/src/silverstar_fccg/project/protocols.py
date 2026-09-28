from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import (
    PROTOCOL_PROFILE_SLOTS,
    ProtocolProfileContribution,
    TransportContribution,
)
from silverstar_fccg.project.model import (
    PROTOCOL_CATEGORIES,
    DeviceInstance,
    ProjectModel,
    ProtocolSelection,
)
from silverstar_fccg.project.resources import ResourceRequirementOptions_Get


PROTOCOL_SERVICES = {
    "telemetry": "telemetry_service",
    "maintenance": "maintenance_service",
    "logging": "flight_log_service",
}

PROTOCOL_BINDINGS = {
    "telemetry": "telemetry_transport",
    "maintenance": "maintenance_console",
    "logging": "flight_log_sink",
}


@dataclass(frozen=True, slots=True)
class ProtocolProfileSelection:
    category: str
    component_id: str
    profile: ProtocolProfileContribution


@dataclass(frozen=True, slots=True)
class ProtocolProfileAvailability:
    category: str
    component_id: str
    profile_id: str
    available: bool
    reason_code: str = ""


@dataclass(frozen=True, slots=True)
class ProtocolTransportProvider:
    component_id: str
    instance_id: str
    transport: TransportContribution


@dataclass(frozen=True, slots=True)
class ProtocolBinding:
    category: str
    service: str
    slot: str
    profile_id: str
    binding: str
    provider_component: str
    provider_instance: str
    transport_capability: str
    transport_selection: str = "single"
    candidate_instances: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtocolResolutionIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ProtocolResolution:
    selections: tuple[ProtocolProfileSelection, ...]
    bindings: tuple[ProtocolBinding, ...]
    issues: tuple[ProtocolResolutionIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def ProtocolProfileSelections_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ProtocolProfileSelection, ...]:
    selections: list[ProtocolProfileSelection] = []
    for category, selected in sorted(model.protocols.items()):
        if selected is None:
            continue
        contribution = catalog.Component_Get(selected.component).protocol
        if contribution is None:
            continue
        selections.extend(
            ProtocolProfileSelection(category, selected.component, profile)
            for profile in contribution.profiles.get(category, ())
            if profile.profile_id == selected.profile
        )
    return tuple(selections)


def ProtocolAutoManagedManifests_Get(
    catalog: PluginCatalog, category: str
):
    """Return internal Device manifests owned by one Protocol category."""
    return tuple(
        manifest
        for manifest in catalog.Type_Get("device")
        if manifest.metadata.get("auto_managed_protocol_category") == category
    )


def _DeviceInstanceId_Next(model: ProjectModel, preferred: str) -> str:
    selected = {instance.instance_id for instance in model.device_instances}
    if preferred not in selected:
        return preferred
    suffix = 1
    while f"{preferred}_{suffix}" in selected:
        suffix += 1
    return f"{preferred}_{suffix}"


def ProtocolAutoManagedDevices_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[str, ...]:
    """Synchronize declarative internal endpoints with nullable Protocol slots.

    Only Devices explicitly declaring ``auto_managed_protocol_category`` are
    touched.  A normal physical Device can therefore never be removed by this
    coordinator merely because it happens to provide a compatible transport.
    """
    changed: list[str] = []
    for category in PROTOCOL_CATEGORIES:
        manifests = ProtocolAutoManagedManifests_Get(catalog, category)
        plugins = {manifest.component_id for manifest in manifests}
        if model.protocols.get(category) is None:
            removed_ids = {
                instance.instance_id
                for instance in model.device_instances
                if instance.plugin in plugins
            }
            if not removed_ids:
                continue
            model.device_instances = [
                instance
                for instance in model.device_instances
                if instance.instance_id not in removed_ids
            ]
            model.resource_assignments = {
                key: value
                for key, value in model.resource_assignments.items()
                if key.partition(":")[0] not in removed_ids
            }
            model.capability_source_overrides = {
                capability: instance_id
                for capability, instance_id in (
                    model.capability_source_overrides.items()
                )
                if instance_id not in removed_ids
            }
            changed.extend(sorted(removed_ids))
            continue
        selected_plugins = set(model.DevicePluginIds_Get())
        for manifest in manifests:
            if manifest.component_id in selected_plugins:
                continue
            preferred = str(
                manifest.metadata.get(
                    "default_instance_id", manifest.component_class or "device0"
                )
            )
            instance_id = _DeviceInstanceId_Next(model, preferred)
            model.device_instances.append(
                DeviceInstance(instance_id, manifest.component_id)
            )
            selected_plugins.add(manifest.component_id)
            changed.append(instance_id)
    return tuple(changed)


def ProtocolTransportProviders_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[ProtocolTransportProvider, ...]:
    providers: list[ProtocolTransportProvider] = []
    for instance in model.device_instances:
        manifest = catalog.Component_Get(instance.plugin)
        providers.extend(
            ProtocolTransportProvider(
                component_id=manifest.component_id,
                instance_id=instance.instance_id,
                transport=transport,
            )
            for transport in manifest.transports
        )
    if model.hardware.mode == "board_plugin" and model.board:
        board = catalog.Component_Get(model.board)
        providers.extend(
            ProtocolTransportProvider(
                component_id=board.component_id,
                instance_id=board.component_id,
                transport=transport,
            )
            for transport in board.transports
        )
    return tuple(providers)


def _TransportCompatible_Is(requirement, provider: TransportContribution) -> bool:
    return (
        provider.capability == requirement.capability
        and provider.kind == requirement.kind
        and provider.mode == requirement.mode
        and provider.mtu >= requirement.minimum_mtu
        and (not requirement.ordered or provider.ordered)
        and (not requirement.bidirectional or provider.bidirectional)
        and (not requirement.reliable or provider.reliable)
    )


def _ProviderHardwareAvailable_Is(
    model: ProjectModel,
    catalog: PluginCatalog,
    provider: ProtocolTransportProvider,
) -> bool:
    """Check that a Device transport has candidates for required resources."""
    if model.hardware.mode == "custom" and not model.hardware.snapshot_id:
        # An unprepared custom-hardware draft has no inventory yet.  Its
        # transport is selected, but physical availability is still unknown;
        # keep an explicit/default Protocol choice until the import supplies
        # facts that can prove incompatibility.
        return True
    if provider.instance_id == provider.component_id:
        return True
    prefix = f"{provider.instance_id}:"
    options = tuple(
        option
        for option in ResourceRequirementOptions_Get(model, catalog)
        if option.key.startswith(prefix) and option.required
    )
    return all(option.candidates for option in options)


def ProtocolProfileAvailabilities_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> dict[tuple[str, str, str], ProtocolProfileAvailability]:
    """Resolve UI availability from manifest transport contracts only."""
    result: dict[tuple[str, str, str], ProtocolProfileAvailability] = {}
    for manifest in catalog.Type_Get("protocol"):
        contribution = manifest.protocol
        if contribution is None:
            continue
        category = contribution.category
        for profile in contribution.profiles.get(category, ()):
            candidate = deepcopy(model)
            candidate.protocols[category] = ProtocolSelection(
                component=manifest.component_id,
                version=manifest.version,
                profile=profile.profile_id,
                manifest_sha256=manifest.ManifestSha256_Get(),
            )
            ProtocolAutoManagedDevices_Reconcile(candidate, catalog)
            providers = ProtocolTransportProviders_Get(candidate, catalog)
            requirement = profile.transport
            compatible = (
                ()
                if requirement is None
                else tuple(
                    provider
                    for provider in providers
                    if _TransportCompatible_Is(requirement, provider.transport)
                )
            )
            reason_code = ""
            if requirement is None or not compatible:
                reason_code = "protocol.unavailable.transport_missing"
            elif profile.transport_selection == "single" and len(compatible) > 1:
                reason_code = "protocol.unavailable.transport_ambiguous"
            elif not any(
                _ProviderHardwareAvailable_Is(candidate, catalog, provider)
                for provider in compatible
            ):
                reason_code = "protocol.unavailable.hardware"
            availability = ProtocolProfileAvailability(
                category=category,
                component_id=manifest.component_id,
                profile_id=profile.profile_id,
                available=not reason_code,
                reason_code=reason_code,
            )
            result[(category, manifest.component_id, profile.profile_id)] = (
                availability
            )
    return result


def ProtocolResolution_Resolve(
    model: ProjectModel, catalog: PluginCatalog
) -> ProtocolResolution:
    selections = ProtocolProfileSelections_Get(model, catalog)
    providers = ProtocolTransportProviders_Get(model, catalog)
    issues: list[ProtocolResolutionIssue] = []
    bindings: list[ProtocolBinding] = []

    selected_by_category: dict[str, list[ProtocolProfileSelection]] = {}
    for selection in selections:
        selected_by_category.setdefault(selection.category, []).append(selection)

    declared_categories = {
        protocol.category
        for selection in model.protocols.values()
        if selection is not None
        for protocol in (catalog.Component_Get(selection.component).protocol,)
        if protocol is not None and protocol.category
    }
    selected_categories = {
        category
        for category, selection in model.protocols.items()
        if selection is not None
    }
    if set(model.protocols) != set(PROTOCOL_CATEGORIES):
        issues.append(
            ProtocolResolutionIssue(
                "protocol_profile_categories",
                "Protocol slots must contain telemetry, maintenance and logging",
            )
        )
    if selected_categories != declared_categories:
        issues.append(
            ProtocolResolutionIssue(
                "protocol_profile_categories",
                "Protocol profile categories do not match the selected bundles",
            )
        )

    for category, selected in sorted(model.protocols.items()):
        if selected is None:
            continue
        profile_id = selected.profile
        matches = selected_by_category.get(category, [])
        if len(matches) != 1:
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_profile",
                    f"Protocol profile {category}/{profile_id} resolves to "
                    f"{len(matches)} complete implementations",
                )
            )
            continue
        selection = matches[0]
        profile = selection.profile
        if (
            profile.service != PROTOCOL_SERVICES.get(category)
            or profile.slot != PROTOCOL_PROFILE_SLOTS.get(category)
            or profile.binding != PROTOCOL_BINDINGS.get(category)
        ):
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_layers",
                    f"Protocol profile {category}/{profile.profile_id} has an "
                    "invalid Service, Slot, or Transport Binding declaration",
                )
            )
            continue
        requirement = profile.transport
        if requirement is None:
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_transport",
                    f"Protocol profile {category}/{profile.profile_id} has no "
                    "transport constraint",
                )
            )
            continue
        compatible = tuple(
            provider
            for provider in providers
            if _TransportCompatible_Is(requirement, provider.transport)
        )
        if not compatible:
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_transport",
                    f"Protocol profile {category}/{profile.profile_id} requires "
                    f"{requirement.capability} ({requirement.kind}, "
                    f"{requirement.mode}, MTU >= {requirement.minimum_mtu})",
                )
            )
            continue
        if profile.transport_selection == "single" and len(compatible) > 1:
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_transport_ambiguous",
                    f"Protocol profile {category}/{profile.profile_id} has "
                    f"multiple compatible physical transports: "
                    + ", ".join(provider.instance_id for provider in compatible),
                )
            )
            continue
        available = tuple(
            provider
            for provider in compatible
            if _ProviderHardwareAvailable_Is(model, catalog, provider)
        )
        if not available:
            issues.append(
                ProtocolResolutionIssue(
                    "protocol_transport_hardware",
                    f"Protocol profile {category}/{profile.profile_id} has no "
                    "hardware-available transport",
                )
            )
            continue
        provider = available[0]
        bindings.append(
            ProtocolBinding(
                category=category,
                service=profile.service,
                slot=profile.slot,
                profile_id=profile.profile_id,
                binding=profile.binding,
                provider_component=provider.component_id,
                provider_instance=provider.instance_id,
                transport_capability=provider.transport.capability,
                transport_selection=profile.transport_selection,
                candidate_instances=tuple(
                    candidate.instance_id for candidate in available
                ),
            )
        )
    return ProtocolResolution(
        selections=selections,
        bindings=tuple(bindings),
        issues=tuple(issues),
    )
