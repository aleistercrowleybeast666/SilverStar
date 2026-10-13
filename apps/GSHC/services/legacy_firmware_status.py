"""Read-only maintenance.serial.0_0 status; never infers file-service support."""
from dataclasses import dataclass
import re
import time
from threading import Event

from services.file_service_client import FileServiceError, FileServiceResult, _uint
from services.device_export import ExportCancelled


@dataclass(frozen=True)
class LegacyStorageSnapshot:
    received_ns: int
    initialized: bool
    mounted: bool
    writer_open: bool
    healthy: bool
    writes: int
    syncs: int
    errors: int


@dataclass(frozen=True)
class LegacyFirmwareSnapshot:
    firmware: str
    received_ns: int
    lifecycle: int
    ready: bool
    blocking_mask: int
    warning_mask: int
    attitude: str
    capabilities: tuple[int, int, int, int] | None
    storage: LegacyStorageSnapshot | None
    storage_detail: str


def _hex(fields, key):
    value = fields.get(key, "")
    if not re.fullmatch(r"0x[0-9A-Fa-f]{8}", value):
        raise FileServiceError(FileServiceResult.BAD_RESPONSE, f"Invalid legacy {key}")
    return int(value, 16)


class LegacyFirmwareStatusClient:
    def __init__(self, transport, *, cancel: Event, timeout=2.0):
        self.transport, self.cancel, self.timeout = transport, cancel, timeout
        self.firmware = "unknown"
        self.capabilities = None
        self.identity_queried = False

    def _query(self, command):
        # An explicit allowlist keeps this adapter read-only even if called
        # incorrectly. No START, calibration, configuration, unlock or LIST.
        if command not in {"SYSTEM INFO", "SYSTEM STATUS", "SYSTEM CAPABILITIES", "LOG STATUS"}:
            raise ValueError("Not a read-only status command")
        if self.cancel.is_set():
            raise ExportCancelled("Status query cancelled")
        line = self.transport.exchange(command, self.timeout, self.cancel).strip()
        prefix = "OK " + command + " "
        if len(line) > 511 or not line.isascii() or not line.startswith(prefix):
            raise FileServiceError(FileServiceResult.UNSUPPORTED, f"{command} unavailable: " + line[:120])
        fields = {}
        for item in line[len(prefix):].split():
            key, separator, value = item.partition("=")
            if not separator or not key or not value or key in fields:
                raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Malformed legacy status fields")
            fields[key] = value
        return fields

    def status(self):
        if not self.identity_queried:
            self.identity_queried = True
            try:
                info = self._query("SYSTEM INFO")
                if info.get("project") != "SilverStar" or not re.fullmatch(r"[0-9A-Za-z_.+-]{1,48}", info.get("version", "")):
                    raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid legacy firmware identity")
                self.firmware = info["version"]
                caps = self._query("SYSTEM CAPABILITIES")
                self.capabilities = tuple(_hex(caps, key) for key in ("compiled", "enabled", "present", "healthy"))
            except (FileServiceError, TimeoutError):
                # Unknown identity/capabilities must not hide a valid status.
                self.capabilities = None
        fields = self._query("SYSTEM STATUS")
        received = time.monotonic_ns()
        lifecycle, ready = _uint(fields, "state", 8), bool(_uint(fields, "ready", 1))
        block, warn = _hex(fields, "block"), _hex(fields, "warn")
        attitude = fields.get("attitude", "")
        if not re.fullmatch(r"[A-Z_]{1,48}", attitude):
            raise FileServiceError(FileServiceResult.BAD_RESPONSE, "Invalid legacy attitude")
        storage, detail = None, ""
        try:
            log = self._query("LOG STATUS")
            storage = LegacyStorageSnapshot(time.monotonic_ns(),
                bool(_uint(log, "initialized", 1)), bool(_uint(log, "mounted", 1)),
                bool(_uint(log, "open", 1)), bool(_uint(log, "healthy", 1)),
                _uint(log, "writes"), _uint(log, "syncs"), _uint(log, "errors"))
        except (FileServiceError, TimeoutError) as exc:
            detail = str(exc)
        return LegacyFirmwareSnapshot(self.firmware, received, lifecycle, ready,
            block, warn, attitude, self.capabilities, storage, detail)
