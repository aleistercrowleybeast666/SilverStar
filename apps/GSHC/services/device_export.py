"""Verified exports to filesystem destinations; MTP is not a filesystem adapter."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event
from uuid import uuid4


class DeviceExportResult(str, Enum):
    COPIED = "copied"
    CUT = "cut"
    CANCELLED = "cancelled"


class ExportCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ExportFile:
    source: Path
    target: Path
    size: int
    sha256: str
    identity: tuple[int, int, int, int]


def _regular_path(path: Path, *, directory: bool = False) -> Path:
    """Reject symlinks/junctions before resolving, including their ancestors."""
    path = path.expanduser().absolute()
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Reparse/symbolic paths are unsupported: {part}")
    if directory and not path.is_dir() or not directory and not path.is_file():
        raise ValueError(f"Not a {'directory' if directory else 'regular file'}: {path}")
    return path.resolve(strict=True)


def _identity(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class DeviceExport:
    CHUNK_BYTES = 1024 * 1024

    def __init__(self, sources: list[Path], destination: Path, *, managed_root: Path,
                 is_active: Callable[[Path], bool], cancel: Event | None = None,
                 app_version: str = "unknown") -> None:
        self.sources = sources
        self.destination = destination
        self.managed_root = managed_root
        self.is_active = is_active
        self.cancel = cancel or Event()
        self.app_version = app_version
        self.output: Path | None = None
        self.files: list[ExportFile] = []
        self.manifest_sha256: str | None = None
        self.ready = False
        self.cut_requested = False

    def _check(self, path: Path | None = None) -> None:
        if self.cancel.is_set():
            raise ExportCancelled("Cancelled; source files retained")
        if path is not None and self.is_active(path):
            raise ValueError(f"Active log cannot be exported: {path}")

    def _hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while data := stream.read(self.CHUNK_BYTES):
                self._check()
                digest.update(data)
        return digest.hexdigest()

    def copy(self, *, cut: bool = False,
             progress: Callable[[int, int, str], None] = lambda *_: None) -> Path:
        self._check()
        if not self.sources or len(self.sources) > 1024:
            raise ValueError("Select between 1 and 1024 files")
        if cut and len(self.sources) != 1:
            raise ValueError("Cut exports one closed managed session at a time; use copy for a batch")
        self.cut_requested = cut
        destination = _regular_path(self.destination, directory=True)
        root = _regular_path(self.managed_root, directory=True)
        paths = [_regular_path(Path(path)) for path in self.sources]
        if len(set(paths)) != len(paths) or len({p.name.casefold() for p in paths}) != len(paths):
            raise ValueError("Duplicate source paths or filenames")
        for source in paths:
            self._check(source)
            if cut and (source.parent != root or not source.name.startswith("fc_session_")
                        or source.suffix != ".jsonl"):
                raise ValueError("Cut supports only closed managed fc_session JSONL logs")
        self.output = destination / ("SilverStar_export_" + time.strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:12])
        self.output.mkdir(exist_ok=False)
        for index, source in enumerate(paths):
            self._check(source)
            before = _identity(source)
            filename = source.name if re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", source.name) and source.name != "manifest.json" else f"file_{index:04d}.bin"
            target = self.output / filename
            digest = hashlib.sha256()
            with source.open("rb") as src, target.open("xb") as dst:
                while data := src.read(self.CHUNK_BYTES):
                    self._check(source)
                    dst.write(data)
                    digest.update(data)
                dst.flush()
                os.fsync(dst.fileno())
            self._check(source)
            if before != _identity(source) or self._hash(target) != digest.hexdigest():
                raise OSError(f"Source changed or destination readback failed: {source}")
            self.files.append(ExportFile(source, target, before[2], digest.hexdigest(), before))
            progress(index + 1, len(paths), source.name)
        manifest = {"format": "silverstar.session-export", "schema_version": 1,
                    "session_id": self.output.name, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source_app": {"name": "SilverStar GSHC", "version": self.app_version},
                    "protocols": {}, "files": [
                        {"path": f.target.name, **self._format(f.source), "size_bytes": f.size, "sha256": f.sha256}
                        for f in self.files]}
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        with (self.output / "manifest.json").open("xb") as fp:
            fp.write(encoded)
            fp.flush()
            os.fsync(fp.fileno())
        self._check()
        self.manifest_sha256 = hashlib.sha256(encoded).hexdigest()
        if self._hash(self.output / "manifest.json") != self.manifest_sha256:
            raise OSError("Manifest readback failed")
        self.ready = True
        return self.output

    @staticmethod
    def _format(source: Path) -> dict[str, str]:
        with source.open("rb") as fp:
            header = fp.read(64)
        if (len(header) == 64 and header[:8] == b"SSLOG0\x00\x00"
                and struct.unpack_from("<HHH", header, 8) == (0, 64, 24)
                and struct.unpack_from("<H", header, 44)[0] == 4
                and zlib.crc32(header[:60]) == struct.unpack_from("<I", header, 60)[0]):
            return {"role": "flight_log", "format": "SSLOG", "format_version": "0.0"}
        if source.suffix.lower() == ".jsonl":
            version = "legacy-unversioned"
            with source.open("rb") as fp:
                first = fp.readline(65537)
            try:
                record = json.loads(first) if len(first) <= 65536 else {}
                if isinstance(record, dict) and record.get("kind") == "SESSION_START" and record.get("log_format") == "silverstar.gshc-jsonl" and record.get("log_format_version") == 1:
                    version = "1"
            except (ValueError, UnicodeError):
                pass
            return {"role": "session_log", "format": "silverstar.gshc-jsonl", "format_version": version}
        return {"role": "attachment", "format": "opaque", "format_version": "unknown"}

    def delete_verified_sources(self, *, confirmed: bool) -> DeviceExportResult:
        """Call only after a GUI confirmation of this exact completed copy."""
        if not confirmed:
            return DeviceExportResult.COPIED
        if not self.cut_requested or len(self.sources) != 1:
            raise ValueError("Deletion requires a single-session cut export")
        if not self.ready or not self.files or len(self.files) != len(self.sources):
            raise ValueError("Export is incomplete")
        root = _regular_path(self.managed_root, directory=True)
        for item in self.files:
            self._verify_for_delete(item, root)
        # Preflight all files before deleting any; every destructive step repeats
        # the check. A later disk failure can leave a partially completed cut;
        # its verified destination remains intact and remaining sources survive.
        for item in self.files:
            self._verify_for_delete(item, root)
            self._check(item.source)
            item.source.unlink()
        return DeviceExportResult.CUT

    def _verify_for_delete(self, item: ExportFile, root: Path) -> None:
        self._check(item.source)
        if self.output is None:
            raise ValueError("Export is incomplete")
        if {path.name for path in self.output.iterdir()} != {"manifest.json", *(f.target.name for f in self.files)}:
            raise OSError("Deletion refused: undeclared export contents")
        _regular_path(self.output / "manifest.json")
        if self._hash(self.output / "manifest.json") != self.manifest_sha256:
            raise OSError("Deletion refused: export manifest changed")
        source = _regular_path(item.source)
        _regular_path(item.target)
        if (source.parent != root or not source.name.startswith("fc_session_")
                or source.suffix != ".jsonl" or _identity(source) != item.identity
                or self._hash(source) != item.sha256 or self._hash(item.target) != item.sha256):
            raise OSError(f"Deletion refused: source/destination identity changed: {source}")


__all__ = ["DeviceExport", "DeviceExportResult", "ExportCancelled"]
