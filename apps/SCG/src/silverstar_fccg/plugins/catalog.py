from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.core.platform_tokens import PlatformToken_Get

from silverstar_fccg.plugins.manifest import (
    PluginManifest,
    PluginManifestError,
    PluginManifest_Load,
    PluginManifest_VariantResolve,
    ResourceMode,
)


class PluginCatalogError(FccgError):
    pass


class PluginCatalog:
    def __init__(self, builtin_root: Path, installed_root: Path) -> None:
        self.builtin_root = builtin_root.resolve()
        self.installed_root = installed_root.resolve()
        self._components: dict[str, PluginManifest] = {}
        self._project_variant_view = False
        self._instance_components: dict[str, PluginManifest] = {}
        self._project_views: dict[tuple, PluginCatalog] = {}

    def InstanceComponent_Get(self, instance) -> PluginManifest:
        return self._instance_components.get(
            instance.instance_id, self.Component_Get(instance.plugin)
        )

    def InstanceIdComponent_Get(self, instance_id: str) -> PluginManifest:
        try:
            return self._instance_components[instance_id]
        except KeyError as error:
            raise PluginCatalogError(f"Unknown device instance: {instance_id}") from error

    def ProjectView_Get(self, model) -> PluginCatalog:
        """Resolve selected Device variants without registering duplicate chip plugins."""
        if self._project_variant_view:
            return self
        # Immutable device selections and target identity completely determine
        # a variant view. Keep a small working set for old/new GUI transactions;
        # Scan invalidates it after any plugin install, removal or reload.
        variant_inputs = []
        for plugin_id in dict.fromkeys(item.plugin for item in model.device_instances):
            manifest = self.Component_Get(plugin_id)
            if manifest.device_variants:
                stamp = manifest.manifest_path.stat()
                variant_inputs.append((plugin_id, stamp.st_mtime_ns, stamp.st_size))
        key = (model.core, model.board, tuple(model.device_instances), tuple(variant_inputs))
        cached = self._project_views.get(key)
        if cached is not None:
            return cached
        view = PluginCatalog(self.builtin_root, self.installed_root)
        view._components = dict(self._components)
        view._project_variant_view = True
        selected: dict[str, list[PluginManifest]] = {}
        from silverstar_fccg.project.radio_variants import RadioManifest_Resolve
        for instance in model.device_instances:
            manifest = RadioManifest_Resolve(self.Component_Get(instance.plugin), instance)
            if not manifest.device_variants:
                if instance.interface or instance.profile:
                    raise PluginCatalogError(f"{instance.plugin} has no Device variants")
                view._instance_components[instance.instance_id] = manifest
                continue
            default_variant = next(iter(manifest.device_variants.values()))
            interface = instance.interface or default_variant["interface"]
            profile = instance.profile or default_variant["profile"]
            matches = [
                variant_id for variant_id, variant in manifest.device_variants.items()
                if variant["interface"] == interface
                and variant["profile"] == profile
            ]
            if len(matches) != 1:
                raise PluginCatalogError(
                    f"{instance.plugin} requires a valid interface and profile"
                )
            resolved = PluginManifest_VariantResolve(manifest, matches[0])
            view._instance_components[instance.instance_id] = resolved
            selected.setdefault(instance.plugin, []).append(resolved)
        for plugin_id, variants in selected.items():
            first = variants[0]
            if len(variants) == 1:
                view._components[plugin_id] = first
                continue
            build = replace(
                first.build,
                sources=tuple(dict.fromkeys(
                    source for variant in variants for source in variant.build.sources
                )),
                include_dirs=tuple(dict.fromkeys(
                    path for variant in variants for path in variant.build.include_dirs
                )),
                defines=tuple(dict.fromkeys(
                    value for variant in variants for value in variant.build.defines
                )),
            )
            view._components[plugin_id] = replace(
                first, build=build,
                payload_roots=tuple(dict.fromkeys(
                    path for variant in variants for path in variant.payload_roots
                )),
                provides=tuple(dict.fromkeys(
                    capability for variant in variants
                    for capability in variant.provides
                )),
            )
        target_role = self.Component_Get(model.core).metadata.get("target_role", "")
        if target_role:
            for plugin_id in model.DevicePluginIds_Get():
                manifest = view._components[plugin_id]
                modes = manifest.metadata.get("target_resource_modes", {}).get(target_role, {})
                if modes:
                    names = {item.name for item in manifest.resource_requirements}
                    if not set(modes).issubset(names):
                        raise PluginCatalogError("Unknown target-scoped resource requirement")
                    resolved = replace(manifest, resource_requirements=tuple(
                        replace(item, mode=ResourceMode(modes[item.name]))
                        if item.name in modes else item for item in manifest.resource_requirements
                    ))
                    view._components[plugin_id] = resolved
                    for instance in model.device_instances:
                        if instance.plugin == plugin_id:
                            per_instance = view._instance_components[instance.instance_id]
                            view._instance_components[instance.instance_id] = replace(per_instance,
                                resource_requirements=tuple(replace(item, mode=ResourceMode(modes[item.name]))
                                    if item.name in modes else item for item in per_instance.resource_requirements))
        if target_role == "ground_station" and model.board and model.device_instances:
            # A verified PCB's one telemetry footprint belongs to the first
            # configured radio, regardless of which instance owns uplink.
            board = view._components[model.board]
            first = model.device_instances[0].instance_id
            view._components[model.board] = replace(board, resource_roles=tuple(
                replace(role, key=first + ":" + role.key.removeprefix("telemetry:"))
                if role.key.startswith("telemetry:") else role for role in board.resource_roles
            ))
        if len(self._project_views) >= 8:
            self._project_views.pop(next(iter(self._project_views)))
        self._project_views[key] = view
        return view

    def Scan(self) -> tuple[PluginManifest, ...]:
        self._project_views.clear()
        manifests: dict[str, PluginManifest] = {}
        errors: list[str] = []
        for source, root in (("builtin", self.builtin_root), ("installed", self.installed_root)):
            if not root.exists():
                continue
            for path in sorted(root.rglob("plugin.json")):
                try:
                    manifest = PluginManifest_Load(path, source=source)
                except PluginManifestError as error:
                    errors.append(str(error))
                    continue
                previous = manifests.get(manifest.component_id)
                if previous is not None:
                    errors.append(
                        f"Duplicate component id {manifest.component_id}: "
                        f"{previous.manifest_path} and {manifest.manifest_path}"
                    )
                else:
                    manifests[manifest.component_id] = manifest
        errors.extend(self._ProtocolAssetsErrors_Get(manifests))
        errors.extend(self._PlatformAssetsErrors_Get(manifests))
        errors.extend(self._SharedParameterErrors_Get(manifests))
        errors.extend(self._PhysicalDeviceErrors_Get(manifests))
        if errors:
            raise PluginCatalogError("\n".join(errors))
        self._components = manifests
        return self.All_Get()

    @staticmethod
    def _PhysicalDeviceParts_Get(manifest, manifests) -> frozenset[str]:
        platforms = [manifests[item.component_id] for item in manifest.dependencies
            if not item.optional and item.component_id in manifests
            and manifests[item.component_id].component_type in {"mcu", "mcu_family"}]
        if len(platforms) != 1 or platforms[0].platform is None:
            return frozenset()
        rules = platforms[0].platform.match_rules
        if not rules or any(not rule.exact_part or
                any(token in rule.exact_part for token in "*?[]") for rule in rules):
            return frozenset()
        parts = frozenset(PlatformToken_Get(rule.exact_part) for rule in rules)
        return parts if all(parts) else frozenset()

    @staticmethod
    def _PhysicalDeviceErrors_Get(manifests) -> tuple[str, ...]:
        """Same hardware may have mutually exclusive platform implementations.

        A different component id, interface or family label is not proof of
        exclusivity. Duplicate physical facts require finite, disjoint exact
        parts from one mandatory platform dependency for every implementation.
        Broad/missing rules and overlapping target parts remain errors.
        """
        groups = defaultdict(list)
        for manifest in manifests.values():
            device = manifest.physical_device
            if manifest.component_type == "device" and device is not None:
                groups[(device.vendor, device.model, device.chipset)].append(manifest)
        errors = []
        for identity, implementations in groups.items():
            if len(implementations) == 1:
                continue
            owners = {}
            for manifest in implementations:
                parts = PluginCatalog._PhysicalDeviceParts_Get(manifest, manifests)
                if not parts:
                    errors.append(f"Physical device {identity}: {manifest.component_id} "
                                  "has no proven exact platform variant domain")
                for part in sorted(parts):
                    if part in owners:
                        errors.append(f"Duplicate physical device {identity} on {part}: "
                                      f"{owners[part]} and {manifest.component_id}")
                    owners[part] = manifest.component_id
        return tuple(errors)

    def PhysicalDeviceIdentityKeys_Get(self, manifest) -> tuple[tuple[str, ...], ...]:
        """Hardware facts plus implementation target, never invented chip names."""
        device = manifest.physical_device
        if device is None:
            raise PluginCatalogError("Physical device facts unavailable")
        physical = (device.vendor, device.model, device.chipset)
        parts = self._PhysicalDeviceParts_Get(manifest, self._components)
        return tuple((*physical, part) for part in sorted(parts or {"*"}))

    @staticmethod
    def _ProtocolAssetsErrors_Get(
        manifests: dict[str, PluginManifest],
    ) -> tuple[str, ...]:
        """Reject named-only protocol profiles with no complete implementation."""
        errors: list[str] = []
        profile_owners: dict[tuple[str, str], str] = {}
        for manifest in manifests.values():
            if manifest.protocol is None:
                continue
            dependency_ids: set[str] = {manifest.component_id}
            pending = [
                dependency.component_id
                for dependency in manifest.dependencies
                if not dependency.optional
            ]
            while pending:
                dependency_id = pending.pop()
                if dependency_id in dependency_ids:
                    continue
                dependency = manifests.get(dependency_id)
                if dependency is None:
                    errors.append(
                        f"Protocol bundle {manifest.component_id} requires missing "
                        f"component {dependency_id}"
                    )
                    continue
                dependency_ids.add(dependency_id)
                pending.extend(
                    requirement.component_id
                    for requirement in dependency.dependencies
                    if not requirement.optional
                )
            dependencies = tuple(
                manifests[component_id]
                for component_id in sorted(dependency_ids)
                if component_id in manifests
            )
            payload_files = {
                path.relative_to(dependency.payload_root).as_posix()
                for dependency in dependencies
                for path in dependency.PayloadFiles_Get()
            }
            for category, profiles in manifest.protocol.profiles.items():
                for profile in profiles:
                    identity = (category, profile.profile_id)
                    previous_owner = profile_owners.get(identity)
                    if previous_owner is not None:
                        errors.append(
                            "Duplicate Protocol Profile "
                            f"{category}/{profile.profile_id}: "
                            f"{previous_owner} and {manifest.component_id}"
                        )
                    else:
                        profile_owners[identity] = manifest.component_id
                    for field_name, paths in (
                        ("codec_sources", profile.codec_sources),
                        ("parser_sources", profile.parser_sources),
                        ("host_tests", profile.host_tests),
                        ("golden_tests", profile.golden_tests),
                        ("decoder_metadata", (profile.decoder_metadata,)),
                    ):
                        for relative in paths:
                            if relative not in payload_files:
                                errors.append(
                                    f"Protocol profile {category}/{profile.profile_id} "
                                    f"{field_name} asset is missing from its dependency "
                                    f"closure: {relative}"
                                )
                    for relative in profile.include_dirs:
                        if not any(
                            (dependency.payload_root / relative).is_dir()
                            and not (dependency.payload_root / relative).is_symlink()
                            for dependency in dependencies
                        ):
                            errors.append(
                                f"Protocol profile {category}/{profile.profile_id} "
                                f"include directory is missing from its dependency "
                                f"closure: {relative}"
                            )
                    for relative in profile.documentation:
                        if not any(
                            (dependency.package_root / relative).is_file()
                            and not (dependency.package_root / relative).is_symlink()
                            for dependency in dependencies
                        ):
                            errors.append(
                                f"Protocol profile {category}/{profile.profile_id} "
                                f"documentation is missing: {relative}"
                            )
        return tuple(errors)

    @staticmethod
    def _SharedParameterErrors_Get(manifests: dict[str, PluginManifest]) -> tuple[str, ...]:
        declarations: dict[str, tuple[object, ...]] = {}
        errors: list[str] = []
        for manifest in manifests.values():
            for parameter in manifest.algorithm_parameters:
                if not parameter.shared_key:
                    continue
                contract = (parameter.value_type, parameter.default, parameter.unit,
                            parameter.representation, parameter.minimum, parameter.maximum,
                            parameter.precision, parameter.step)
                previous = declarations.setdefault(parameter.shared_key, contract)
                if previous != contract:
                    errors.append(f"Incompatible shared parameter declaration: {parameter.shared_key}")
        return tuple(errors)

    @staticmethod
    def _PlatformAssetsErrors_Get(
        manifests: dict[str, PluginManifest],
    ) -> tuple[str, ...]:
        errors: list[str] = []
        for manifest in manifests.values():
            platform = manifest.platform
            if platform is None:
                continue
            payload_owners = [manifest]
            for dependency in manifest.dependencies:
                if dependency.optional:
                    continue
                owner = manifests.get(dependency.component_id)
                if owner is None:
                    errors.append(
                        f"Platform {manifest.component_id} needs missing payload "
                        f"component {dependency.component_id}"
                    )
                    continue
                payload_owners.append(owner)
            payload_files = {
                path.relative_to(owner.payload_root).as_posix()
                for owner in payload_owners
                for path in owner.PayloadFiles_Get()
            }
            if not any(
                path == platform.resource_header
                or path.endswith("/" + platform.resource_header)
                for path in payload_files
            ):
                errors.append(
                    f"Platform {manifest.component_id} resource header is missing: "
                    f"{platform.resource_header}"
                )
            for backend in platform.resource_backends.values():
                for source in backend.sources:
                    if source not in payload_files:
                        errors.append(
                            f"Platform {manifest.component_id} backend "
                            f"{backend.backend_id} source is missing: {source}"
                        )
                for include_dir in backend.include_dirs:
                    if not any(
                        (owner.payload_root / include_dir).is_dir()
                        and not (owner.payload_root / include_dir).is_symlink()
                        for owner in payload_owners
                    ):
                        errors.append(
                            f"Platform {manifest.component_id} backend "
                            f"{backend.backend_id} include directory is missing: "
                            f"{include_dir}"
                        )
            for provider in platform.module_providers.values():
                for source in (
                    *provider.provider_sources,
                    *provider.middleware_sources,
                ):
                    if source not in payload_files:
                        errors.append(
                            f"Platform {manifest.component_id} module provider "
                            f"{provider.provider_id} source is missing: {source}"
                        )
                for include_dir in provider.include_dirs:
                    if not any(
                        (owner.payload_root / include_dir).is_dir()
                        and not (owner.payload_root / include_dir).is_symlink()
                        for owner in payload_owners
                    ):
                        errors.append(
                            f"Platform {manifest.component_id} module provider "
                            f"{provider.provider_id} include directory is missing: "
                            f"{include_dir}"
                        )
        return tuple(errors)

    def All_Get(self) -> tuple[PluginManifest, ...]:
        return tuple(self._components[key] for key in sorted(self._components))

    def Component_Get(self, component_id: str) -> PluginManifest:
        try:
            return self._components[component_id]
        except KeyError as error:
            raise PluginCatalogError(f"Unknown component: {component_id}") from error

    def Type_Get(self, component_type: str) -> tuple[PluginManifest, ...]:
        return tuple(
            component for component in self.All_Get() if component.component_type == component_type
        )

    def SelectionSlot_Get(self, slot: str) -> tuple[PluginManifest, ...]:
        return tuple(
            component
            for component in self.All_Get()
            if component.selection is not None and component.selection.slot == slot
        )

    def SelectionSlots_Get(self, kind: str) -> tuple[str, ...]:
        slots = {
            component.selection.slot
            for component in self.All_Get()
            if component.selection is not None
            and component.selection.kind.value == kind
        }
        return tuple(
            sorted(
                slots,
                key=lambda slot: min(
                    component.selection.ui_order
                    for component in self.SelectionSlot_Get(slot)
                    if component.selection is not None
                ),
            )
        )

    def ReferenceProvenance_Get(self) -> dict:
        path = self.builtin_root / "reference_provenance.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PluginCatalogError(
                f"Invalid builtin reference provenance: {error}"
            ) from error
        if not isinstance(value, dict):
            raise PluginCatalogError("Builtin reference provenance must be an object")
        return value

    def DependencyErrors_Get(self, component_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        selected = set(component_ids)
        errors: list[str] = []
        for component_id in sorted(selected):
            manifest = self._components.get(component_id)
            if manifest is None:
                errors.append(f"Missing selected component: {component_id}")
                continue
            for requirement in manifest.dependencies:
                if not requirement.optional and requirement.component_id not in selected:
                    errors.append(
                        f"{component_id} requires component {requirement.component_id}"
                    )
            available_capabilities = {
                capability
                for selected_id in selected
                if selected_id in self._components
                for capability in self._components[selected_id].provides
            }
            for capability in manifest.capabilities_required:
                if capability not in available_capabilities:
                    errors.append(f"{component_id} requires capability {capability}")
        return tuple(errors)

    def PathConflicts_Get(self, component_ids: tuple[str, ...] | list[str]) -> dict[str, tuple[str, ...]]:
        owners: defaultdict[str, list[str]] = defaultdict(list)
        for component_id in component_ids:
            manifest = self.Component_Get(component_id)
            for path in manifest.PayloadFiles_Get():
                relative = path.relative_to(manifest.payload_root).as_posix()
                owners[relative].append(component_id)
        return {
            path: tuple(component_owners)
            for path, component_owners in sorted(owners.items())
            if len(component_owners) > 1
        }
