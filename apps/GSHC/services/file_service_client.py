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
from services.file_service_block import BLOCK_SIZE, Block_Decode, BlockIntegrityError

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
    # Keep the atomic sibling short: the partial already contains a unique ID.
    # Appending another UUID can exceed Windows' path limit in a valid folder.
    temporary = path.with_name(".checkpoint-" + uuid4().hex + ".tmp")
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
                 timeout: float = 2.0, expected_uart=None) -> None:
        self.transport = transport
        self.cancel = cancel or Event()
        self.timeout = max(0.1, min(30.0, timeout))
        from services.maintenance_serial_profile import MaintenanceSerial_Timeout
        self.expected_uart = expected_uart if expected_uart is not None else getattr(transport, 'expected_uart', None)
        self.timeout = MaintenanceSerial_Timeout(getattr(transport, 'baudrate', None), self.timeout)
        self.capabilities: dict[str, str] | None = None
        self._delete_selection: RemoteLog | None = None
        self.last_cancel_error = ""
        self._block_transfer = 0
        self.transfer_diagnostics = self._TransferDiagnostics_New()

    @staticmethod
    def _TransferDiagnostics_New():
        return dict(batch_replays=0, recovered_batches=0, resync_completed=0, frame_timeouts=0,
                    framing_errors=0, crc_batches=0, duplicate_records=0,
                    retransmitted_window_bytes=0, recovery_failures=0)

    def _check(self) -> None:
        if self.cancel.is_set():
            raise ExportCancelled("Download cancelled; source remains on device")

    def Console_Execute(self, operation: str, arguments: str = '') -> dict[str,str]:
        """One explicit console protocol transaction; never enters or writes files implicitly."""
        if operation not in {'CAPS','STATUS','ENTER','CANCEL','LIST','META','READ'}:
            raise ValueError('Unsupported console file transaction')
        return self._request(operation,arguments)

    def _request(self, op: str, args: str = "") -> dict[str, str]:
        begin=getattr(self.cancel,'Transaction_Begin',None)
        if begin is not None:begin()
        try:return self._Request_Execute(op,args)
        finally:
            if begin is not None:self.cancel.Transaction_End()

    def _Activity_Record(self):
        record=getattr(self.cancel,'Activity_Record',None)
        if record is not None:record()

    def _Request_Execute(self, op: str, args: str = "") -> dict[str, str]:
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
            self._Activity_Record()
            if self.cancel.wait(min(0.05, pending_count * 0.005)):
                self._check()
            pending_count += 1
            command = f"LOGFILE POLL {request_id}"

    def negotiate(self) -> dict[str, str]:
        self._delete_selection = None
        fields = self._request("CAPS")
        if (fields.get("file_service_version") not in (None, "1") or
                fields.get("supported") == "0"):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Unsupported LOGFILE capabilities")
        required = ("file_service_version", "supported", "max_chunk",
                    "telemetry_bulk", "device_id", "boot_id")
        missing = [key for key in required if not fields.get(key)]
        if missing:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE,
                                   "Incomplete LOGFILE capabilities: " + ", ".join(missing))
        if (fields.get("file_service_version") != "1" or fields.get("supported") != "1"
                or fields.get("max_chunk") != "64" or fields.get("telemetry_bulk") != "0"
                or not fields.get("device_id") or not fields.get("boot_id")):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Unsupported LOGFILE capabilities")
        from services.maintenance_serial_profile import MaintenanceSerial_Check
        try:
            MaintenanceSerial_Check(fields, getattr(self.transport, 'baudrate', None), self.expected_uart)
        except ValueError as exc:
            self.capabilities = None
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, str(exc)) from exc
        self.capabilities = fields
        block_keys = ('block_version', 'max_block', 'block_encoding', 'block_window')
        if any(key in fields for key in block_keys) and tuple(fields.get(key) for key in block_keys) != ('1', '512', 'COBS', '1'):
            self.capabilities = None
            raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Unsupported negotiated block capabilities')
        batch_keys = ('batch_version', 'batch_count')
        if any(key in fields for key in batch_keys) and (
                tuple(fields.get(key) for key in batch_keys) != ('1', '4')
                or fields.get('block_version') != '1'):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, 'Unsupported negotiated batch capabilities')

        self._Activity_Record()
        return fields

    def status(self) -> FirmwareSnapshot:
        caps = self.capabilities if self.capabilities is not None else self.negotiate()
        if caps.get("status_version") != "1":
            raise FileServiceError(FileServiceResult.UNSUPPORTED, "Firmware RAM status unsupported")
        fields = self._request("STATUS")
        if fields.get("status_version") != "1" or fields.get("source") != "FC_DEBUG_RAM":
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Unknown status version/source")
        snapshot = FirmwareSnapshot(
            caps.get("firmware", "unknown"), time.monotonic_ns(),
            _uint(fields, "sequence"), _uint(fields, "age_ms"), _uint(fields, "lifecycle", 8),
            bool(_uint(fields, "storage_valid", 1)), bool(_uint(fields, "mounted", 1)),
            bool(_uint(fields, "healthy", 1)), bool(_uint(fields, "writer_open", 1)),
            bool(_uint(fields, "log_fault", 1)), _uint(fields, "finalization", 3),
            _uint(fields, "maintenance", 3), bool(_uint(fields, "cleanup_pending", 1)),
            bool(_uint(fields, "reboot_required", 1)))
        self._Activity_Record()
        return snapshot

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
        sizes = {}
        self.catalog_sizes = {}
        seen_cursors = {0}
        cursor = 0
        for _ in range(1025):
            fields = self._request("LIST", str(cursor))
            end = _uint(fields, "end", 1)
            cursor = _uint(fields, "next_cursor")
            if end:
                if cursor != 0:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid list end")
                self.catalog_sizes = sizes
                self._Activity_Record()
                return result
            file_id = _uint(fields, "file_id", 999999)
            size = _uint(fields, "size")
            if fields.get("closed") != "1" or file_id < 1 or file_id in result or cursor in seen_cursors:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid/active/duplicate list entry")
            seen_cursors.add(cursor)
            result.append(file_id)
            sizes[file_id] = size
            self._Activity_Record()
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
        self._Activity_Record()
        return RemoteLog(file_id, token, size, crc)

    def _read(self, log: RemoteLog, offset: int) -> bytes:
        if (self._block_transfer and self.capabilities is not None
                and self.capabilities.get('block_version') == '1'
                and callable(getattr(self.transport, 'block_poll', None))
                and callable(getattr(self.transport, 'block_complete', None))):
            if (self.capabilities.get('batch_version') == '1'
                    and callable(getattr(self.transport, 'batch_receive', None))
                    and callable(getattr(self.transport, 'batch_complete', None))):
                return self._Batch_Read(log, offset)
            return self._Block_Read(log, offset)
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
        self._Activity_Record()
        return data

    @staticmethod
    def _Block_TextParse(line: str, operation='BLOCK') -> tuple[str, dict[str, str]]:
        if len(line) > 511 or not line.isascii():
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Invalid BLOCK text reply')
        parts = line.split()
        if len(parts) < 4 or parts[1:3] != ['LOGFILE', operation] or parts[0] not in {'PENDING', 'ERR'}:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Unexpected BLOCK reply')
        fields = {}
        for item in parts[3:]:
            key, separator, value = item.partition('=')
            if not separator or not key or not value or key in fields:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Malformed BLOCK fields')
            fields[key] = value
        if parts[0] == 'ERR':
            result = FileServiceResult.STALE if fields.get('code') == 'STALE' else FileServiceResult.IO_ERROR
            raise FileServiceError(result, 'Device rejected BLOCK: ' + fields.get('code', 'unknown'))
        return parts[0], fields

    def _Batch_Read(self, log: RemoteLog, offset: int) -> bytes:
        begin = getattr(self.cancel, 'Transaction_Begin', None)
        if begin is not None:
            begin()
        deadline = time.monotonic() + 30.0
        recovery_request = None
        request_id = None
        try:
            for attempt in range(3):
                self._check()
                recovering = recovery_request is not None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('BATCH absolute transaction deadline exceeded')
                command = f'LOGFILE BATCH {log.file_id} {log.token} {offset} {self._block_transfer:016X} {offset // BLOCK_SIZE}'
                if recovery_request is None:
                    _, fields = self._Block_TextParse(self.transport.exchange(command, min(self.timeout, remaining), self.cancel), 'BATCH')
                    request_id = _uint(fields, 'request_id')
                    if not request_id:
                        raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Missing BATCH request ID')
                else:
                    expected = (self._block_transfer, offset // BLOCK_SIZE, log.file_id,
                                log.crc32, log.size, offset)
                    try:
                        request_id = self.transport.batch_recover(
                            recovery_request, command, expected, deadline, self.cancel)
                    except Exception:
                        self.transfer_diagnostics['recovery_failures'] += 1
                        raise
                    recovery_request = None
                    self.transfer_diagnostics['resync_completed'] += 1
                try:
                    data = self._Batch_Receive(log, offset, request_id, deadline)
                except (TimeoutError, OSError) as error:
                    kind = getattr(error, 'recovery_kind', '')
                    if kind not in ('timeout', 'framing'):
                        raise  # Budgets, I/O errors and cancellation never auto-retry.
                    self.transfer_diagnostics['frame_timeouts' if kind == 'timeout' else 'framing_errors'] += 1
                    if attempt == 2 or not callable(getattr(self.transport, 'batch_recover', None)):
                        raise
                    self._Batch_RetryAdmit(log, offset)
                    recovery_request = request_id
                    self._block_transfer = (uuid4().int & 0xFFFFFFFFFFFFFFFF) or 1
                    continue
                self.transport.batch_complete(request_id)
                if data is not None:
                    if recovering:
                        self.transfer_diagnostics['recovered_batches'] += 1
                    return data
                self.transfer_diagnostics['crc_batches'] += 1
                if attempt < 2:
                    self._Batch_RetryAdmit(log, offset)
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BATCH replay CRC/framing limit')
        except Exception:
            abort = getattr(self.transport, 'batch_abort', None)
            if request_id is not None and callable(abort):
                abort(request_id)
            invalidate = getattr(self.transport, 'block_invalidate', None)
            if callable(invalidate):
                invalidate()
            raise
        finally:
            if begin is not None:
                self.cancel.Transaction_End()

    def _Batch_RetryAdmit(self, log, offset):
        # At most two replays per 2 KiB window and sixteen across one download.
        # The original 30-second window/outer job deadlines are never renewed.
        self._check()
        if self.transfer_diagnostics['batch_replays'] >= 16:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BATCH whole-download replay limit')
        self.transfer_diagnostics['batch_replays'] += 1
        self.transfer_diagnostics['retransmitted_window_bytes'] += min(2048, log.size - offset)

    def _Batch_Receive(self, log, offset, request_id, deadline):
        count = min(4, (log.size - offset + BLOCK_SIZE - 1) // BLOCK_SIZE)
        if count < 1:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Empty BATCH extent')
        output = bytearray()
        corrupt = False
        index = duplicates = 0
        for _ in range(count + 4):
            if index == count:
                break
            self._check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('BATCH absolute transaction deadline exceeded')
            # Complete CRC faults drain the window. A truncated record may only
            # recover through an explicit new-nonce transport boundary.
            reply = self.transport.batch_receive(request_id, min(self.timeout, remaining), self.cancel)
            self._check()
            if time.monotonic() >= deadline:
                raise TimeoutError('Late BATCH record')
            if isinstance(reply, str):
                self._Block_TextParse(reply, 'BATCH')
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Unexpected BATCH text response')
            try:
                block = Block_Decode(reply)
            except BlockIntegrityError:
                corrupt = True
                index += 1
                continue
            except ValueError as error:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, str(error)) from error
            position = offset + index * BLOCK_SIZE
            if (not corrupt and block.transfer == self._block_transfer
                    and block.request_id == request_id and block.file_id == log.file_id
                    and block.whole_crc == log.crc32 and block.size == log.size
                    and offset <= block.offset < position and block.offset % BLOCK_SIZE == 0
                    and block.sequence == block.offset // BLOCK_SIZE
                    and block.data == output[block.offset-offset:block.offset-offset+len(block.data)]):
                duplicates += 1
                self.transfer_diagnostics['duplicate_records'] += 1
                if duplicates > 4:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BATCH duplicate limit')
                continue
            if (block.transfer, block.request_id, block.sequence, block.file_id,
                    block.whole_crc, block.size, block.offset) != (
                    self._block_transfer, request_id, position // BLOCK_SIZE, log.file_id,
                    log.crc32, log.size, position):
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BATCH identity/sequence mismatch')
            output.extend(block.data)
            index += 1
            self._Activity_Record()
        if index != count:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BATCH duplicate limit')
        return None if corrupt else bytes(output)

    def _Block_Read(self, log: RemoteLog, offset: int) -> bytes:
        begin = getattr(self.cancel, 'Transaction_Begin', None)
        if begin is not None:
            begin()
        try:
            return self._Block_Receive(log, offset)
        except TimeoutError:
            invalidate = getattr(self.transport, 'block_invalidate', None)
            if callable(invalidate):
                invalidate()
            raise
        finally:
            if begin is not None:
                self.cancel.Transaction_End()

    def _Block_Receive(self, log: RemoteLog, offset: int) -> bytes:
        self._check()
        sequence = offset // BLOCK_SIZE
        deadline = time.monotonic() + 30.0
        command = f'LOGFILE BLOCK {log.file_id} {log.token} {offset} {self._block_transfer:016X} {sequence}'
        _, fields = self._Block_TextParse(self.transport.exchange(command, self.timeout, self.cancel))
        request_id = _uint(fields, 'request_id')
        if not request_id:
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Missing BLOCK request ID')
        corrupt = pending = 0
        while time.monotonic() < deadline:
            self._check()
            reply = self.transport.block_poll(request_id, min(self.timeout, max(0.001, deadline-time.monotonic())), self.cancel)
            if time.monotonic() >= deadline:
                raise TimeoutError('Late BLOCK reply exceeded absolute transaction deadline')
            if isinstance(reply, str):
                _, fields = self._Block_TextParse(reply)
                if _uint(fields, 'request_id') != request_id:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'Stale BLOCK request ID')
                self._Activity_Record()
                self.cancel.wait(min(0.05, pending * 0.005))
                pending += 1
                continue
            try:
                block = Block_Decode(reply)
            except BlockIntegrityError as error:
                corrupt += 1
                if corrupt > 2:
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BLOCK replay CRC/framing limit') from error
                continue  # Same completed request, no local write or deadline extension.
            except ValueError as error:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, str(error)) from error
            if (block.transfer, block.request_id, block.sequence, block.file_id,
                    block.whole_crc, block.size, block.offset) != (
                    self._block_transfer, request_id, sequence, log.file_id,
                    log.crc32, log.size, offset):
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, 'BLOCK identity/sequence mismatch')
            self._check()
            if time.monotonic() >= deadline:
                raise TimeoutError('BLOCK validation exceeded absolute transaction deadline')
            self.transport.block_complete(request_id)
            self._Activity_Record()
            return block.data
        raise TimeoutError('BLOCK absolute transaction deadline exceeded; reconnect required')

    def download(self, file_id: int, destination: Path, *,
                 progress: Callable[[int, int, str], None] = lambda *_: None,
                 byte_progress=None) -> Path:
        # Never reuse cached CAPS/META across operations or reconnects.
        notify = byte_progress or (lambda *_: None)
        notify(0,None,'capabilities')
        self.negotiate()
        # Unique per attempt, never reused across reconnect/partial downloads.
        self._block_transfer = (uuid4().int & 0xFFFFFFFFFFFFFFFF) or 1
        self.transfer_diagnostics = self._TransferDiagnostics_New()
        notify(0,None,'metadata')
        log = self.metadata(file_id)
        notify(0,log.size,'receiving')
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
                    "note": "Diagnostic checkpoint only; CRC is not identity. Restart from zero.",
                    "transfer_diagnostics": self.transfer_diagnostics}
        offset = 0
        crc = 0
        published = False
        digest = hashlib.sha256()
        try:
            with partial.open("xb", buffering=0) as fp:
                _download_checkpoint(sidecar, metadata)
                checkpoint_time = time.monotonic()
                if log.size:notify(0,log.size,'first_block')
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
                    notify(offset,log.size,'receiving')
                notify(offset,log.size,'verifying')
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
                    self._Activity_Record()
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
            notify(offset,log.size,'verified')
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
