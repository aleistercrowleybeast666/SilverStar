"""Conservative repository cleanup. No git clean and no recursive tree deletion."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
from enum import StrEnum
from pathlib import Path

_CACHE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})
_GENERATED_ROOTS = frozenset({"build", "dist", ".acceptance"})
_TEST_WORKSPACE_PREFIXES = (".tmp_", ".pytest", ".integrity-")
_TEST_WORKSPACE_SUFFIXES = ("_temp", "_cache")
_PROTECTED_SUFFIXES = frozenset(
    {".bin", ".sslog", ".ssdecoder", ".ssflp", ".ssproject", ".zip"}
)
_GENERATED_SUFFIXES = frozenset(
    {
        ".pyc",
        ".pyo",
        ".png",
        ".gif",
        ".csv",
        ".json",
        ".txt",
        ".html",
        ".log",
        ".toc",
        ".pkg",
        ".pyz",
        ".zip",
        ".exe",
        ".dll",
        ".pyd",
        ".manifest",
        ".ico",
    }
)


class WorkspaceCleanResult(StrEnum):
    APPLIED = "applied"
    REFUSED = "refused"


def _Linked_Check(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _Root_Validate(root: Path) -> Path:
    root = root.absolute()
    if _Linked_Check(root):
        raise ValueError("cleanup_root_is_link")
    root = root.resolve(strict=True)
    actual = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if Path(actual).resolve() != root:
        raise ValueError("cleanup_requires_repository_root")
    return root


def _Generated_Check(parts: tuple[str, ...]) -> bool:
    if not parts:
        return False
    if parts[0] in _GENERATED_ROOTS or parts[0].startswith(
        (".codex_pytest_", ".codex_container_stage_")
    ):
        return True
    if parts[0] != "tests" or len(parts) < 2:
        return False
    if parts[1].startswith(_TEST_WORKSPACE_PREFIXES):
        return True
    return any(part.endswith(_TEST_WORKSPACE_SUFFIXES) for part in parts[1:])


def _Evidence_Preserve(parts: tuple[str, ...], path: Path) -> bool:
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    if suffix in {".sha256", ".sha256sum", ".md5"} or "manifest" in name:
        return True
    if name in {"summary.json", "evidence.json", "final.json"}:
        return True
    if suffix == ".log" and (name.startswith("final") or "_final" in name):
        return True
    if suffix in {".png", ".jpg", ".jpeg"} and (
        "screenshot" in name
        or (
            parts[0] == ".acceptance"
            and len(parts) > 1
            and parts[1] in {"dialogs_gui", "parameters25"}
        )
    ):
        return True
    # Acceptance JSON/log summaries and finished replay GIFs remain review evidence.
    return parts[0] == ".acceptance" and suffix in {".json", ".log", ".gif"}


def _Tracked_Get(root: Path) -> frozenset[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached"], check=True, capture_output=True
    )
    return frozenset(
        os.fsdecode(name).replace("\\", "/").casefold()
        for name in result.stdout.split(b"\0")
        if name
    )


def _Target_Validate(root: Path, path: Path, tracked: frozenset[str]) -> bool:
    try:
        relative = path.relative_to(root)
        parts = tuple(part.casefold() for part in relative.parts)
        if not parts or parts[0] in {".git", ".venv", "docs"}:
            return False
        if parts[:2] == ("tests", "fixtures") or "golden" in parts:
            return False
        if relative.as_posix().casefold() in tracked:
            return False
        for parent in (path, *path.parents):
            if parent == root:
                break
            if _Linked_Check(parent):
                return False
        path.resolve(strict=True).relative_to(root)
        if path.suffix.casefold() in _PROTECTED_SUFFIXES:
            return False
        if path.is_file() and _Evidence_Preserve(parts, path):
            return False
        cache = any(part in _CACHE_NAMES for part in parts)
        generated = _Generated_Check(parts)
        if path.is_dir():
            return cache or generated
        if not path.is_file():
            return False
        if path.suffix.casefold() in {".pyc", ".pyo"}:
            return True
        # Cache internals have documented names, including extensionless hash files.
        if cache:
            return path.suffix.casefold() not in {".py", ".c", ".h"}
        return generated and path.suffix.casefold() in _GENERATED_SUFFIXES
    except (OSError, ValueError):
        return False


def WorkspaceClean_Plan(root: Path) -> tuple[Path, ...]:
    root = _Root_Validate(root)
    tracked = _Tracked_Get(root)
    targets = []
    directories = []
    for directory, names, files in os.walk(root, followlinks=False):
        current = Path(directory)
        names[:] = [
            name
            for name in names
            if name.casefold() not in {".git", ".venv", "fixtures", "golden", "docs"}
            and not _Linked_Check(current / name)
        ]
        for name in files:
            path = current / name
            if _Target_Validate(root, path, tracked):
                targets.append(path)
        if _Target_Validate(root, current, tracked):
            directories.append(current)
    removable = set(targets)
    for directory in sorted(directories, key=lambda path: -len(path.parts)):
        # Include only directories that will be empty after the planned removals.
        if all(child in removable for child in directory.iterdir()):
            targets.append(directory)
            removable.add(directory)
    return tuple(sorted(targets, key=lambda path: (-len(path.parts), str(path))))


def WorkspaceClean_Apply(
    root: Path, targets: tuple[Path, ...]
) -> tuple[WorkspaceCleanResult, tuple[Path, ...]]:
    root = _Root_Validate(root)
    removed = []
    refused = False
    for path in targets:
        # Re-read the index and inspect every ancestor immediately before each removal.
        if not _Target_Validate(root, path, _Tracked_Get(root)):
            refused = True
            continue
        try:
            if path.is_dir():
                # rmdir only accepts empty directories: protected descendants always survive.
                if any(path.iterdir()):
                    continue
                path.rmdir()
            else:
                path.unlink()
            removed.append(path)
        except OSError:
            refused = True
    return (
        WorkspaceCleanResult.REFUSED if refused else WorkspaceCleanResult.APPLIED,
        tuple(removed),
    )


def WorkspaceClean_RetireTests(
    root: Path, names: tuple[str, ...]
) -> tuple[WorkspaceCleanResult, int]:
    """Explicitly retire user-authorized historical test runs, including tracked outputs.

    Unlike ordinary cleanup, this is a source-tree change reviewable in git diff.
    Never follows links; a linked descendant refuses the entire run directory.
    """
    root = _Root_Validate(root)
    removed = 0
    for name in names:
        if Path(name).name != name or not name.startswith(
            (".codex_pytest_", ".codex_container_stage_")
        ):
            return WorkspaceCleanResult.REFUSED, removed
        target = root / name
        if _Linked_Check(target) or target.resolve().parent != root:
            return WorkspaceCleanResult.REFUSED, removed
        paths = []
        for directory, directories, files in os.walk(target, followlinks=False):
            for child in (*directories, *files):
                path = Path(directory) / child
                if _Linked_Check(path):
                    return WorkspaceCleanResult.REFUSED, removed
                path.resolve(strict=True).relative_to(target.resolve(strict=True))
                paths.append(path)
        for path in sorted(paths, key=lambda item: -len(item.parts)):
            # Recheck ancestors at the point of deletion; no recursive removal.
            for ancestor in (path, *path.parents):
                if ancestor == root:
                    break
                if _Linked_Check(ancestor):
                    return WorkspaceCleanResult.REFUSED, removed
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()
            removed += 1
        target.rmdir()
        removed += 1
    return WorkspaceCleanResult.APPLIED, removed


def WorkspaceClean_Main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print candidates (default)")
    mode.add_argument("--apply", action="store_true", help="remove verified generated files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    targets = WorkspaceClean_Plan(root)
    if args.apply:
        result, removed = WorkspaceClean_Apply(root, targets)
        for path in removed:
            print(f"REMOVED {path.relative_to(root)}")
        print(f"{result.value}: {len(removed)} paths removed; tracked/protected files preserved")
        return int(result == WorkspaceCleanResult.REFUSED)
    for path in targets:
        print(f"CANDIDATE {path.relative_to(root)}")
    print(f"Dry run: {len(targets)} candidates; directories removed only when empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(WorkspaceClean_Main())
