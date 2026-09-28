"""Independent application path preferences; no .ssflp schema fields."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


def ExistingDirectory_Get(path: Path | None, fallback: Path | None = None) -> Path:
    for candidate in (path, fallback, Path.home() / "Documents", Path.home(), Path.cwd()):
        if candidate is not None:
            for parent in (Path(candidate), *Path(candidate).parents):
                if parent.is_dir():
                    return parent
    return Path.cwd()


class PathPreferences:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def DefaultProjectRoot_Get(self) -> Path | None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or type(document.get("schema_version")) is not int
                or document["schema_version"] != 1
            ):
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=".path_preferences-", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    {"schema_version": 1, "default_project_root": str(root)},
                    stream,
                    ensure_ascii=False,
                    indent=2,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def ProjectDirectory_Prepare(project_path: Path) -> None:
    """Called only after the user accepts the exact new-project destination."""
    project_path.parent.mkdir(parents=True, exist_ok=True)


def ExportDirectory_Default(log_path: Path, project_path: Path | None = None) -> Path:
    name = log_path.name
    if log_path.suffix.casefold() in (".bin", ".sslog"):
        name = name[: -len(log_path.suffix)]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .") or "Log"
    parent = project_path.parent if project_path is not None else log_path.parent
    base = parent / ("Result_" + name)
    candidate = base
    index = 2
    while candidate.exists():
        candidate = parent / (base.name + "_" + str(index))
        index += 1
    return candidate
