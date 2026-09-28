from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from silverstar_fccg.core.errors import FccgError

from silverstar_fccg.plugins.manifest import (
    PluginManifest,
    PluginManifestError,
    PluginManifest_Load,
)


class PluginCatalogError(FccgError):
    pass


class PluginCatalog:
    def __init__(self, builtin_root: Path, installed_root: Path) -> None:
        self.builtin_root = builtin_root.resolve()
        self.installed_root = installed_root.resolve()
        self._components: dict[str, PluginManifest] = {}

    def Scan(self) -> tuple[PluginManifest, ...]:
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
        if errors:
            raise PluginCatalogError("\n".join(errors))
        self._components = manifests
        return self.All_Get()

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
            payload_files = {
                path.relative_to(manifest.payload_root).as_posix()
                for path in manifest.PayloadFiles_Get()
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
                    directory = manifest.payload_root.joinpath(
                        *include_dir.split("/")
                    )
                    if not directory.is_dir() or directory.is_symlink():
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
                    directory = manifest.payload_root.joinpath(
                        *include_dir.split("/")
                    )
                    if not directory.is_dir() or directory.is_symlink():
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
