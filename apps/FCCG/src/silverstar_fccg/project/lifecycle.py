from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.hardware_preparation import (
    HardwarePreparationFingerprint_Get,
    HardwareResourceBindingFingerprint_Get,
)
from silverstar_fccg.generator.eide_ownership import (
    EideOwnershipError,
    EideOwnedFields_Normalize,
)
from silverstar_fccg.project.generation_state import (
    ProjectGenerationFingerprint_Get,
    ProjectGenerationState_Normalize,
)
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel, ProjectModel_Load


class ProjectLifecycleState(StrEnum):
    DRAFT = "draft"
    DIRTY = "dirty"
    MATERIALIZING = "materializing"
    READY = "ready"
    BUILDING = "building"
    ERROR = "error"


BUILDABLE_MAKE_TARGETS = (
    "all",
    "clean",
    "clean-all",
    "host-tests",
    "architecture-check",
    "power10-check",
    "static-analysis",
    "artifact-check",
)


@dataclass(frozen=True, slots=True)
class ProjectReadiness:
    state: ProjectLifecycleState
    missing: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    technical_detail: str = ""

    @property
    def ready(self) -> bool:
        return self.state == ProjectLifecycleState.READY


def MakefileTarget_Has(makefile_text: str, target: str) -> bool:
    pattern = rf"^[ \t]*{re.escape(target)}[ \t]*:(?:[ \t]|$)"
    return re.search(pattern, makefile_text, re.MULTILINE) is not None


def ProjectReadiness_Inspect(
    model: ProjectModel,
    project_root: Path,
    catalog: PluginCatalog,
) -> ProjectReadiness:
    root = Path(project_root).resolve(strict=False)
    project_file = root / "SilverStar.ssproject"
    if not project_file.is_file():
        return ProjectReadiness(
            ProjectLifecycleState.DRAFT,
            missing=("SilverStar.ssproject",),
        )

    try:
        saved_model = ProjectModel_Load(project_file)
    except Exception as error:
        return ProjectReadiness(
            ProjectLifecycleState.ERROR,
            stale=("SilverStar.ssproject",),
            technical_detail=str(error),
        )

    stale: list[str] = []
    pre_release_migration = model.reference_provenance.get(
        "pre_release_migration"
    )
    if (
        "silverstar.core.0_0_9" in model.component_provenance
        or (
            isinstance(pre_release_migration, dict)
            and pre_release_migration.get("requires_new_output_directory") is True
        )
    ):
        stale.append("SilverStar.ssproject:pre_release_rebuild_required")
    if ProjectGenerationState_Normalize(
        saved_model
    ) != ProjectGenerationState_Normalize(model):
        stale.append("SilverStar.ssproject")

    logging_enabled = model.protocols.get("logging") is not None
    required_files = (
        "Makefile",
        ".fccg/ownership.json",
        ".fccg/hardware-preparation.json",
        ".eide/eide.yml",
        ".vscode/tasks.json",
        f"{model.identity.name}.code-workspace",
        *(
            (
                "Generated/Inc/project_log_decoder_profile.h",
                "Generated/Src/project_log_decoder_profile.c",
                "Logs/README.md",
                (
                    model.log_decoder_profile.relative_path
                    or f"{model.identity.name}.ssdecoder"
                ),
            )
            if logging_enabled
            else ()
        ),
    )
    required_directories = (
        "BuildSystem",
        "Generated",
        f"Targets/{model.build.target_profile}",
    )
    missing = [
        relative
        for relative in required_files
        if not root.joinpath(*relative.split("/")).is_file()
    ]
    missing.extend(
        relative
        for relative in required_directories
        if not root.joinpath(*relative.split("/")).is_dir()
    )

    decoder_reference = model.log_decoder_profile
    if logging_enabled and (
        not decoder_reference.relative_path
        or not decoder_reference.generation_profile_sha256
        or not decoder_reference.package_sha256
    ):
        stale.append("SilverStar.ssproject:log_decoder_profile")
    elif logging_enabled:
        decoder_package = root.joinpath(
            *decoder_reference.relative_path.split("/")
        )
        if decoder_package.is_file() and (
            hashlib.sha256(decoder_package.read_bytes()).hexdigest()
            != decoder_reference.package_sha256
        ):
            stale.append(decoder_reference.relative_path)
    elif any(
        (
            decoder_reference.relative_path,
            decoder_reference.package_schema,
            decoder_reference.container_plugin_id,
            decoder_reference.generation_profile_sha256,
            decoder_reference.package_sha256,
        )
    ):
        stale.append("SilverStar.ssproject:log_decoder_profile")

    for component_id in model.ComponentIds_Get():
        try:
            manifest = catalog.Component_Get(component_id)
            payload_files = manifest.PayloadFiles_Get()
        except Exception as error:
            return ProjectReadiness(
                ProjectLifecycleState.ERROR,
                tuple(dict.fromkeys(missing)),
                tuple(dict.fromkeys(stale)),
                str(error),
            )
        for source in payload_files:
            relative = source.relative_to(manifest.payload_root)
            if not (root / relative).is_file():
                missing.append(relative.as_posix())

    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            makefile_text = makefile.read_text(encoding="utf-8")
        except OSError as error:
            return ProjectReadiness(
                ProjectLifecycleState.ERROR,
                tuple(dict.fromkeys(missing)),
                tuple(dict.fromkeys(stale)),
                str(error),
            )
        if "SilverStar authoritative build entry" not in makefile_text:
            stale.append("Makefile")
        if "# FCCG cleanup contract: determinate-v1" not in makefile_text:
            stale.append("Makefile:cleanup-progress")
        for target in BUILDABLE_MAKE_TARGETS:
            if not MakefileTarget_Has(makefile_text, target):
                stale.append(f"Makefile:{target}")

    preparation_file = root / ".fccg" / "hardware-preparation.json"
    if preparation_file.is_file():
        try:
            preparation = json.loads(preparation_file.read_text(encoding="utf-8"))
            actual_fingerprint = preparation.get("fingerprint")
            expected_fingerprint = HardwarePreparationFingerprint_Get(model, catalog)
            if actual_fingerprint != expected_fingerprint:
                stale.append(".fccg/hardware-preparation.json")
            actual_binding_fingerprint = preparation.get(
                "resource_binding_fingerprint"
            )
            expected_binding_fingerprint = (
                HardwareResourceBindingFingerprint_Get(model, catalog)
            )
            if actual_binding_fingerprint != expected_binding_fingerprint:
                stale.append(".fccg/hardware-preparation.json:resource-binding")
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            AttributeError,
            EideOwnershipError,
            ValueError,
        ) as error:
            return ProjectReadiness(
                ProjectLifecycleState.ERROR,
                tuple(dict.fromkeys(missing)),
                tuple(dict.fromkeys(stale)),
                str(error),
            )

    ownership_file = root / ".fccg" / "ownership.json"
    if ownership_file.is_file():
        try:
            ownership = json.loads(ownership_file.read_text(encoding="utf-8"))
            recorded_fingerprint = ownership.get("generation_fingerprint")
            expected_generation_fingerprint = (
                f"{ProjectGenerationFingerprint_Get(model):08x}"
            )
            if (
                recorded_fingerprint is not None
                and recorded_fingerprint != expected_generation_fingerprint
            ):
                stale.append(".fccg/ownership.json")
            recorded_binding_fingerprint = ownership.get("hardware", {}).get(
                "resource_binding_fingerprint"
            )
            expected_binding_fingerprint = (
                HardwareResourceBindingFingerprint_Get(model, catalog)
            )
            if recorded_binding_fingerprint != expected_binding_fingerprint:
                stale.append(".fccg/ownership.json:resource-binding")
            managed_hashes = ownership.get("managed_hashes")
            if isinstance(managed_hashes, dict) and managed_hashes:
                root_policy = WorkspacePolicy(root)
                for relative, expected_hash in managed_hashes.items():
                    if not isinstance(relative, str) or not isinstance(
                        expected_hash, str
                    ):
                        stale.append(".fccg/ownership.json")
                        break
                    try:
                        portable = root_policy.RelativePath_Validate(relative)
                    except ValueError:
                        stale.append(".fccg/ownership.json")
                        break
                    target = root.joinpath(*portable.parts)
                    if not target.is_file():
                        missing.append(relative)
                    elif relative == ".eide/eide.yml":
                        recorded_fields = ownership.get("eide", {}).get(
                            "owned_fields"
                        )
                        if not isinstance(recorded_fields, dict) or (
                            EideOwnedFields_Normalize(
                                target.read_text(encoding="utf-8")
                            )
                            != recorded_fields
                        ):
                            stale.append(relative)
                    elif (
                        hashlib.sha256(target.read_bytes()).hexdigest()
                        != expected_hash
                    ):
                        stale.append(relative)
            else:
                stale.append(".fccg/ownership.json")
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            AttributeError,
            EideOwnershipError,
            ValueError,
        ) as error:
            return ProjectReadiness(
                ProjectLifecycleState.ERROR,
                tuple(dict.fromkeys(missing)),
                tuple(dict.fromkeys(stale)),
                str(error),
            )

    if missing or stale:
        return ProjectReadiness(
            ProjectLifecycleState.DIRTY,
            tuple(dict.fromkeys(missing)),
            tuple(dict.fromkeys(stale)),
        )
    return ProjectReadiness(ProjectLifecycleState.READY)
