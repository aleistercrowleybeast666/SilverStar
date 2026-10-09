"""Bind automatic results to generated target inputs, without modifying them."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.lifecycle import MakefileTarget_Has
from silverstar_fccg.project.model import ProjectModel_Load


QUALITY_TASKS = ("host_tests", "architecture_check", "power10_check",
                 "static_analysis", "artifact_check")
_OUTPUT_DIRECTORIES = {"build", ".git", "__pycache__", ".pytest_cache"}
_RESULT_FILES = {".fccg/quality-results.json", ".fccg/power10-report.json"}


def QualityInput_Require(root: Path, target: str, task: str) -> None:
    policy = WorkspacePolicy(root)
    if target not in {"flight", "ground"} or task not in QUALITY_TASKS:
        raise ValueError("Unknown quality target or task")
    if root.is_symlink() or root.resolve() != root.absolute() or (hasattr(root, "is_junction") and root.is_junction()):
        raise ValueError("Generated target directory must not be a link")
    makefile = policy.Path_Resolve("Makefile", allow_root=False)
    text = makefile.read_text(encoding="utf-8")
    marker = ("SilverStar authoritative build entry" if target == "flight"
              else "Generated Ground target; source graph is Generated/ground_source_graph.json.")
    if marker not in text or not MakefileTarget_Has(text, task.replace("_", "-")):
        raise ValueError(f"Generated {target} Makefile has no {task} entry")
    required = (("SilverStar.ssproject",) if target == "flight" else
                ("Generated/ground_source_graph.json", "Generated/ground_target_metadata.json"))
    for name in required:
        if not policy.Path_Resolve(name, allow_root=False).is_file():
            raise ValueError(f"Generated {target} input missing: {name}")
    if target == "flight":
        ProjectModel_Load(policy.Path_Resolve("SilverStar.ssproject", allow_root=False))
    else:
        graph = json.loads(policy.Path_Resolve(required[0], allow_root=False).read_text(encoding="utf-8"))
        metadata = json.loads(policy.Path_Resolve(required[1], allow_root=False).read_text(encoding="utf-8"))
        if not isinstance(graph, dict) or not isinstance(metadata, dict) or metadata.get("target_role") != "ground_station":
            raise ValueError("Invalid generated Ground target identity")
        for key in ("sources", "asm_sources", "include_dirs", "defines"):
            if not isinstance(graph.get(key), list) or not all(isinstance(item, str) for item in graph[key]):
                raise ValueError(f"Invalid Ground source graph field: {key}")
        if not isinstance(graph.get("linker_script"), str) or not graph["linker_script"]:
            raise ValueError("Invalid Ground linker input")
        for name in (*graph["sources"], *graph["asm_sources"], *graph["include_dirs"], graph["linker_script"]):
            if not policy.Path_Resolve(name, allow_root=False).exists():
                raise ValueError(f"Missing Ground graph input: {name}")


def QualityInputHash_Get(root: Path, target: str, task: str, command: tuple[str, ...] = (),
                         *, include_artifacts: bool = True) -> str:
    """Hash the in-root input tree; build products count only for artifact checks.

    This is provenance for the recorded check, not a dependency-closure proof.
    Links/junctions are rejected, including ones inside otherwise ignored outputs.
    """
    QualityInput_Require(root, target, task)
    policy = WorkspacePolicy(root)
    digest = hashlib.sha256(json.dumps([target, task, str(policy.root), command],
                                     ensure_ascii=True).encode())
    tools = [command[0]] if command else []
    tools.append(os.environ.get("PYTHON", "python"))
    if task == "power10_check":
        tools.append("powershell")
    if task == "host_tests":
        tools.extend(item.partition("=")[2] for item in command if item.startswith("HOST_CC="))
    if task in {"static_analysis", "artifact_check"}:
        gcc_dirs = [item.partition("=")[2] for item in command if item.startswith("GCC_PATH=")]
        tools.append(str(Path(gcc_dirs[0]) / "arm-none-eabi-gcc.exe") if gcc_dirs else "arm-none-eabi-gcc")
    for tool in dict.fromkeys(tools):
        resolved = shutil.which(tool)
        digest.update(json.dumps([tool, resolved], ensure_ascii=True).encode())
        if resolved:
            with Path(resolved).open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    def read_error(error: OSError) -> None:
        raise error

    for current, dirs, names in os.walk(root, followlinks=False, onerror=read_error):
        directory = Path(current)
        for name in (*dirs, *names):
            path = directory / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"Quality input must not be a link: {path}")
            if policy.Path_Resolve(path, allow_root=False) != path.absolute():
                raise ValueError(f"Quality input must not redirect through a link: {path}")
        dirs[:] = sorted(name for name in dirs if name not in _OUTPUT_DIRECTORIES
                         or (name == "build" and task == "artifact_check" and include_artifacts))
        for name in sorted(names):
            path = directory / name
            relative = path.relative_to(root).as_posix()
            if relative in _RESULT_FILES:
                continue
            if name.endswith(".pyc"):
                continue
            if relative.startswith("build/") and path.suffix not in {".elf", ".bin", ".hex", ".map"}:
                continue
            checked = policy.Path_Resolve(relative, allow_root=False)
            with checked.open("rb") as stream:
                file_digest = hashlib.file_digest(stream, "sha256").hexdigest()
            digest.update(json.dumps([relative, file_digest], ensure_ascii=True).encode())
    return digest.hexdigest()
