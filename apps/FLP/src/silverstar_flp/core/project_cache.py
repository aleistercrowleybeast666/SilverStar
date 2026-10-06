"""Explicit cache inventory and conservative manual removal of unused generations."""
from __future__ import annotations

import re
from pathlib import Path

from silverstar_flp.core.artifacts import Artifact_Read
from silverstar_flp.core.project import Project_Load, Project_Save


def ProjectCache_Inspect(path: Path) -> dict:
    document = Project_Load(path)
    root = document.project_path.parent / (document.project_path.name + ".artifacts")
    active = {Path(reference["path"]).parts[1]: role for role, reference in
              (("saved_results", document.result_artifact), ("parsed_dataset", document.parse_artifact))
              if reference is not None}
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
            "bytes": sum(item["bytes"] for item in items),
            "physical_bytes": sum(physical_files.values()), "generations": items}


def ProjectCache_ParseClear(path: Path) -> None:
    document = Project_Load(path)
    document.parse_artifact = None
    # Preserve every saved result; this operation removes only the reusable parse reference.
    Project_Save(document, path)


def ProjectCache_UnusedRemove(path: Path, generation: str) -> None:
    from silverstar_flp.core.artifacts import FileHash_Get, _Json_Load, RecordFiles_Get
    inventory = ProjectCache_Inspect(path)
    item = next((item for item in inventory["generations"] if item["generation"] == generation), None)
    if item is None or item["role"] != "unreferenced":
        raise ValueError("project_cache_generation_protected")
    directory = Path(inventory["root"]) / generation
    manifests = [file for file in directory.iterdir() if file.name in ("manifest.json", "manifest.json.gz")]
    if len(manifests) != 1:
        raise ValueError("project_cache_generation_not_verified")
    manifest = manifests[0]
    payload = _Json_Load(manifest)
    expected = set(payload.get("arrays", {})) | {manifest.name} | RecordFiles_Get(payload.get("payload"))
    files = list(directory.iterdir())
    if {file.name for file in files} != expected:
        raise ValueError("project_cache_generation_not_verified")
    for file in files:
        if file.is_symlink() or not file.resolve().is_relative_to(directory.resolve()) or not file.is_file():
            raise ValueError("project_cache_generation_not_verified")
    reference = {"path": manifest.relative_to(Path(path).resolve().parent).as_posix(),
                 "sha256": FileHash_Get(manifest)}
    Artifact_Read(Path(path).resolve(), reference)
    # Re-read live references immediately before deletion; never remove a live saved generation.
    refreshed = ProjectCache_Inspect(path)
    if any(entry["generation"] == generation and entry["role"] != "unreferenced"
           for entry in refreshed["generations"]):
        raise ValueError("project_cache_generation_protected")
    for file in files:
        file.unlink()
    directory.rmdir()
