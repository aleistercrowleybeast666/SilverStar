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
             progress: Callable[[int, int, str], None] = lambda *_: None, byte_progress=None) -> Path:
        if cut:
            raise ValueError('Device exports are copy-only; clean source files manually')
        from services.transfer_progress import TransferProgress
        notify = byte_progress or (lambda _:None)
        self._check()
        if not self.sources or len(self.sources) > 1024:
            raise ValueError("Select between 1 and 1024 files")
        destination = _regular_path(self.destination, directory=True)
        paths = [_regular_path(Path(path)) for path in self.sources]
        if len(set(paths)) != len(paths) or len({p.name.casefold() for p in paths}) != len(paths):
            raise ValueError("Duplicate source paths or filenames")
        for source in paths:
            self._check(source)
        self.output = destination / ("SilverStar_export_" + time.strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:12])
        self.output.mkdir(exist_ok=False)
        total = sum(path.stat().st_size for path in paths)
        received = 0
        for index, source in enumerate(paths):
            self._check(source)
            before = _identity(source)
            filename = source.name if re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", source.name) and source.name != "manifest.json" else f"file_{index:04d}.bin"
            target = self.output / filename
            digest = hashlib.sha256()
            notify(TransferProgress(received,total,'receiving',index+1,len(paths),source.name))
            with source.open("rb") as src, target.open("xb") as dst:
                while data := src.read(self.CHUNK_BYTES):
                    self._check(source)
                    if dst.write(data)!=len(data):raise OSError('Incomplete destination write')
                    digest.update(data)
                    received += len(data)
                    notify(TransferProgress(received,total,'receiving',index+1,len(paths),source.name))
                notify(TransferProgress(received,total,'verifying',index+1,len(paths),source.name))
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
            if fp.write(encoded)!=len(encoded):raise OSError('Incomplete manifest write')
            fp.flush()
            os.fsync(fp.fileno())
        self._check()
        self.manifest_sha256 = hashlib.sha256(encoded).hexdigest()
        if self._hash(self.output / "manifest.json") != self.manifest_sha256:
            raise OSError("Manifest readback failed")
        self.ready = True
        notify(TransferProgress(received,total,'verified',len(paths),len(paths),'manifest'))
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
        """Compatibility operation: source deletion is no longer provided."""
        if not confirmed:
            return DeviceExportResult.COPIED
        raise ValueError('Device exports are copy-only; clean source files manually')


__all__ = ["DeviceExport", "DeviceExportResult", "ExportCancelled"]
