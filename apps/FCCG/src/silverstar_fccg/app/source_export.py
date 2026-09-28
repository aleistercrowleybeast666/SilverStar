from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from silverstar_fccg.core.workspace import WorkspacePolicy


@dataclass(frozen=True, slots=True)
class SourcePackageExportResult:
    destination: Path
    file_count: int
    source_bytes: int
    archive_bytes: int


_EXCLUDED_ROOTS = frozenset(
    {
        ".git",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".fccg",
        ".staging",
        "build",
        "dist",
    }
)
_EXCLUDED_TEST_ROOTS = frozenset(
    {
        ".tmp",
        ".pytest-work",
        ".pytest-cache",
        "artifacts",
        "generated_projects",
        "reference_copy",
    }
)
_EXCLUDED_SUFFIXES = frozenset(
    {".o", ".d", ".lst", ".elf", ".bin", ".hex", ".map", ".exe", ".pyc", ".su"}
)


def _SourcePathIncluded_Is(relative: PurePosixPath) -> bool:
    if not relative.parts:
        return False
    if relative.parts[0] in _EXCLUDED_ROOTS:
        return False
    if relative.parts[:2] == ("plugins", "installed"):
        return False
    if "__pycache__" in relative.parts:
        return False
    if relative.parts[0] == "tests" and len(relative.parts) > 1:
        test_root = relative.parts[1]
        if (
            test_root in _EXCLUDED_TEST_ROOTS
            or test_root.startswith("acceptance_")
            or test_root.startswith(".pytest-")
            or test_root.startswith(".probe")
            or test_root.startswith(".startup")
            or test_root.startswith(".vscode-")
            or test_root.startswith(".work")
        ):
            return False
    if relative.suffix.casefold() in _EXCLUDED_SUFFIXES:
        return False
    if relative.suffix.casefold() == ".zip" or relative.name == "main.zip":
        return False
    return True


def SourcePackage_Export(
    workspace_root: Path,
    destination: Path,
    progress_callback: Callable[[int, int, str, bool], None] | None = None,
) -> SourcePackageExportResult:
    source_policy = WorkspacePolicy(workspace_root)
    source_root = source_policy.Path_Resolve(workspace_root, allow_root=True)
    selected_destination = Path(destination).resolve(strict=False)
    if selected_destination.suffix.casefold() != ".zip":
        selected_destination = selected_destination.with_suffix(".zip")
    destination_policy = WorkspacePolicy(selected_destination.parent)
    if selected_destination.is_symlink():
        raise ValueError("Source package destination must not be a symlink")

    files: list[tuple[PurePosixPath, Path]] = []
    for current_text, directory_names, file_names in os.walk(
        source_root, topdown=True, followlinks=False
    ):
        current = Path(current_text)
        retained_directories: list[str] = []
        for directory_name in sorted(directory_names):
            directory = current / directory_name
            relative = PurePosixPath(
                directory.relative_to(source_root).as_posix()
            )
            if not _SourcePathIncluded_Is(relative):
                continue
            if current == source_root / "tests" and directory_name != "fixtures":
                continue
            if directory.is_symlink():
                raise ValueError(
                    f"Source package does not accept symlinks: {relative}"
                )
            retained_directories.append(directory_name)
        directory_names[:] = retained_directories
        for file_name in sorted(file_names):
            source = current / file_name
            if current == source_root / "tests" and source.suffix != ".py":
                continue
            relative = PurePosixPath(source.relative_to(source_root).as_posix())
            if not _SourcePathIncluded_Is(relative):
                continue
            if source.is_symlink():
                raise ValueError(
                    f"Source package does not accept symlinks: {relative}"
                )
            if source.is_file():
                files.append((relative, source))
    files.sort(key=lambda item: item[0].as_posix())

    stream = io.BytesIO()
    source_bytes = 0
    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        total = len(files)
        for current, (relative, source) in enumerate(files, start=1):
            if progress_callback is not None:
                progress_callback(
                    current, total, relative.as_posix(), False
                )
            content = source.read_bytes()
            source_bytes += len(content)
            info = zipfile.ZipInfo(
                filename=f"SilverStar_FCCG/{relative.as_posix()}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
            if progress_callback is not None:
                progress_callback(
                    current, total, relative.as_posix(), True
                )
    payload = stream.getvalue()
    destination_policy.Bytes_AtomicWrite(selected_destination.name, payload)
    return SourcePackageExportResult(
        destination=selected_destination,
        file_count=len(files),
        source_bytes=source_bytes,
        archive_bytes=len(payload),
    )
