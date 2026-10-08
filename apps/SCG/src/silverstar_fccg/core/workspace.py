from __future__ import annotations

import os
import shutil
import secrets
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from silverstar_fccg.core.errors import FccgError


class WorkspacePolicyError(FccgError):
    """Raised when a filesystem operation would escape an authorized root."""


def PortableRelativePath_Validate(value: str) -> PurePosixPath:
    """Validate a portable project-relative path without filesystem state."""

    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise WorkspacePolicyError(f"Invalid portable relative path: {value!r}")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise WorkspacePolicyError(f"Unsafe portable relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise WorkspacePolicyError(f"Unsafe portable relative path: {value!r}")
    windows_reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    for part in path.parts:
        if ":" in part or part.endswith((" ", ".")):
            raise WorkspacePolicyError(
                f"Non-portable path segment is not allowed: {value!r}"
            )
        base_name = part.split(".", 1)[0].upper()
        if base_name in windows_reserved:
            raise WorkspacePolicyError(
                f"Windows reserved path segment is not allowed: {value!r}"
            )
    return path


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    root: Path

    def __post_init__(self) -> None:
        resolved = self.root.resolve()
        if resolved == Path(resolved.anchor):
            raise WorkspacePolicyError("A filesystem root cannot be an authorized workspace")
        object.__setattr__(self, "root", resolved)

    def Path_Resolve(self, path: str | Path, *, allow_root: bool = True) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as error:
            raise WorkspacePolicyError(
                f"Path escapes authorized workspace: {resolved}"
            ) from error
        if not allow_root and relative == Path("."):
            raise WorkspacePolicyError("The workspace root is not a valid operation target")
        return resolved

    def RelativePath_Validate(self, value: str) -> PurePosixPath:
        return PortableRelativePath_Validate(value)

    def Directory_Ensure(self, path: str | Path) -> Path:
        resolved = self.Path_Resolve(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def StagingDirectory_Create(self, prefix: str = "fccg-") -> Path:
        # A prefix is one portable segment, never a path into another root.
        if len(PortableRelativePath_Validate(prefix + "stage").parts) != 1:
            raise WorkspacePolicyError("Staging prefix must be one path segment")
        staging_root = self.Directory_Ensure(".staging")
        if os.name == "nt":
            # Python 3.13+ mkdtemp uses mode0700 on Windows, replacing inherited
            # access with a restricted ACL. Create with normal parent inheritance
            # from the outset; never repair permissions using an external command.
            for _attempt in range(16):
                staging = self.Path_Resolve(
                    staging_root / (prefix + secrets.token_hex(8)), allow_root=False
                )
                try:
                    staging.mkdir()
                except FileExistsError:
                    continue
                return staging
            raise WorkspacePolicyError("Could not create a unique staging directory")
        return self.Path_Resolve(tempfile.mkdtemp(prefix=prefix, dir=staging_root))

    def Text_AtomicWrite(self, path: str | Path, text: str) -> Path:
        target = self.Path_Resolve(path, allow_root=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            self.Path_Replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def Bytes_AtomicWrite(self, path: str | Path, content: bytes) -> Path:
        target = self.Path_Resolve(path, allow_root=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.Path_Replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def File_Copy(self, source: Path, destination: str | Path) -> Path:
        if source.is_symlink() or not source.is_file():
            raise WorkspacePolicyError(f"Only regular files may be copied: {source}")
        target = self.Path_Resolve(destination, allow_root=False)
        # Generation and downstream ARM tools use ordinary Windows paths.
        # Reject their legacy API boundary before mkdir/copy instead of a
        # misleading missing-file error or a partial extended-path workaround.
        if os.name == "nt" and (len(str(source)) >= 260 or
                                len(str(target)) >= 260 or
                                len(str(target.parent)) >= 248):
            raise WorkspacePolicyError(
                "WINDOWS_PATH_TOO_LONG: shorten the workspace/project root; "
                "copied file paths must be under 260 characters and parent "
                f"directories under 248 characters: {target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def Path_Replace(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        attempts: int = 5,
    ) -> Path:
        """Atomically replace one validated path, tolerating short Windows locks."""
        if attempts < 1:
            raise ValueError("Path replacement attempts must be positive")
        source_path = self.Path_Resolve(source, allow_root=False)
        destination_path = self.Path_Resolve(destination, allow_root=False)
        last_error: OSError | None = None
        for attempt in range(attempts):
            try:
                os.replace(source_path, destination_path)
                return destination_path
            except OSError as error:
                last_error = error
                if attempt + 1 == attempts:
                    raise
                time.sleep(0.1 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def Tree_Remove(self, path: str | Path) -> None:
        target = self.Path_Resolve(path, allow_root=False)
        if target.is_symlink() or target.is_file():
            target.unlink(missing_ok=True)
        elif target.exists():
            shutil.rmtree(target)


def PortablePath_Normalize(value: str) -> str:
    """Return a validated, slash-separated project path."""

    return PortableRelativePath_Validate(value).as_posix()
