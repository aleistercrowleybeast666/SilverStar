from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.generator.render import (
    ComponentProvenance_Get,
    GeneratedFiles_Render,
    MetadataFiles_Render,
)
from silverstar_fccg.generator.eide_ownership import (
    EideOwnershipError,
    EideOwnedFields_Compare,
    EideOwnedFields_Merge,
    EideOwnedFields_Normalize,
    EideOwnedFingerprint_Get,
)
from silverstar_fccg.generator.hardware_preparation import (
    HardwareResourceBindingFingerprint_Get,
)
from silverstar_fccg.project.generation_state import (
    ProjectGenerationFingerprint_Get,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.project.validation import ProjectValidationResult, Project_Validate


class ProjectAssemblerError(FccgError):
    pass


@dataclass(frozen=True, slots=True)
class PlanOperation:
    operation: str
    target: str
    detail: str
    ownership: str
    dangerous: bool = False


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    project_root: Path
    operations: tuple[PlanOperation, ...]
    validation: ProjectValidationResult
    new_project: bool

    @property
    def valid(self) -> bool:
        return self.validation.valid and not any(
            operation.operation == "CONFLICT" for operation in self.operations
        )

    @property
    def dangerous(self) -> bool:
        return any(operation.dangerous for operation in self.operations)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    project_root: Path
    files_added: int
    files_modified: int
    component_files_preserved: int
    hardware_replaced: bool = False


GenerationProgressCallback = Callable[[int, int, str, bool], None]


class ProjectAssembler:
    HARDWARE_ROOT = "HardwareGenerated/STM32CubeMX"

    def __init__(
        self,
        workspace_policy: WorkspacePolicy,
        catalog: PluginCatalog,
        output_policy: WorkspacePolicy | None = None,
    ) -> None:
        self.internal_policy = workspace_policy
        self.policy = output_policy or workspace_policy
        self.catalog = catalog

    def Plan(self, model: ProjectModel, project_root: Path) -> GenerationPlan:
        destination = self.policy.Path_Resolve(project_root, allow_root=True)
        if destination.exists() and not destination.is_dir():
            raise ProjectAssemblerError(
                f"Project destination is not a directory: {destination}"
            )
        new_project = not destination.exists() or not any(destination.iterdir())
        if not new_project and not (destination / "SilverStar.ssproject").is_file():
            raise ProjectAssemblerError(
                "Existing destination is not an FCCG project (SilverStar.ssproject missing)"
            )
        validation = Project_Validate(model, self.catalog)
        if not validation.valid:
            return GenerationPlan(destination, (), validation, new_project)

        hardware_files = self._HardwareFiles_Get(model)
        desired, _ownership = self._DesiredFiles_Get(
            model, destination, hardware_files
        )
        managed_paths = set(desired)
        previous = self._Ownership_Load(destination) if not new_project else {}
        previous_components = previous.get("components", {})
        previous_active = set(previous.get("active_components", []))
        selected_components = set(model.ComponentIds_Get())
        operations: list[PlanOperation] = []

        for relative in self._StaleManagedPaths_Get(previous, managed_paths):
            target = self.policy.Path_Resolve(
                destination.joinpath(*relative.split("/")), allow_root=False
            )
            if target.is_file():
                operations.append(
                    PlanOperation(
                        "REMOVE",
                        relative,
                        "stale FCCG-managed output",
                        "generated",
                    )
                )
            elif target.exists():
                operations.append(
                    PlanOperation(
                        "CONFLICT",
                        relative,
                        "stale managed path is not a file",
                        "generated",
                    )
                )

        for component_id in model.ComponentIds_Get():
            manifest = self.catalog.Component_Get(component_id)
            was_installed = component_id in previous_components
            previous_component = previous_components.get(component_id, {})
            previous_files = (
                previous_component.get("files", {})
                if isinstance(previous_component, dict)
                else {}
            )
            for source in manifest.PayloadFiles_Get():
                relative = source.relative_to(manifest.payload_root).as_posix()
                target = destination.joinpath(*relative.split("/"))
                if self._ManagedPath_Is(relative, managed_paths):
                    operations.append(
                        PlanOperation(
                            "CONFLICT",
                            relative,
                            f"component {component_id} occupies an FCCG-managed path",
                            "component",
                        )
                    )
                elif new_project:
                    operations.append(
                        PlanOperation("ADD", relative, component_id, "component")
                    )
                elif was_installed:
                    newly_owned = relative not in previous_files
                    operations.append(
                        PlanOperation(
                            (
                                "ADD"
                                if newly_owned and not target.exists()
                                else "CONFLICT"
                                if newly_owned
                                else "PRESERVE"
                                if target.is_file()
                                else "CONFLICT"
                            ),
                            relative,
                            (
                                "new payload file added by the component update"
                                if newly_owned and not target.exists()
                                else "new component payload file collides with an existing path"
                                if newly_owned
                                else "project-owned source"
                                if target.is_file()
                                else "project-owned component file is missing; Apply will not restore it"
                            ),
                            "component",
                        )
                    )
                elif target.exists():
                    operations.append(
                        PlanOperation(
                            "CONFLICT",
                            relative,
                            f"new component {component_id} collides with an existing path",
                            "component",
                        )
                    )
                else:
                    operations.append(
                        PlanOperation("ADD", relative, component_id, "component")
                    )

        for component_id in sorted(previous_active - selected_components):
            modified = self._ComponentModified_Is(
                destination, previous_components.get(component_id, {})
            )
            detail = "component deactivated; project-owned source is retained"
            if modified:
                detail += " (local source changes detected)"
            operations.append(
                PlanOperation(
                    "DEACTIVATE",
                    component_id,
                    detail,
                    "component",
                    dangerous=True,
                )
            )

        previous_model = previous.get("model", {})
        if not new_project:
            for field_name, old_value, new_value in (
                ("MCU", previous_model.get("mcu", model.mcu), model.mcu),
                (
                    "target",
                    previous_model.get("target_profile", model.build.target_profile),
                    model.build.target_profile,
                ),
            ):
                if old_value != new_value:
                    operations.append(
                        PlanOperation(
                            "CHANGE",
                            field_name,
                            f"{old_value} -> {new_value}",
                            "project",
                            dangerous=True,
                        )
                    )

        for relative, content in sorted(desired.items()):
            target = destination.joinpath(*relative.split("/"))
            dangerous = False
            detail = "FCCG-managed file"
            if not target.exists():
                operation = "ADD"
            elif target.is_file() and target.read_bytes() == content:
                operation = "UNCHANGED"
            elif target.is_file():
                operation = "MODIFY"
                if relative == ".eide/eide.yml":
                    try:
                        current_fields = EideOwnedFields_Normalize(
                            target.read_text(encoding="utf-8")
                        )
                    except (OSError, UnicodeError, EideOwnershipError) as error:
                        operations.append(
                            PlanOperation(
                                "CONFLICT",
                                relative,
                                f"EIDE configuration cannot be normalized: {error}",
                                "generated",
                                dangerous=True,
                            )
                        )
                        continue
                    desired_fields = EideOwnedFields_Normalize(
                        content.decode("utf-8")
                    )
                    recorded_fields = previous.get("eide", {}).get(
                        "owned_fields"
                    )
                    if isinstance(recorded_fields, dict) and (
                        current_fields != recorded_fields
                    ):
                        dangerous = True
                        changed = EideOwnedFields_Compare(
                            recorded_fields, current_fields
                        )
                        detail = (
                            "EIDE build-owned fields were manually modified: "
                            + ", ".join(changed)
                        )
                    else:
                        changed = EideOwnedFields_Compare(
                            current_fields, desired_fields
                        )
                        detail = (
                            "EIDE build-owned fields updated: "
                            + ", ".join(changed)
                        )
            else:
                operation = "CONFLICT"
            operations.append(
                PlanOperation(
                    operation, relative, detail, "generated", dangerous=dangerous
                )
            )

        operations.extend(
            self._HardwareOperations_Get(
                model, destination, hardware_files, previous, new_project
            )
        )
        return GenerationPlan(
            destination, tuple(operations), validation, new_project
        )

    def Apply(
        self,
        model: ProjectModel,
        plan: GenerationPlan,
        *,
        confirm_dangerous: bool = False,
        progress_callback: GenerationProgressCallback | None = None,
    ) -> ApplyResult:
        if not plan.valid:
            raise ProjectAssemblerError(
                "Cannot apply an invalid or conflicting generation plan"
            )
        if plan.dangerous and not confirm_dangerous:
            raise ProjectAssemblerError(
                "Dangerous operations require an explicit confirmation"
            )
        self._Progress_Report(
            progress_callback, 1, "validate_configuration", False
        )
        expected = self.Plan(model, plan.project_root)
        if (
            expected.operations != plan.operations
            or expected.new_project != plan.new_project
        ):
            raise ProjectAssemblerError(
                "Project state changed after planning; create a new plan"
            )
        self._Progress_Report(
            progress_callback, 1, "validate_configuration", True
        )
        if plan.new_project:
            return self._NewProject_Apply(
                model, plan.project_root, progress_callback
            )
        return self._ExistingProject_Apply(
            model,
            plan.project_root,
            replace_hardware=plan.dangerous,
            progress_callback=progress_callback,
        )

    def _DesiredFiles_Get(
        self,
        model: ProjectModel,
        project_root: Path,
        hardware_files: dict[str, bytes] | None = None,
        progress_callback: GenerationProgressCallback | None = None,
    ) -> tuple[dict[str, bytes], dict]:
        self._Progress_Report(progress_callback, 4, "generate_glue", False)
        graph = SourceGraph_Resolve(model, self.catalog)
        desired = GeneratedFiles_Render(model, self.catalog, graph)
        self._Progress_Report(progress_callback, 4, "generate_glue", True)

        self._Progress_Report(
            progress_callback, 5, "generate_environments", False
        )
        desired.update(MetadataFiles_Render(model, self.catalog, graph))
        previous = self._Ownership_Load(project_root)
        eide_relative = ".eide/eide.yml"
        eide_target = project_root / ".eide" / "eide.yml"
        desired_eide = desired[eide_relative].decode("utf-8")
        desired_eide_fields = EideOwnedFields_Normalize(desired_eide)
        if eide_target.is_file():
            try:
                current_eide = eide_target.read_text(encoding="utf-8")
                current_eide_fields = EideOwnedFields_Normalize(current_eide)
            except (OSError, UnicodeError, EideOwnershipError) as error:
                raise ProjectAssemblerError(
                    f"Invalid EIDE configuration: {error}"
                ) from error
            if current_eide_fields == desired_eide_fields:
                desired[eide_relative] = eide_target.read_bytes()
            else:
                desired[eide_relative] = EideOwnedFields_Merge(
                    current_eide, desired_eide
                ).encode("utf-8")
        self._Progress_Report(
            progress_callback, 5, "generate_environments", True
        )

        self._Progress_Report(
            progress_callback, 6, "generate_documents", False
        )
        for relative in desired:
            try:
                self.policy.RelativePath_Validate(relative)
            except ValueError as error:
                raise ProjectAssemblerError(
                    f"Renderer produced an unsafe managed path: {relative!r}"
                ) from error
        components = dict(previous.get("components", {}))
        components.update(
            {
                component_id: ComponentProvenance_Get(self.catalog, component_id)
                for component_id in model.ComponentIds_Get()
            }
        )
        hardware_files = hardware_files or {}
        hardware_hashes = {
            path: hashlib.sha256(content).hexdigest()
            for path, content in sorted(hardware_files.items())
        }
        managed_files = sorted((*desired.keys(), ".fccg/ownership.json"))
        ownership = {
            "format_version": 2,
            "generation_fingerprint": f"{ProjectGenerationFingerprint_Get(model):08x}",
            "active_components": list(model.ComponentIds_Get()),
            "components": components,
            "managed_files": managed_files,
            "managed_hashes": {
                path: hashlib.sha256(content).hexdigest()
                for path, content in sorted(desired.items())
            },
            "eide": {
                "owned_fingerprint": EideOwnedFingerprint_Get(
                    desired_eide_fields
                ),
                "owned_fields": desired_eide_fields,
            },
            "hardware": {
                "snapshot_id": (
                    model.hardware.snapshot_id
                    if model.hardware.mode == "custom"
                    else ""
                ),
                "resource_binding_fingerprint": (
                    HardwareResourceBindingFingerprint_Get(model, self.catalog)
                ),
                "files": hardware_hashes,
            },
            "model": {
                "mcu": model.mcu,
                "target_profile": model.build.target_profile,
            },
        }
        desired[".fccg/ownership.json"] = (
            json.dumps(ownership, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        self._Progress_Report(
            progress_callback, 6, "generate_documents", True
        )
        return desired, ownership

    def _Ownership_Load(self, project_root: Path) -> dict:
        path = project_root / ".fccg" / "ownership.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectAssemblerError(
                f"Invalid project ownership metadata: {error}"
            ) from error
        if not isinstance(value, dict) or value.get("format_version") not in (
            0,
            1,
            2,
        ):
            raise ProjectAssemblerError("Unsupported project ownership metadata")
        return value

    def _StaleManagedPaths_Get(
        self, previous: dict, desired_paths: set[str]
    ) -> tuple[str, ...]:
        recorded = previous.get("managed_files", ())
        if not isinstance(recorded, list):
            return ()
        stale: list[str] = []
        for relative in recorded:
            if not isinstance(relative, str) or relative in desired_paths:
                continue
            try:
                portable = self.policy.RelativePath_Validate(relative)
            except ValueError as error:
                raise ProjectAssemblerError(
                    f"Invalid managed path in ownership metadata: {relative!r}"
                ) from error
            stale.append(portable.as_posix())
        return tuple(sorted(set(stale)))

    def _HardwareFiles_Get(self, model: ProjectModel) -> dict[str, bytes]:
        if model.hardware.mode != "custom":
            return {}
        snapshot_id = model.hardware.snapshot_id
        if not _Sha256_Is(snapshot_id):
            raise ProjectAssemblerError("Custom hardware snapshot id is invalid")
        snapshot = self.internal_policy.Path_Resolve(
            self.internal_policy.root
            / ".fccg"
            / "hardware_imports"
            / snapshot_id
            / "STM32CubeMX",
            allow_root=False,
        )
        if not snapshot.is_dir():
            raise ProjectAssemblerError(
                f"Custom hardware snapshot is unavailable: {snapshot_id}"
            )
        files: dict[str, bytes] = {}
        for source in sorted(snapshot.rglob("*")):
            if source.is_symlink():
                raise ProjectAssemblerError("Hardware snapshot contains a symlink")
            if not source.is_file():
                continue
            relative = source.relative_to(snapshot).as_posix()
            target = f"{self.HARDWARE_ROOT}/{relative}"
            self.internal_policy.RelativePath_Validate(target)
            files[target] = source.read_bytes()
        return files

    def _HardwareOperations_Get(
        self,
        model: ProjectModel,
        destination: Path,
        hardware_files: dict[str, bytes],
        previous: dict,
        new_project: bool,
    ) -> list[PlanOperation]:
        previous_hardware = previous.get("hardware", {})
        previous_snapshot = str(previous_hardware.get("snapshot_id", ""))
        operations: list[PlanOperation] = []
        if model.hardware.mode != "custom":
            if previous_snapshot:
                operations.append(
                    PlanOperation(
                        "DEACTIVATE",
                        self.HARDWARE_ROOT,
                        "custom vendor snapshot retained but removed from the active source graph",
                        "hardware",
                        dangerous=True,
                    )
                )
            return operations
        if previous_snapshot and previous_snapshot != model.hardware.snapshot_id:
            return [
                PlanOperation(
                    "REPLACE_TREE",
                    self.HARDWARE_ROOT,
                    f"CubeMX snapshot {previous_snapshot[:12]} -> {model.hardware.snapshot_id[:12]}",
                    "hardware",
                    dangerous=True,
                )
            ]
        for relative, content in sorted(hardware_files.items()):
            target = destination.joinpath(*relative.split("/"))
            if new_project or not previous_snapshot:
                operation = "ADD" if not target.exists() else "CONFLICT"
                detail = "imported CubeMX vendor file"
            elif not target.is_file():
                operation = "CONFLICT"
                detail = "imported hardware file is missing; Apply will not restore it"
            else:
                operation = "PRESERVE"
                source_hash = hashlib.sha256(content).hexdigest()
                current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                detail = (
                    "locally modified vendor file"
                    if source_hash != current_hash
                    else "imported CubeMX vendor file"
                )
            operations.append(
                PlanOperation(operation, relative, detail, "hardware")
            )
        return operations

    @staticmethod
    def _ManagedPath_Is(relative: str, managed_paths: set[str]) -> bool:
        return (
            relative in managed_paths
            or relative.startswith("Generated/")
            or relative.startswith(".fccg/")
            or relative.startswith(".vscode/")
            or relative.startswith(".eide/")
        )

    @staticmethod
    def _ComponentModified_Is(destination: Path, provenance: dict) -> bool:
        files = provenance.get("files", {}) if isinstance(provenance, dict) else {}
        for relative, expected_hash in files.items():
            target = destination.joinpath(*relative.split("/"))
            if not target.is_file():
                return True
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash:
                return True
        return False

    def _NewProject_Apply(
        self,
        model: ProjectModel,
        destination: Path,
        progress_callback: GenerationProgressCallback | None,
    ) -> ApplyResult:
        if destination.exists() and any(destination.iterdir()):
            raise ProjectAssemblerError("New-project destination became non-empty")
        destination_preexisted = destination.exists()
        destination.mkdir(parents=True, exist_ok=True)
        stage = self.policy.StagingDirectory_Create("project-")
        staged_project = stage / "project"
        added = 0
        applied: list[Path] = []
        try:
            self._Progress_Report(
                progress_callback, 2, "prepare_hardware", False
            )
            hardware_files = self._HardwareFiles_Get(model)
            self._Progress_Report(
                progress_callback, 2, "prepare_hardware", True
            )

            self._Progress_Report(
                progress_callback, 3, "copy_components", False
            )
            for component_id in model.ComponentIds_Get():
                manifest = self.catalog.Component_Get(component_id)
                for source in manifest.PayloadFiles_Get():
                    relative = source.relative_to(manifest.payload_root)
                    target = staged_project / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    added += 1
            self._Progress_Report(
                progress_callback, 3, "copy_components", True
            )

            for relative, content in hardware_files.items():
                target = staged_project.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                added += 1
            desired, _ownership = self._DesiredFiles_Get(
                model, destination, hardware_files, progress_callback
            )
            for relative, content in desired.items():
                target = staged_project.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                added += 1
            self._Progress_Report(
                progress_callback, 7, "integrity_check", False
            )
            for source in sorted(
                staged_project.iterdir(),
                key=lambda item: (
                    item.name == "SilverStar.ssproject",
                    item.name,
                ),
            ):
                target = destination / source.name
                if target.exists():
                    raise ProjectAssemblerError(
                        f"New-project destination changed during apply: {target}"
                    )
                self.policy.Path_Replace(source, target)
                applied.append(target)
            return ApplyResult(destination, added, 0, 0)
        except Exception:
            for target in reversed(applied):
                if target.is_dir():
                    self.policy.Tree_Remove(target)
                else:
                    target.unlink(missing_ok=True)
            raise
        finally:
            if stage.exists():
                self.policy.Tree_Remove(stage)
            self._StagingRoot_Cleanup()
            if (
                not destination_preexisted
                and destination.is_dir()
                and not any(destination.iterdir())
            ):
                destination.rmdir()

    def _ExistingProject_Apply(
        self,
        model: ProjectModel,
        destination: Path,
        *,
        replace_hardware: bool,
        progress_callback: GenerationProgressCallback | None,
    ) -> ApplyResult:
        self._Progress_Report(
            progress_callback, 2, "prepare_hardware", False
        )
        hardware_files = self._HardwareFiles_Get(model)
        self._Progress_Report(
            progress_callback, 2, "prepare_hardware", True
        )
        previous = self._Ownership_Load(destination)
        previous_components = previous.get("components", {})
        previous_snapshot = str(previous.get("hardware", {}).get("snapshot_id", ""))
        current_snapshot = (
            model.hardware.snapshot_id if model.hardware.mode == "custom" else ""
        )
        stage = self.policy.StagingDirectory_Create("apply-")
        staged_files = stage / "files"
        backup_files = stage / "backup"
        preserved = 0
        added = 0
        modified = 0
        copied_components: list[Path] = []
        applied_managed: list[tuple[Path, bool]] = []
        removed_managed: list[tuple[Path, Path]] = []
        hardware_backup: Path | None = None
        hardware_target = destination / "HardwareGenerated" / "STM32CubeMX"
        hardware_was_replaced = False
        try:
            self._Progress_Report(
                progress_callback, 3, "copy_components", False
            )
            component_files_to_add: list[Path] = []
            for component_id in model.ComponentIds_Get():
                manifest = self.catalog.Component_Get(component_id)
                previous_component = previous_components.get(component_id, {})
                previous_files = (
                    previous_component.get("files", {})
                    if isinstance(previous_component, dict)
                    else {}
                )
                for source in manifest.PayloadFiles_Get():
                    relative = source.relative_to(manifest.payload_root)
                    if (
                        component_id in previous_components
                        and relative.as_posix() in previous_files
                    ):
                        preserved += 1
                        continue
                    staged = staged_files / "components" / relative
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, staged)
                    component_files_to_add.append(relative)
            self._Progress_Report(
                progress_callback, 3, "copy_components", True
            )

            desired, _ownership = self._DesiredFiles_Get(
                model, destination, hardware_files, progress_callback
            )

            stale_managed = self._StaleManagedPaths_Get(
                previous, set(desired)
            )

            managed_targets: list[tuple[Path, Path, bool]] = []
            for relative, content in sorted(
                desired.items(),
                key=lambda item: (
                    item[0] == "SilverStar.ssproject",
                    item[0],
                ),
            ):
                relative_path = Path(*relative.split("/"))
                staged = staged_files / "managed" / relative_path
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(content)
                target = self.policy.Path_Resolve(
                    destination / relative_path, allow_root=False
                )
                existed = target.is_file()
                if existed and target.read_bytes() == content:
                    continue
                managed_targets.append((target, staged, existed))
                if existed:
                    backup = backup_files / relative_path
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                    modified += 1
                else:
                    added += 1

            self._Progress_Report(
                progress_callback, 7, "integrity_check", False
            )
            for relative in component_files_to_add:
                staged = staged_files / "components" / relative
                target = self.policy.Path_Resolve(
                    destination / relative, allow_root=False
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged, target)
                copied_components.append(target)
                added += 1

            if current_snapshot and not previous_snapshot:
                for relative, content in hardware_files.items():
                    target = self.policy.Path_Resolve(
                        destination.joinpath(*relative.split("/")), allow_root=False
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    added += 1
            elif (
                current_snapshot
                and previous_snapshot != current_snapshot
                and replace_hardware
            ):
                staged_hardware = staged_files / "hardware"
                for relative, content in hardware_files.items():
                    suffix = Path(*relative.split("/")).relative_to(
                        Path("HardwareGenerated") / "STM32CubeMX"
                    )
                    target = staged_hardware / suffix
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                if hardware_target.exists():
                    hardware_backup = stage / "hardware-backup"
                    self.policy.Path_Replace(hardware_target, hardware_backup)
                hardware_target.parent.mkdir(parents=True, exist_ok=True)
                self.policy.Path_Replace(staged_hardware, hardware_target)
                hardware_was_replaced = True

            for relative in stale_managed:
                relative_path = Path(*relative.split("/"))
                target = self.policy.Path_Resolve(
                    destination / relative_path, allow_root=False
                )
                if not target.is_file():
                    continue
                backup = backup_files / "removed" / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                self.policy.Path_Replace(target, backup)
                removed_managed.append((target, backup))
                modified += 1

            for target, staged, existed in managed_targets:
                target.parent.mkdir(parents=True, exist_ok=True)
                self.policy.Path_Replace(staged, target)
                applied_managed.append((target, existed))
            for target, _backup in removed_managed:
                self._EmptyParents_Remove(target.parent, destination)
            return ApplyResult(
                destination,
                added,
                modified,
                preserved,
                hardware_replaced=hardware_was_replaced,
            )
        except Exception:
            for target, existed in reversed(applied_managed):
                if existed:
                    relative = target.relative_to(destination)
                    backup = backup_files / relative
                    if backup.exists():
                        self.policy.Path_Replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            for target, backup in reversed(removed_managed):
                if backup.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self.policy.Path_Replace(backup, target)
            if hardware_was_replaced:
                if hardware_target.exists():
                    self.policy.Tree_Remove(hardware_target)
                if hardware_backup is not None and hardware_backup.exists():
                    self.policy.Path_Replace(hardware_backup, hardware_target)
            for target in reversed(copied_components):
                target.unlink(missing_ok=True)
            raise
        finally:
            if stage.exists():
                self.policy.Tree_Remove(stage)
            self._StagingRoot_Cleanup()

    def _StagingRoot_Cleanup(self) -> None:
        staging_root = self.policy.Path_Resolve(".staging", allow_root=False)
        if staging_root.is_dir() and not any(staging_root.iterdir()):
            staging_root.rmdir()

    @staticmethod
    def _EmptyParents_Remove(start: Path, root: Path) -> None:
        current = start
        while current != root and current.is_dir() and not any(current.iterdir()):
            parent = current.parent
            current.rmdir()
            current = parent

    @staticmethod
    def _Progress_Report(
        callback: GenerationProgressCallback | None,
        current: int,
        subject: str,
        done: bool,
    ) -> None:
        if callback is not None:
            callback(current, 7, subject, done)


def _Sha256_Is(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
