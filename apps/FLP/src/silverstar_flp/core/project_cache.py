"""Local cache inventory; physical removal requires proof of exclusive ownership."""
from __future__ import annotations

import re
from pathlib import Path

from silverstar_flp.core.project import Project_Load, Project_Save


def ProjectCache_Inspect(path: Path) -> dict:
    document = Project_Load(path)
    root = document.project_path.parent / (document.project_path.name + ".artifacts")
    active = {Path(reference["path"]).parts[1]: role for role, reference in
              (("saved_results", document.result_artifact), ("parsed_dataset", document.parse_artifact))
              if reference is not None}
    for history, role in ((document.removed_results, "deleted_run_backup"),
                          (document.recovery_sources, "historical_recovery_source")):
        for item in history.values():
            backup = item["backup"]
            if backup is not None and backup["project_reference"] is None:
                active.setdefault(Path(backup["artifact_reference"]["path"]).parts[1], role)
    items = []
    physical_files = {}
    if root.exists():
        if not root.resolve().is_relative_to(document.project_path.parent):
            raise ValueError("artifact_path_escape")
        for directory in sorted(root.iterdir()):
            if not re.fullmatch(r"generation-[0-9a-f]{32}", directory.name):
                continue
            if not directory.resolve().is_relative_to(root.resolve()) or not directory.is_dir():
                raise ValueError("artifact_path_escape")
            files = list(directory.iterdir())
            size = sum(file.stat().st_size for file in files if file.is_file())
            for file in files:
                info = file.lstat()
                if file.is_file() and not file.is_symlink():
                    physical_files[(info.st_dev, info.st_ino)] = info.st_size
            items.append({"generation": directory.name, "bytes": size,
                          "role": active.get(directory.name, "unreferenced"),
                          "file_count": len(files)})
    return {"project": str(document.project_path), "root": str(root),
            "reference_scope": "current_project_only", "physical_removal": "ownership_not_proven",
            "bytes": sum(item["bytes"] for item in items),
            "physical_bytes": sum(physical_files.values()), "generations": items}


def ProjectCache_ParseClear(path: Path) -> None:
    document = Project_Load(path)
    document.parse_artifact = None
    # Preserve every saved result; this operation removes only the reusable parse reference.
    Project_Save(document, path)


def ProjectCache_UnusedRemove(path: Path, generation: str) -> None:
    inventory = ProjectCache_Inspect(path)
    item = next((item for item in inventory["generations"] if item["generation"] == generation), None)
    if item is None or item["role"] != "unreferenced":
        raise ValueError("project_cache_generation_protected")
    # Another configuration-only Save As may depend on this generation through
    # an external recovery reference. Local non-reference and valid contents do
    # not establish exclusive ownership. No ownership registry exists yet, and
    # scanning a selected directory cannot prove absence of external dependents.
    raise ValueError("project_cache_generation_ownership_unproven")
