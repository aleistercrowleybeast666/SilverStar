"""Conservative repository cleanup. No git clean and no recursive tree deletion."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
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
    {".bin", ".sslog", ".ssdecoder", ".ssflp", ".ssproject", ".zip",
     ".bak", ".tdproj", ".tdrun", ".keystore", ".jks", ".pem", ".key"}
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


@dataclass(frozen=True)
class WorkspaceCleanPlan:
    root: Path
    scope: Path
    records: tuple[dict, ...]
    owner: str
    retained: dict[str, str]

    def __iter__(self):
        return (self.root / record["path"] for record in self.records)

    def __len__(self):
        return len(self.records)


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


def _Scope_Validate(root: Path, scope: Path) -> Path:
    scope = scope.absolute()
    relative = scope.relative_to(root)
    if ".." in relative.parts:
        raise ValueError("cleanup_scope_outside_repository")
    for current in (scope, *scope.parents):
        if _Linked_Check(current):
            raise ValueError("cleanup_scope_is_link")
        if current == root:
            break
        if (current / ".git").exists():
            raise ValueError("cleanup_scope_is_nested_repository")
    return scope.resolve(strict=True)


def _Active_Check(root: Path, path: Path) -> bool:
    for current in (path if path.is_dir() else path.parent, *path.parents):
        if (current / ".cleanup-active").exists():
            return True
        if current == root:
            break
    return False


def _Record_Get(root: Path, path: Path) -> dict:
    info = path.lstat()
    record = {"path": path.relative_to(root).as_posix(),
              "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
              "size": info.st_size if stat.S_ISREG(info.st_mode) else 0,
              "mtime_ns": info.st_mtime_ns, "device": info.st_dev, "inode": info.st_ino}
    if record["kind"] == "file":
        with path.open("rb") as stream:
            record["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        record["children"] = sorted(child.name for child in path.iterdir())
    return record


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


def _Target_Validate(
    root: Path, path: Path, tracked: frozenset[str], scope: Path | None = None
) -> bool:
    try:
        relative = path.relative_to(root)
        scoped = path.relative_to(scope or root)
        parts = tuple(part.casefold() for part in scoped.parts)
        if not parts or any(part in {".git", ".venv", "docs", "fixtures", "golden"}
                            for part in (item.casefold() for item in relative.parts)):
            return False
        if parts[:2] == ("tests", "fixtures") or "golden" in parts:
            return False
        if relative.as_posix().casefold() in tracked:
            return False
        for parent in (path, *path.parents):
            if parent == root:
                break
            if _Linked_Check(parent) or (parent.is_dir() and (parent / ".git").exists()):
                return False
        path.resolve(strict=True).relative_to(root)
        if _Active_Check(root, path):
            return False
        if path.suffix.casefold() in _PROTECTED_SUFFIXES:
            return False
        if path.name.casefold().endswith((
            ".tdmotor.json", ".sstuning.json", ".tdrun.json", ".retldc.json",
        )):
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


def WorkspaceClean_Plan(
    root: Path, scope: Path | None = None, *, owner: str = "reviewed generated workspace"
) -> WorkspaceCleanPlan:
    root = _Root_Validate(root)
    scope = _Scope_Validate(root, scope or root)
    tracked = _Tracked_Get(root)
    targets = []
    directories = []
    retained = {}
    def retain_error(error):
        path = Path(error.filename)
        retained[path.relative_to(root).as_posix()] = f"unreadable: {error}"

    for directory, names, files in os.walk(scope, followlinks=False, onerror=retain_error):
        current = Path(directory)
        if _Active_Check(root, current):
            retained[current.relative_to(root).as_posix()] = "active task"
            names[:] = []
            continue
        accepted = []
        for name in names:
            try:
                if (name.casefold() not in {".git", ".venv", "fixtures", "golden", "docs"}
                        and not _Linked_Check(current / name)
                        and not (current / name / ".git").exists()):
                    accepted.append(name)
            except OSError as error:
                retain_error(error)
        for name in names:
            if name not in accepted:
                retained.setdefault((current / name).relative_to(root).as_posix(), "protected directory or link")
        names[:] = accepted
        for name in files:
            path = current / name
            if _Target_Validate(root, path, tracked, scope):
                targets.append(path)
            else:
                key = path.relative_to(root).as_posix()
                retained[key] = ("tracked" if key.casefold() in tracked else
                                 "active task" if _Active_Check(root, path) else
                                 "input, source, evidence, link or unclassified content")
        if _Target_Validate(root, current, tracked, scope):
            directories.append(current)
    removable = set(targets)
    for directory in sorted(directories, key=lambda path: -len(path.parts)):
        # Include only directories that will be empty after the planned removals.
        if all(child in removable for child in directory.iterdir()):
            targets.append(directory)
            removable.add(directory)
    ordered = sorted(targets, key=lambda path: (-len(path.parts), str(path)))
    return WorkspaceCleanPlan(root, scope, tuple(_Record_Get(root, path) for path in ordered),
                              owner, retained)


def WorkspaceClean_Apply(
    root: Path, targets: WorkspaceCleanPlan
) -> tuple[WorkspaceCleanResult, tuple[Path, ...]]:
    root = _Root_Validate(root)
    # A bare list has no reviewed content/identity snapshot and cannot authorize removal.
    if not isinstance(targets, WorkspaceCleanPlan) or targets.root != root:
        return WorkspaceCleanResult.REFUSED, ()
    try:
        scope = _Scope_Validate(root, targets.scope)
        tracked = _Tracked_Get(root)
        for record, path in zip(targets.records, targets, strict=True):
            if not path.exists() and not path.is_symlink():
                continue  # Reapplying the same verified plan is idempotent.
            if (not _Target_Validate(root, path, tracked, scope)
                    or _Record_Get(root, path) != record):
                return WorkspaceCleanResult.REFUSED, ()
    except (OSError, ValueError):
        return WorkspaceCleanResult.REFUSED, ()
    removed = []
    refused = False
    records_by_path = {record["path"]: record for record in targets.records}
    index_name = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", "index"],
                                check=True, capture_output=True, text=True).stdout.strip()
    index_path = Path(index_name)
    if not index_path.is_absolute():
        index_path = root / index_path
    def index_identity():
        if not index_path.exists():
            return None
        info = index_path.stat()
        return info.st_ino, info.st_size, info.st_mtime_ns

    index_state = index_identity()
    for path in targets:
        if not path.exists() and not path.is_symlink():
            continue
        # Re-read whenever the index identity changes; inspect all path ancestors
        # and the content snapshot immediately before each individual removal.
        current_index = index_identity()
        if current_index != index_state:
            tracked = _Tracked_Get(root)
            index_state = current_index
        if not _Target_Validate(root, path, tracked, scope):
            refused = True
            continue
        try:
            if path.is_dir():
                # rmdir only accepts empty directories: protected descendants always survive.
                if any(path.iterdir()):
                    continue
                path.rmdir()
            else:
                expected = records_by_path[path.relative_to(root).as_posix()]
                if _Record_Get(root, path) != expected:
                    refused = True
                    continue
                path.unlink()
            removed.append(path)
        except OSError:
            refused = True
    return (
        WorkspaceCleanResult.REFUSED if refused else WorkspaceCleanResult.APPLIED,
        tuple(removed),
    )


def WorkspaceClean_PlanSave(plan: WorkspaceCleanPlan, path: Path) -> None:
    document = {"schema": 1, "root": str(plan.root),
                "scope": plan.scope.relative_to(plan.root).as_posix(),
                "owner": plan.owner, "records": plan.records, "retained": plan.retained}
    with path.open("x", encoding="utf8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def WorkspaceClean_PlanLoad(root: Path, path: Path) -> WorkspaceCleanPlan:
    root = _Root_Validate(root)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("cleanup_plan_too_large")
    document = json.loads(path.read_text(encoding="utf8"))
    if (type(document.get("schema")) is not int or document["schema"] != 1
            or Path(document.get("root", "")) != root
            or not isinstance(document.get("owner"), str) or not document["owner"].strip()):
        raise ValueError("cleanup_plan_identity_invalid")
    scope = _Scope_Validate(root, root / document["scope"])
    records = document["records"]
    if not isinstance(records, list) or len(records) > 200000:
        raise ValueError("cleanup_plan_records_invalid")
    paths = set()
    for record in records:
        path = Path(record["path"])
        if path.is_absolute() or path.drive or ".." in path.parts or path in paths:
            raise ValueError("cleanup_plan_path_invalid")
        (root / path).relative_to(scope)
        paths.add(path)
    return WorkspaceCleanPlan(root, scope, tuple(records), document["owner"], document["retained"])


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
    mode.add_argument("--apply", type=Path, metavar="PLAN", help="apply this previously reviewed plan")
    parser.add_argument("--plan", type=Path, help="save the preview for review; never overwritten")
    parser.add_argument("--scope", help="repository-relative cleanup scope; default apps/FLP")
    parser.add_argument("--owner", default="FLP generated workspace", help="candidate owner/purpose")
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    actual = subprocess.run(["git", "-C", str(app), "rev-parse", "--show-toplevel"],
                            check=True, capture_output=True, text=True).stdout.strip()
    root = _Root_Validate(Path(actual))
    targets = (WorkspaceClean_PlanLoad(root, args.apply) if args.apply else
               WorkspaceClean_Plan(root, root / args.scope if args.scope else app, owner=args.owner))
    if args.apply:
        result, removed = WorkspaceClean_Apply(root, targets)
        for path in removed:
            print(f"REMOVED {path.relative_to(root)}")
        print(f"{result.value}: {len(removed)} paths removed; tracked/protected files preserved")
        return int(result == WorkspaceCleanResult.REFUSED)
    if args.plan:
        WorkspaceClean_PlanSave(targets, args.plan)
    for record in targets.records:
        print(f"CANDIDATE {record['kind']} {record['size']}B {record['path']} owner={targets.owner}")
    for path, reason in targets.retained.items():
        print(f"KEEP {path}: {reason}")
    print(f"Dry run: {len(targets)} candidates; directories removed only when empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(WorkspaceClean_Main())
