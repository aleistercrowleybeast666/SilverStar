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

    @classmethod
    def Product_Open(cls):
        from PySide6.QtCore import QStandardPaths
        from silverstar_flp.app.version import PRODUCT_NAME

        root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
        return cls(root / "SilverStar" / PRODUCT_NAME / "path_preferences.json")

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
        document = self._Document_Get()
        document["default_project_root"] = str(root)
        self._Document_Save(document)

    def _Document_Get(self) -> dict:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(document, dict) and type(document.get("schema_version")) is int and document["schema_version"] == 1:
                return document
        except (OSError, ValueError, TypeError):
            pass
        return {"schema_version": 1}

    def DecoderDirectories_Get(self) -> tuple[Path, ...]:
        values = self._Document_Get().get("decoder_search_directories", [])
        if not isinstance(values, list) or len(values) > 4:
            return ()
        directories = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                return ()
            path = Path(value)
            if not path.is_absolute():
                return ()
            # Keep disconnected removable directories visible for the user;
            # the bounded scanner skips unavailable directories at open time.
            if path not in directories:
                directories.append(path)
        return tuple(directories)

    def DecoderDirectories_Set(self, directories: tuple[Path, ...]) -> None:
        if len(directories) > 4:
            raise ValueError("decoder_search_directory_limit")
        resolved = []
        for directory in directories:
            path = Path(directory).resolve()
            if path not in resolved:
                resolved.append(path)
        document = self._Document_Get()
        document["decoder_search_directories"] = [str(path) for path in resolved]
        self._Document_Save(document)

    def _Document_Save(self, document: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=".path_preferences-", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    document,
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
