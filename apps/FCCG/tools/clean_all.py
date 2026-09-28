from __future__ import annotations

import argparse
import os
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path


def _WorkspaceRoot_Get() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file() or not (root / ".git").exists():
        raise RuntimeError(f"Refusing to clean an unverified FCCG workspace: {root}")
    return root


def _InsideWorkspace_Validate(root: Path, target: Path) -> Path:
    resolved = target.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Cleanup target escapes the workspace: {resolved}") from error
    if relative == Path("."):
        raise RuntimeError("Cleanup must never target the workspace root")
    return resolved


def _Targets_Get(root: Path) -> tuple[Path, ...]:
    tests = root / "tests"
    targets = [
        root / "build",
        root / ".pytest_cache",
        root / ".staging",
        tests / ".tmp",
        tests / ".pytest-work",
        tests / ".pytest-cache",
        tests / "artifacts",
        tests / "generated_projects",
        tests / "reference_copy",
    ]
    if tests.is_dir():
        prefixes = (
            "acceptance_",
            "tmp",
            ".cache-",
            ".inspect",
            ".pycache-",
            ".pytest-",
            ".probe",
            ".startup",
            ".tmp-",
            ".vscode-",
            ".work",
            ".w",
            ".c",
        )
        targets.extend(
            child
            for child in tests.iterdir()
            if child.name.startswith(prefixes)
        )
    initial_keys = {
        str(_InsideWorkspace_Validate(root, target)).casefold()
        for target in targets
    }
    for current, directories, _files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        retained_directories: list[str] = []
        for directory in directories:
            child = current_path / directory
            if directory == "__pycache__":
                targets.append(child)
                continue
            if str(child.resolve(strict=False)).casefold() in initial_keys:
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories
    unique = {
        str(_InsideWorkspace_Validate(root, target)).casefold(): target
        for target in targets
    }
    return tuple(
        sorted(unique.values(), key=lambda path: (len(path.parts), str(path)), reverse=True)
    )


def _Size_Get(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    if not path.is_dir():
        return 0
    return sum(
        child.lstat().st_size
        for child in path.rglob("*")
        if child.is_file() or child.is_symlink()
    )


def _RemoveError_Handle(
    function: Callable[[str], object], path: str, _exception_info: object
) -> None:
    """Retry a Windows removal after clearing a read-only attribute."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass
    function(path)


def _Path_Remove(path: Path) -> None:
    """Remove one validated target, tolerating short Windows filesystem races."""
    last_error: OSError | None = None
    for attempt in range(5):
        if not path.exists() and not path.is_symlink():
            return
        try:
            if path.is_symlink() or path.is_file():
                try:
                    path.chmod(stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
                path.unlink()
            else:
                shutil.rmtree(path, onerror=_RemoveError_Handle)
            return
        except OSError as error:
            last_error = error
            if attempt < 4:
                time.sleep(0.1 * (attempt + 1))
    assert last_error is not None
    raise last_error


def WorkspaceArtifacts_Clean(
    *, dry_run: bool = False, measure_bytes: bool = False
) -> tuple[int, int]:
    root = _WorkspaceRoot_Get()
    removed_count = 0
    removed_bytes = 0
    failures: list[tuple[Path, OSError]] = []
    for candidate in _Targets_Get(root):
        target = _InsideWorkspace_Validate(root, candidate)
        if not target.exists() and not target.is_symlink():
            continue
        size = _Size_Get(target) if measure_bytes else 0
        size_text = f"{size} bytes" if measure_bytes else "size not measured"
        print(f"{'WOULD REMOVE' if dry_run else 'REMOVE'} {target} ({size_text})")
        if dry_run:
            removed_count += 1
            removed_bytes += size
            continue
        try:
            _Path_Remove(target)
        except OSError as error:
            failures.append((target, error))
            print(f"FAILED {target}: {error}")
            continue
        removed_count += 1
        removed_bytes += size
    if failures:
        details = "; ".join(f"{path}: {error}" for path, error in failures)
        raise RuntimeError(f"Cleanup left {len(failures)} target(s): {details}")
    return removed_count, removed_bytes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely clean FCCG build and test artifacts inside this workspace."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--measure-bytes", action="store_true")
    arguments = parser.parse_args()
    count, size = WorkspaceArtifacts_Clean(
        dry_run=arguments.dry_run,
        measure_bytes=arguments.measure_bytes,
    )
    print(
        f"cleanup targets={count} bytes={size} dry_run={arguments.dry_run} "
        f"measured={arguments.measure_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
