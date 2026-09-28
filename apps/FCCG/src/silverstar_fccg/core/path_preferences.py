"""Application paths are preferences, never project generation inputs."""
from __future__ import annotations

import json
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy


def ExistingDirectory_Get(path: Path | None, fallback: Path | None = None) -> Path:
    for candidate in (path, fallback, Path.home() / "Documents", Path.home(), Path.cwd()):
        if candidate is not None:
            candidate = Path(candidate)
            for parent in (candidate, *candidate.parents):
                if parent.is_dir():
                    return parent
    return Path.cwd()


class PathPreferences:
    def __init__(self, policy: WorkspacePolicy, path: Path) -> None:
        self._policy = policy
        self.path = policy.Path_Resolve(path, allow_root=False)

    def DefaultProjectRoot_Get(self) -> Path | None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document["schema_version"] != 1:
                return None
            value = document.get("default_project_root")
            if not isinstance(value, str) or not value.strip():
                return None
            root = Path(value)
            return root if root.is_absolute() and root.is_dir() else None
        except (OSError, ValueError, TypeError):
            return None

    def DefaultProjectRoot_EffectiveGet(self) -> Path:
        for directory in (
            self.DefaultProjectRoot_Get(), Path.home() / "Documents", Path.home(), Path.cwd(),
        ):
            try:
                if directory is not None and directory.is_dir():
                    return directory
            except OSError:
                continue
        return Path.cwd()

    def DefaultProjectRoot_Set(self, root: Path) -> None:
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Default project root must be an existing directory")
        self._policy.Text_AtomicWrite(self.path, json.dumps(
            {"schema_version": 1, "default_project_root": str(root)},
            ensure_ascii=False, indent=2,
        ) + "\n")
