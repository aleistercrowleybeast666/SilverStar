from __future__ import annotations

import json
import shutil
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.plugins.catalog import PluginCatalog, PluginCatalogError
from silverstar_fccg.plugins.manifest import PluginManifest, PluginManifest_Parse


class PluginInstallError(FccgError):
    pass


class PluginInstaller:
    MAX_ENTRY_COUNT = 10_000
    MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024

    def __init__(
        self,
        workspace_policy: WorkspacePolicy,
        installed_root: Path,
        catalog: PluginCatalog,
    ) -> None:
        self.policy = workspace_policy
        self.installed_root = self.policy.Path_Resolve(installed_root)
        self.catalog = catalog

    def Install(
        self,
        archive_path: Path,
        progress_callback: Callable[[int, int, str, bool], None] | None = None,
    ) -> PluginManifest:
        phases = ("validate", "copy", "register", "refresh_catalog")

        def progress(current: int, done: bool) -> None:
            if progress_callback is not None:
                progress_callback(current, len(phases), phases[current - 1], done)

        progress(1, False)
        if archive_path.suffix.lower() != ".ssplugin":
            raise PluginInstallError("Plugin archive must use the .ssplugin extension")
        if not archive_path.is_file():
            raise PluginInstallError(f"Plugin archive does not exist: {archive_path}")
        staging = self.policy.StagingDirectory_Create("plugin-")
        destination: Path | None = None
        installed = False
        try:
            manifest_data = self._Archive_Extract(archive_path, staging)
            staged_manifest_path = staging / "plugin.json"
            manifest = PluginManifest_Parse(
                manifest_data, staged_manifest_path, source="installed"
            )
            existing_ids = {component.component_id for component in self.catalog.All_Get()}
            if manifest.component_id in existing_ids:
                raise PluginInstallError(
                    f"Component id is already installed: {manifest.component_id}"
                )
            for requirement in manifest.dependencies:
                if not requirement.optional and requirement.component_id not in existing_ids:
                    raise PluginInstallError(
                        f"Missing plugin dependency: {requirement.component_id}"
                    )
            available_capabilities = {
                capability
                for component in self.catalog.All_Get()
                for capability in component.provides
            } | set(manifest.provides)
            missing_capabilities = set(manifest.capabilities_required) - available_capabilities
            if missing_capabilities:
                raise PluginInstallError(
                    "Missing plugin capabilities: "
                    + ", ".join(sorted(missing_capabilities))
                )
            new_files = {
                path.relative_to(manifest.payload_root).as_posix()
                for path in manifest.PayloadFiles_Get()
            }
            reserved_conflicts = sorted(
                path for path in new_files if self._ManagedPath_IsReserved(path)
            )
            if reserved_conflicts:
                raise PluginInstallError(
                    "Plugin payload occupies FCCG-managed paths: "
                    + ", ".join(reserved_conflicts[:8])
                )
            for component in self.catalog.All_Get():
                existing_files = {
                    path.relative_to(component.payload_root).as_posix()
                    for path in component.PayloadFiles_Get()
                }
                conflicts = sorted(new_files & existing_files)
                if conflicts:
                    raise PluginInstallError(
                        f"Plugin payload conflicts with {component.component_id}: "
                        + ", ".join(conflicts[:8])
                    )
            destination = self.policy.Path_Resolve(
                self.installed_root / manifest.component_id / manifest.version,
                allow_root=False,
            )
            if destination.exists():
                raise PluginInstallError(f"Plugin destination already exists: {destination}")
            progress(1, True)

            progress(2, False)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.policy.Path_Replace(staging, destination)
            installed = True
            progress(2, True)

            progress(3, False)
            installed_manifest = PluginManifest_Parse(
                manifest_data, destination / "plugin.json", source="installed"
            )
            progress(3, True)

            progress(4, False)
            self.catalog.Scan()
            progress(4, True)
            return installed_manifest
        except Exception:
            if staging.exists():
                self.policy.Tree_Remove(staging)
            if installed and destination is not None and destination.exists():
                self.policy.Tree_Remove(destination)
                self.catalog.Scan()
            raise

    @staticmethod
    def _ManagedPath_IsReserved(relative: str) -> bool:
        parts = PurePosixPath(relative).parts
        if not parts:
            return True
        if parts[0] in {"Generated", ".fccg", ".vscode", ".eide"}:
            return True
        if relative in {
            "Makefile",
            "README.md",
            "SilverStar.ssproject",
            "SilverStar_Configuration.md",
        }:
            return True
        return len(parts) >= 3 and parts[0] == "Targets" and parts[-1] == "target.mk"

    def Remove(
        self,
        component_id: str,
        progress_callback: Callable[[int, int, str, bool], None] | None = None,
    ) -> PluginManifest:
        phases = ("validate", "delete", "unregister", "refresh_catalog")

        def progress(current: int, done: bool) -> None:
            if progress_callback is not None:
                progress_callback(current, len(phases), phases[current - 1], done)

        progress(1, False)
        try:
            manifest = self.catalog.Component_Get(component_id)
        except PluginCatalogError as error:
            raise PluginInstallError(f"Unknown component: {component_id}") from error
        if manifest.source != "installed":
            raise PluginInstallError(
                f"Builtin component cannot be removed: {component_id}"
            )

        remaining = tuple(
            component
            for component in self.catalog.All_Get()
            if component.component_id != component_id
        )
        dependency_users = sorted(
            component.component_id
            for component in remaining
            if any(
                requirement.component_id == component_id and not requirement.optional
                for requirement in component.dependencies
            )
        )
        if dependency_users:
            raise PluginInstallError(
                f"Plugin is required by: {', '.join(dependency_users)}"
            )

        remaining_capabilities = {
            capability for component in remaining for capability in component.provides
        }
        capability_users = sorted(
            component.component_id
            for component in remaining
            if set(component.capabilities_required) - remaining_capabilities
        )
        if capability_users:
            raise PluginInstallError(
                "Removing the plugin would break capabilities required by: "
                + ", ".join(capability_users)
            )

        package_root = self.policy.Path_Resolve(
            manifest.package_root, allow_root=False
        )
        component_root = self.policy.Path_Resolve(
            package_root.parent, allow_root=False
        )
        try:
            relative = component_root.relative_to(self.installed_root)
        except ValueError as error:
            raise PluginInstallError(
                f"Installed plugin path escaped the plugin store: {component_root}"
            ) from error
        if relative.parts != (component_id,):
            raise PluginInstallError(
                f"Unexpected installed plugin layout: {component_root}"
            )
        progress(1, True)

        staging = self.policy.StagingDirectory_Create("plugin-remove-")
        removed = staging / "plugin"
        moved = False
        try:
            progress(2, False)
            self.policy.Path_Replace(component_root, removed)
            moved = True
            progress(2, True)

            progress(3, False)
            progress(3, True)

            progress(4, False)
            self.catalog.Scan()
            progress(4, True)
            self.policy.Tree_Remove(staging)
            return manifest
        except Exception:
            if moved and removed.exists():
                component_root.parent.mkdir(parents=True, exist_ok=True)
                self.policy.Path_Replace(removed, component_root)
                self.catalog.Scan()
            if staging.exists():
                self.policy.Tree_Remove(staging)
            raise

    def _Archive_Extract(self, archive_path: Path, staging: Path) -> dict:
        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except (OSError, zipfile.BadZipFile) as error:
            raise PluginInstallError(f"Invalid plugin ZIP: {error}") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > self.MAX_ENTRY_COUNT:
                raise PluginInstallError("Plugin archive contains too many entries")
            total_size = sum(info.file_size for info in infos)
            if total_size > self.MAX_TOTAL_UNCOMPRESSED:
                raise PluginInstallError("Plugin archive is too large when extracted")
            names: set[str] = set()
            for info in infos:
                normalized = info.filename.rstrip("/")
                if not normalized:
                    continue
                try:
                    relative = self.policy.RelativePath_Validate(normalized)
                except WorkspacePolicyError as error:
                    raise PluginInstallError(
                        f"Unsafe plugin archive path: {info.filename}"
                    ) from error
                portable_name = relative.as_posix()
                if portable_name.casefold() in names:
                    raise PluginInstallError(
                        f"Duplicate case-insensitive archive path: {portable_name}"
                    )
                names.add(portable_name.casefold())
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise PluginInstallError(f"Plugin archive symlink rejected: {portable_name}")
                file_type = stat.S_IFMT(unix_mode)
                if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
                    raise PluginInstallError(
                        f"Plugin archive special file rejected: {portable_name}"
                    )
                destination = (staging / Path(*relative.parts)).resolve(strict=False)
                try:
                    destination.relative_to(staging.resolve())
                except ValueError as error:
                    raise PluginInstallError(
                        f"Plugin archive path escaped staging: {portable_name}"
                    ) from error
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
            manifest_path = staging / "plugin.json"
            if not manifest_path.is_file():
                raise PluginInstallError("plugin.json is missing from archive root")
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise PluginInstallError(f"plugin.json is invalid: {error}") from error
            if not (staging / "payload").is_dir():
                raise PluginInstallError("payload/ is missing from plugin archive")
            return manifest_data
