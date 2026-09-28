from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import DeviceInstance, ProjectModel


@dataclass(frozen=True, slots=True)
class CapabilityUse:
    consumer_component: str
    capability: str
    purpose: str


class CapabilityKind(StrEnum):
    RAW_DATA = "raw_data"
    QUALIFIED = "qualified"


def CapabilityKind_Get(capability: str) -> CapabilityKind:
    return (
        CapabilityKind.QUALIFIED
        if capability.endswith("_qualified")
        else CapabilityKind.RAW_DATA
    )


@dataclass(frozen=True, slots=True)
class CapabilityProvider:
    instance_id: str
    plugin: str


@dataclass(frozen=True, slots=True)
class CapabilityRoute:
    requirement: CapabilityUse
    provider: CapabilityProvider
    automatic: bool


@dataclass(frozen=True, slots=True)
class CapabilityChoice:
    capability: str
    providers: tuple[CapabilityProvider, ...]
    selected_instance_id: str = ""

    @property
    def requires_selection(self) -> bool:
        return not self.selected_instance_id


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    requirements: tuple[CapabilityUse, ...]
    routes: tuple[CapabilityRoute, ...]
    choices: tuple[CapabilityChoice, ...]
    missing: tuple[CapabilityUse, ...]
    invalid_overrides: tuple[str, ...]
    unused_by_instance: dict[str, tuple[str, ...]]
    required_by_instance: dict[str, tuple[str, ...]] = field(default_factory=dict)
    enabled_by_instance: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source_conflicts: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return (
            not self.missing
            and not self.invalid_overrides
            and not self.source_conflicts
            and not any(choice.requires_selection for choice in self.choices)
        )

    def ConsumedCapabilitiesForInstance_Get(
        self, instance_id: str
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                route.requirement.capability
                for route in self.routes
                if route.provider.instance_id == instance_id
            )
        )

    def EnabledCapabilitiesForInstance_Get(
        self, instance_id: str
    ) -> tuple[str, ...]:
        return self.enabled_by_instance.get(instance_id, ())


def Capability_UserSelectable_Is(capability: str) -> bool:
    return not capability.startswith(
        ("device.", "transport.", "maintenance.", "service.")
    )


def _Requirements_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> tuple[CapabilityUse, ...]:
    device_plugins = set(model.DevicePluginIds_Get())
    non_device_manifests = [
        catalog.Component_Get(component_id)
        for component_id in dict.fromkeys(model.ComponentIds_Get())
        if component_id not in device_plugins
    ]
    component_capabilities = {
        capability
        for manifest in non_device_manifests
        for capability in manifest.provides
    }
    requirements: list[CapabilityUse] = []
    for manifest in non_device_manifests:
        requirements.extend(
            CapabilityUse(
                consumer_component=manifest.component_id,
                capability=requirement.capability,
                purpose=requirement.purpose,
            )
            for requirement in manifest.capability_requirements
            if requirement.capability not in component_capabilities
        )
        selection = manifest.selection
        if selection is None or selection.kind.value != "mode":
            continue
        for option in model.modes.get(selection.slot, []):
            option_requirements = selection.option_requirements.get(option)
            if option_requirements is None:
                continue
            requirements.extend(
                CapabilityUse(
                    consumer_component=manifest.component_id,
                    capability=requirement.capability,
                    purpose=requirement.purpose,
                )
                for requirement in option_requirements.capabilities
                if requirement.capability not in component_capabilities
            )
    return tuple(requirements)


def _Providers_Get(
    instances: list[DeviceInstance], catalog: PluginCatalog
) -> dict[str, tuple[CapabilityProvider, ...]]:
    values: dict[str, list[CapabilityProvider]] = {}
    for instance in instances:
        manifest = catalog.Component_Get(instance.plugin)
        provider = CapabilityProvider(instance.instance_id, instance.plugin)
        for capability in manifest.provides:
            values.setdefault(capability, []).append(provider)
    return {
        capability: tuple(providers)
        for capability, providers in values.items()
    }


def CapabilityResolution_Resolve(
    model: ProjectModel, catalog: PluginCatalog
) -> CapabilityResolution:
    requirements = _Requirements_Get(model, catalog)
    providers_by_capability = _Providers_Get(model.device_instances, catalog)
    requirements_by_capability: dict[str, list[CapabilityUse]] = {}
    for requirement in requirements:
        requirements_by_capability.setdefault(requirement.capability, []).append(
            requirement
        )

    routes: list[CapabilityRoute] = []
    choices: list[CapabilityChoice] = []
    missing: list[CapabilityUse] = []
    invalid_overrides: list[str] = []
    for capability, capability_requirements in requirements_by_capability.items():
        providers = providers_by_capability.get(capability, ())
        override = model.capability_source_overrides.get(capability, "")
        selected: CapabilityProvider | None = None
        automatic = False
        if not providers:
            missing.extend(capability_requirements)
            if override:
                invalid_overrides.append(capability)
            continue
        if len(providers) == 1:
            selected = providers[0]
            automatic = True
            if override:
                invalid_overrides.append(capability)
        else:
            if override:
                selected = next(
                    (
                        provider
                        for provider in providers
                        if provider.instance_id == override
                    ),
                    None,
                )
                if selected is None:
                    invalid_overrides.append(capability)
            else:
                selected = providers[0]
                automatic = True
            choices.append(
                CapabilityChoice(
                    capability,
                    providers,
                    selected.instance_id if selected is not None else "",
                )
            )
        if selected is not None:
            routes.extend(
                CapabilityRoute(requirement, selected, automatic)
                for requirement in capability_requirements
            )

    for capability in model.capability_source_overrides:
        if capability not in requirements_by_capability:
            invalid_overrides.append(capability)

    required_by_instance: dict[str, tuple[str, ...]] = {}
    enabled_by_instance: dict[str, tuple[str, ...]] = {}
    unused_by_instance: dict[str, tuple[str, ...]] = {}
    for instance in model.device_instances:
        provided = catalog.Component_Get(instance.plugin).provides
        required = tuple(
            capability
            for capability in provided
            if any(
                route.provider.instance_id == instance.instance_id
                and route.requirement.capability == capability
                for route in routes
            )
        )
        required_values = set(required)
        enabled = tuple(
            capability
            for capability in provided
            if not Capability_UserSelectable_Is(capability)
            or capability in required_values
        )
        required_by_instance[instance.instance_id] = required
        enabled_by_instance[instance.instance_id] = enabled
        unused_by_instance[instance.instance_id] = tuple(
            capability
            for capability in provided
            if Capability_UserSelectable_Is(capability)
            and capability not in enabled
        )
    source_conflicts = _SourceConflicts_Get(model, catalog, routes)
    return CapabilityResolution(
        requirements=requirements,
        routes=tuple(routes),
        choices=tuple(choices),
        missing=tuple(missing),
        invalid_overrides=tuple(dict.fromkeys(invalid_overrides)),
        unused_by_instance=unused_by_instance,
        required_by_instance=required_by_instance,
        enabled_by_instance=enabled_by_instance,
        source_conflicts=source_conflicts,
    )


def _SourceConflicts_Get(
    model: ProjectModel, catalog: PluginCatalog, routes: list[CapabilityRoute]
) -> tuple[str, ...]:
    """A declared qualification must describe the selected physical data source."""
    selected = {route.requirement.capability: route.provider.instance_id for route in routes}
    conflicts: list[str] = []
    for component in dict.fromkeys(model.ComponentIds_Get()):
        manifest = catalog.Component_Get(component)
        groups = manifest.metadata.get("capability_source_groups", [])
        if not isinstance(groups, list):
            raise ValueError(f"{component}: capability_source_groups must be a list")
        for group in groups:
            if not isinstance(group, list) or len(group) < 2 or any(
                not isinstance(value, str) or not value for value in group
            ):
                raise ValueError(f"{component}: invalid capability source group")
            active = {capability: selected[capability] for capability in group if capability in selected}
            if len(set(active.values())) > 1:
                conflicts.append(
                    "Capabilities require one physical source / 数据与资格必须来自同一物理源: "
                    + ", ".join(f"{capability}={instance}" for capability, instance in active.items())
                )
    return tuple(dict.fromkeys(conflicts))


def CapabilitySourceOverrides_Reconcile(
    model: ProjectModel, catalog: PluginCatalog
) -> CapabilityResolution:
    requirements = _Requirements_Get(model, catalog)
    providers = _Providers_Get(model.device_instances, catalog)
    ambiguous_capabilities = {
        requirement.capability
        for requirement in requirements
        if len(providers.get(requirement.capability, ())) > 1
    }
    model.capability_source_overrides = {
        capability: instance_id
        for capability, instance_id in model.capability_source_overrides.items()
        if capability in ambiguous_capabilities
        and any(
            provider.instance_id == instance_id
            for provider in providers.get(capability, ())
        )
        and instance_id != providers[capability][0].instance_id
    }
    return CapabilityResolution_Resolve(model, catalog)
