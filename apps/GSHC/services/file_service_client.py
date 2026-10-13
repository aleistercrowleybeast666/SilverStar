"""LOGFILE v1 maintenance client. No AIR/GSP binding and no implicit delete.

CRC tokens detect changes; firmware v1 has no device/boot identity. Unknown
identity always starts a new read-only download and never permits remote delete.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event
from typing import Protocol
from uuid import uuid4

from services.device_export import ExportCancelled, _regular_path

_logger = logging.getLogger(__name__)


def validate_download_directory(destination: Path) -> Path:
    root = _regular_path(destination, directory=True)
    probe = root / (".gshc_writeprobe_" + uuid4().hex)
    created = False
    payload = b"GSHC download destination probe\n"
    try:
        with probe.open("xb") as fp:
            created = True
            if fp.write(payload) != len(payload):
                raise OSError("Incomplete destination write probe")
            fp.flush()
            os.fsync(fp.fileno())
    finally:
        if created:
            probe.unlink()
    return root


def _download_checkpoint(path: Path, metadata: dict) -> None:
    encoded = json.dumps(metadata, indent=2).encode("utf-8")
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as fp:
            if fp.write(encoded) != len(encoded):
                raise OSError("Incomplete download metadata write")
            fp.flush()
            os.fsync(fp.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


class FileServiceResult(str, Enum):
    UNSUPPORTED = "UNSUPPORTED"
    BAD_RESPONSE = "BAD_RESPONSE"
    BUSY = "BUSY"
    STALE = "STALE"
    IO_ERROR = "IO_ERROR"


class FileServiceError(RuntimeError):
    def __init__(self, result: FileServiceResult, detail: str) -> None:
        self.result = result
        super().__init__(detail)


class LineTransport(Protocol):
    def exchange(self, command: str, timeout: float, cancel: Event) -> str: ...


@dataclass(frozen=True)
class RemoteLog:
    file_id: int
    token: str
    size: int
    crc32: int
    format_version: str = "0.0"


@dataclass(frozen=True)
class FirmwareSnapshot:
    firmware: str
    received_ns: int
    sequence: int
    age_ms: int
    lifecycle: int
    storage_valid: bool
    mounted: bool
    healthy: bool
    writer_open: bool
    log_fault: bool
    finalization: int
    maintenance: int
    cleanup_pending: bool
    reboot_required: bool


def _uint(fields: dict[str, str], key: str, maximum: int = 0xFFFFFFFF) -> int:
    value = fields.get(key, "")
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) > maximum:
        raise FileServiceError(FileServiceResult.BAD_RESPONSE, f"Invalid {key}")
    return int(value)


def _crc(text: str) -> int:
    if not re.fullmatch(r"[0-9A-F]{8}", text):
        raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid CRC32")
    return int(text, 16)


class FileServiceClient:
    def __init__(self, transport: LineTransport, *, cancel: Event | None = None,
                 timeout: float = 2.0) -> None:
        self.transport = transport
        self.cancel = cancel or Event()
        self.timeout = max(0.1, min(30.0, timeout))
        self.capabilities: dict[str, str] | None = None
        self._delete_selection: RemoteLog | None = None
        self.last_cancel_error = ""

    def _check(self) -> None:
        if self.cancel.is_set():
            raise ExportCancelled("Download cancelled; source remains on device")

    def _request(self, op: str, args: str = "") -> dict[str, str]:
        self._check()
        command = "LOGFILE " + op + (" " + args if args else "")
        request_id: int | None = None
        pending_count = 0
        while True:
            self._check()
            # Timeout applies to each response, not the whole storage operation:
            # large META hashes may legitimately remain PENDING for minutes.
            line = self.transport.exchange(command, self.timeout, self.cancel).strip()
            if len(line) > 511 or not line.isascii():
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Oversized/non-ASCII response")
            parts = line.split()
            if len(parts) < 3 or parts[1:3] != ["LOGFILE", op]:
                result = FileServiceResult.UNSUPPORTED if op == "CAPS" else FileServiceResult.BAD_RESPONSE
                raise FileServiceError(result, "Unexpected LOGFILE response: " + line[:120])
            fields: dict[str, str] = {}
            for pair in parts[3:]:
                key, separator, value = pair.partition("=")
                if not separator or not key or not value or key in fields:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Malformed response fields")
                fields[key] = value
            if parts[0] == "ERR":
                code = fields.get("code", "IO_ERROR")
                if code in {"UNSUPPORTED", "BAD_MODULE", "BAD_COMMAND"}:
                    raise FileServiceError(FileServiceResult.UNSUPPORTED, f"Device does not support {op}: {code}")
                raise FileServiceError(FileServiceResult.BUSY if code in {"BUSY", "LOCKED", "NOT_READY"}
                                       else FileServiceResult.STALE if code == "STALE" else FileServiceResult.IO_ERROR,
                                       f"Device rejected {op}: {code}")
            if op not in {"CAPS", "CANCEL", "STATUS", "ENTER"}:
                if request_id is None and parts[0] != "PENDING":
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Missing submission PENDING acknowledgement")
                response_id = _uint(fields, "request_id")
                if response_id == 0 or request_id is not None and response_id != request_id:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Stale request_id")
                request_id = response_id
            if parts[0] == "OK":
                return fields
            if parts[0] != "PENDING" or request_id is None:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Unexpected response status")
            if self.cancel.wait(min(0.05, pending_count * 0.005)):
                self._check()
            pending_count += 1
            command = f"LOGFILE POLL {request_id}"

    def negotiate(self) -> dict[str, str]:
        self._delete_selection = None
        fields = self._request("CAPS")
        if (fields.get("file_service_version") != "1" or fields.get("supported") != "1"
                or fields.get("max_chunk") != "64" or fields.get("telemetry_bulk") != "0"
                or not fields.get("device_id") or not fields.get("boot_id")):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Unsupported LOGFILE capabilities")
        self.capabilities = fields
        return fields

    def status(self) -> FirmwareSnapshot:
        caps = self.capabilities if self.capabilities is not None else self.negotiate()
        if caps.get("status_version") != "1":
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Firmware RAM status unsupported")
        fields = self._request("STATUS")
        if fields.get("status_version") != "1" or fields.get("source") != "FC_DEBUG_RAM":
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Unknown status version/source")
        return FirmwareSnapshot(
            caps.get("firmware", "unknown"), time.monotonic_ns(),
            _uint(fields, "sequence"), _uint(fields, "age_ms"), _uint(fields, "lifecycle", 8),
            bool(_uint(fields, "storage_valid", 1)), bool(_uint(fields, "mounted", 1)),
            bool(_uint(fields, "healthy", 1)), bool(_uint(fields, "writer_open", 1)),
            bool(_uint(fields, "log_fault", 1)), _uint(fields, "finalization", 3),
            _uint(fields, "maintenance", 3), bool(_uint(fields, "cleanup_pending", 1)),
            bool(_uint(fields, "reboot_required", 1)))

    def enter_maintenance(self) -> None:
        caps = self.capabilities if self.capabilities is not None else self.negotiate()
        if caps.get("maintenance_required") != "1" or caps.get("status_version") != "1":
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Firmware has no explicit maintenance/START exclusion")
        reply = self._request("ENTER")
        if reply.get("accepted") != "1" or reply.get("reboot_required") != "1":
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid maintenance acknowledgement")
        # An accepted reservation is not a closed writer. Wait for owner evidence.
        while True:
            snapshot = self.status()
            if snapshot.maintenance == 3:
                raise FileServiceError(FileServiceResult.IO_ERROR, "Maintenance finalization failed; restart required")
            if snapshot.maintenance == 2:
                if (snapshot.age_ms > 3000 or not snapshot.storage_valid or not snapshot.mounted
                        or not snapshot.healthy or snapshot.writer_open or snapshot.log_fault
                        or snapshot.finalization != 3 or snapshot.cleanup_pending):
                    raise FileServiceError(FileServiceResult.BUSY, "Maintenance snapshot is not safe/fresh for reads")
                return
            if snapshot.maintenance != 1:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Maintenance reservation lost")
            if self.cancel.wait(0.1):
                self._check()

    def list_closed(self) -> list[int]:
        if self.capabilities is None:
            self.negotiate()
        result: list[int] = []
        seen_cursors = {0}
        cursor = 0
        for _ in range(1025):
            fields = self._request("LIST", str(cursor))
            end = _uint(fields, "end", 1)
            cursor = _uint(fields, "next_cursor")
            if end:
                if cursor != 0:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid list end")
                return result
            file_id = _uint(fields, "file_id", 999999)
            _uint(fields, "size")
            if fields.get("closed") != "1" or file_id < 1 or file_id in result or cursor in seen_cursors:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid/active/duplicate list entry")
            seen_cursors.add(cursor)
            result.append(file_id)
        raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Log listing exceeds 1024 entries")

    def metadata(self, file_id: int) -> RemoteLog:
        if not 1 <= file_id <= 999999:
            raise ValueError("Invalid mission file ID")
        fields = self._request("META", str(file_id))
        size = _uint(fields, "size")
        crc = _crc(fields.get("crc32", ""))
        token = f"1-{crc:08X}-{size:08X}"
        if (_uint(fields, "file_id") != file_id or fields.get("token") != token
                or fields.get("format") != "SSLOG" or fields.get("format_version") != "0.0"
                or fields.get("closed") != "1"):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid log metadata or active log")
        return RemoteLog(file_id, token, size, crc)

    def _read(self, log: RemoteLog, offset: int) -> bytes:
        fields = self._request("READ", f"{log.file_id} {log.token} {offset}")
        length = _uint(fields, "length", 64)
        expected = min(64, log.size - offset)
        data_hex = fields.get("data", "")
        if length == 0 and data_hex == "-":
            data = b""
        elif re.fullmatch(r"(?:[0-9A-F]{2}){1,64}", data_hex):
            data = bytes.fromhex(data_hex)
        else:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid chunk data")
        if (_uint(fields, "file_id") != log.file_id or fields.get("token") != log.token
                or _uint(fields, "offset") != offset or length != expected or len(data) != length
                or zlib.crc32(data) != _crc(fields.get("crc32", ""))):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Chunk identity, length or CRC mismatch")
        return data

    def download(self, file_id: int, destination: Path, *,
                 progress: Callable[[int, int, str], None] = lambda *_: None) -> Path:
        # Never reuse cached CAPS/META across operations or reconnects.
        self.negotiate()
        log = self.metadata(file_id)
        root = _regular_path(destination, directory=True)
        # Full new-file space is required: v1 never counts a previous partial.
        if shutil.disk_usage(root).free < log.size + 16 * 1024:
            raise OSError("Insufficient destination space for the complete log and metadata")
        name = f"mission_{file_id:06d}_{log.token}.sslog"
        final = root / name
        # Version 1 defines no stable identity scheme. Even non-unknown strings
        # from a peer cannot authorize continuation of a previous partial.
        partial = root / (name + "." + uuid4().hex + ".partial")
        sidecar = partial.with_name(partial.name + ".json")
        if final.exists():
            _regular_path(final)
            raise FileExistsError(f"Destination exists; choose a separate directory: {final}")
        metadata = {"format": "silverstar.gshc-download-state", "schema_version": 1,
                    "partial_file": partial.name, "final_file": final.name, "file_id": file_id,
                    "expected_size": log.size, "crc32": f"{log.crc32:08X}", "token": log.token,
                    "device_id": "unknown", "boot_id": "unknown", "resume_allowed": False,
                    "bytes_written": 0, "verified": False, "status": "partial",
                    "note": "Diagnostic checkpoint only; CRC is not identity. Restart from zero."}
        offset = 0
        crc = 0
        published = False
        digest = hashlib.sha256()
        try:
            with partial.open("xb", buffering=0) as fp:
                _download_checkpoint(sidecar, metadata)
                checkpoint_time = time.monotonic()
                while offset < log.size:
                    self._check()
                    data = self._read(log, offset)
                    written = fp.write(data)
                    if written is not None:
                        offset += written
                    if written != len(data):
                        raise OSError("Incomplete destination log write")
                    crc = zlib.crc32(data, crc)
                    digest.update(data)
                    if time.monotonic() - checkpoint_time >= 1:
                        metadata["bytes_written"] = offset
                        _download_checkpoint(sidecar, metadata)
                        checkpoint_time = time.monotonic()
                    progress(offset, log.size, f"Mission {file_id}: {offset}/{log.size}")
                fp.flush()
                os.fsync(fp.fileno())
            self._check()
            if crc != log.crc32:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Whole-file CRC mismatch; partial preserved")
            # Fresh META detects size/CRC changes, never device/boot identity.
            if self.metadata(file_id) != log:
                raise FileServiceError(FileServiceResult.STALE, "Log changed during download")
            readback = hashlib.sha256()
            with partial.open("rb") as fp:
                while data := fp.read(1024 * 1024):
                    self._check()
                    readback.update(data)
            if partial.stat().st_size != log.size or readback.digest() != digest.digest():
                raise OSError("Destination readback failed")
            self._check()
            if final.exists():
                raise FileExistsError(final)
            metadata.update(bytes_written=offset, verified=True, status="verified_pending_publish")
            _download_checkpoint(sidecar, metadata)
            # Windows rename refuses replacement. Sources are never deleted here.
            partial.rename(final)
            published = True
            # Only our unique checkpoint is removed after verified publication.
            sidecar.unlink()
            return final
        except Exception as error:
            metadata.update(bytes_written=offset, status="cancelled" if isinstance(error, ExportCancelled)
                            else "failed_after_publish" if published else "failed", error=str(error)[:512])
            try:
                _download_checkpoint(sidecar, metadata)
            except OSError:
                # Revoked permissions / a full disk can also prevent the final
                # diagnostic checkpoint. Keep the prior checkpoint and partial.
                _logger.exception("Could not update failed download checkpoint")
            raise

    def prepare_delete(self, file_id: int) -> RemoteLog:
        self.negotiate()
        raise FileServiceError(FileServiceResult.UNSUPPORTED, "LOGFILE v1 has no stable device/boot identity: remote deletion is disabled")

    def delete(self, log: RemoteLog, *, confirmed_token: str) -> None:
        raise FileServiceError(FileServiceResult.UNSUPPORTED, "LOGFILE v1 remote deletion is disabled regardless of token confirmation")

    def cancel_remote(self) -> None:
        # Best effort, bounded, and does not reset the user's local cancel flag.
        try:
            self.transport.exchange("LOGFILE CANCEL", 0.5, Event())
        except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
            self.last_cancel_error = str(exc)


__all__ = ["FileServiceClient", "FileServiceError", "FileServiceResult", "RemoteLog"]
