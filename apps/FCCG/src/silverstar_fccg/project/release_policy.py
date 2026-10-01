"""First-release feature boundary; legacy schema and implementations stay readable."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.alignment import AlignmentConfiguration, AlignmentConstraint
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.model import ProjectModel, LogDecoderProfileReference


def ReleaseCompatibilityIssues_Get(model: ProjectModel) -> tuple[str, ...]:
    issues = []
    if any(".magnetometer." in item.plugin for item in model.device_instances):
        issues.append("Magnetometer devices are deferred until December. Remove the device explicitly in a copy of the project; the original configuration is preserved.")
    if any(key.startswith("magnetometer.") for key in model.capability_source_overrides):
        issues.append("Legacy magnetic source selection is retained. Explicitly remove it before first-release generation.")
    if any(item.kind == "magnetic_field" for item in model.alignment.constraints):
        issues.append("Legacy magnetic constraints are retained, including dormant ones. Explicitly select the release vector pair and confirm before generation.")
    if (model.strategies.get("alignment") or "").endswith("vector_constraints"):
        if tuple(item.kind for item in model.alignment.constraints) != ("gravity", "reference_direction"):
            issues.append("Legacy alignment constraints are preserved. Select the first-release gravity + known-direction pair and confirm its parameters; navigation is never migrated silently.")
    return tuple(issues)


def ReleaseMigrationModel_Create(original: ProjectModel) -> ProjectModel:
    """Build the explicitly requested KF6 copy; never mutate the loaded model."""
    candidate = deepcopy(original)
    removed = {item.instance_id for item in candidate.device_instances
               if ".magnetometer." in item.plugin}
    candidate.device_instances = [item for item in candidate.device_instances
                                  if item.instance_id not in removed]
    candidate.resource_assignments = {key: value for key, value in candidate.resource_assignments.items()
                                      if key.split(":", 1)[0] not in removed}
    candidate.capability_source_overrides = {key: value for key, value in candidate.capability_source_overrides.items()
                                            if not key.startswith("magnetometer.") and value not in removed}
    gravity = next(item for item in original.alignment.constraints if item.kind == "gravity")
    direction = next((item for item in original.alignment.constraints if item.kind == "reference_direction"),
                     AlignmentConstraint("reference_direction"))
    candidate.alignment = AlignmentConfiguration(constraints=(gravity, direction))
    candidate.strategies["alignment"] = "silverstar.algorithm.alignment.vector_constraints"
    candidate.strategies["estimator"] = "silverstar.algorithm.estimator.kf6"
    candidate.capability_source_overrides.pop("attitude.external", None)
    candidate.log_decoder_profile = LogDecoderProfileReference()
    return candidate


def ReleaseMigrationCopy_Save(original: ProjectModel, candidate: ProjectModel,
                              destination: Path, source_bytes: bytes | None,
                              source_root: Path | None = None) -> None:
    """Create a new empty root only after the GUI's explicit confirmation."""
    policy = WorkspacePolicy(destination)
    if source_root is not None and policy.root.is_relative_to(source_root.resolve()):
        raise ValueError("Migration copy must be outside the original project tree")
    if destination.is_symlink() or (hasattr(destination, "is_junction") and destination.is_junction()):
        raise ValueError("Migration destination must not be a link")
    if policy.root.exists() and any(policy.root.iterdir()):
        raise ValueError("Migration destination must be empty; original project is never overwritten")
    if ReleaseCompatibilityIssues_Get(candidate):
        raise ValueError("Migration candidate still contains deferred selections")
    loaded = json.dumps(original.Dictionary_Get(), ensure_ascii=False, indent=2) + "\n"
    original_bytes = source_bytes if source_bytes is not None else loaded.encode("utf-8")
    policy.Bytes_AtomicWrite("Compatibility/Legacy_Original.ssproject", original_bytes)
    policy.Text_AtomicWrite("Compatibility/Legacy_Loaded.ssproject", loaded)
    policy.Text_AtomicWrite("Compatibility/Migration.json", json.dumps(dict(
        policy="explicit first-release KF6 + gravity/known-direction copy",
        original_sha256=hashlib.sha256(original_bytes).hexdigest(),
        original_model=original.Dictionary_Get(), migrated_model=candidate.Dictionary_Get(),
        source_logs_and_decoders="untouched at original location; not copied or modified",
        direction_review_required=True), ensure_ascii=False, indent=2) + "\n")
    # Publish the descriptor last; failed saves never publish a GUI success.
    ProjectRoot_Save(candidate, policy.root, create_new=True)
