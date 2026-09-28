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


def ProjectRoot_Save(model: ProjectModel, project_root: Path) -> Path:
    """Save the shared project without implicitly generating either target."""
    policy = WorkspacePolicy(project_root)
    root = policy.Directory_Ensure(policy.root)
    project_file = root / PROJECT_FILENAME
    if project_file.exists():
        if not project_file.is_file():
            raise ValueError(f"Project descriptor is not a file: {project_file}")
        current = ProjectModel_Load(project_file)
        if current.identity.name != model.identity.name:
            raise ValueError("Project root belongs to another SilverStar project")
    policy.Directory_Ensure(root / LOG_DIRECTORY)
    policy.Text_AtomicWrite(
        project_file, json.dumps(model.Dictionary_Get(), ensure_ascii=False, indent=2) + "\n"
    )
    return root
