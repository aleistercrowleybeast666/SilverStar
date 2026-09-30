"""User-visible SilverStar project root layout."""

from __future__ import annotations

import json
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel, ProjectModel_Load


FLIGHT_DIRECTORY = "Flight_Controller"
GROUND_DIRECTORY = "Ground_Station"
LOG_DIRECTORY = "Log"
PROJECT_FILENAME = "SilverStar.ssproject"


def ProjectRoot_Save(
    model: ProjectModel, project_root: Path, *, create_new: bool = False,
) -> Path:
    """Save the shared project without implicitly generating either target."""
    policy = WorkspacePolicy(project_root)
    root = policy.root
    project_file = root / PROJECT_FILENAME
    if project_file.is_symlink() or (
        hasattr(project_file, "is_junction") and project_file.is_junction()
    ):
        raise ValueError(f"Project descriptor must not be a link: {project_file}")
    if create_new and project_file.exists():
        raise FileExistsError(f"Project descriptor already exists: {project_file}")
    if project_file.exists():
        if not project_file.is_file():
            raise ValueError(f"Project descriptor is not a file: {project_file}")
        current = ProjectModel_Load(project_file)
        if current.identity.name != model.identity.name:
            raise ValueError("Project root belongs to another SilverStar project")
    directories = tuple(root / name for name in (
        FLIGHT_DIRECTORY, GROUND_DIRECTORY, LOG_DIRECTORY,
    ))
    # Check every child before creating anything, preserving same-named inputs.
    for directory in directories:
        policy.Path_Resolve(directory)
        if directory.is_symlink() or (
            hasattr(directory, "is_junction") and directory.is_junction()
        ):
            raise ValueError(f"Project directory must not be a link: {directory}")
        if directory.exists() and not directory.is_dir():
            raise FileExistsError(f"Project directory is occupied by a file: {directory}")
    policy.Directory_Ensure(root)
    for directory in directories:
        policy.Directory_Ensure(directory)
    policy.Text_AtomicWrite(
        project_file, json.dumps(model.Dictionary_Get(), ensure_ascii=False, indent=2) + "\n"
    )
    return root
