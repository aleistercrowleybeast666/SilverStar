"""Mock-only, short-lived device API/CLI. No hardware or network transport.

Log DTO fields and sample bytes follow the pinned LOGFILE v1 contract. Downloads
use session-export v1; the golden bytes are NOT a valid SSLOG recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Callable


class DeviceServiceResult(str, Enum):
    OK = "OK"
    BAD_ARGUMENT = "BAD_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED = "UNSUPPORTED"
    BUSY = "BUSY"
    STALE = "STALE"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    IO_ERROR = "IO_ERROR"


@dataclass(frozen=True)
class ServiceReply:
    result: DeviceServiceResult
    data: object = None
    detail: str = ""

    def Reply_AsDict(self) -> dict:
        return {"mock": True, "hardware_access": False,
                "result": self.result.value, "data": self.data, "detail": self.detail}


@dataclass(frozen=True)
class _Lease:
    owner: str
    generation: int
    deadline: float


class MockDeviceService:
    """One object is one demo owner registry; never an OS/hardware lock."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        reference = Path(__file__).parent / "contracts" / "log_file_service_v1.json"
        contract = json.loads(reference.read_text(encoding="utf-8-sig"))
        self._golden = contract["golden"]
        self._payload = bytes.fromhex(self._golden["file_bytes_hex"])
        self._chunk_bytes = contract["limits"]["chunk_bytes"]
        self._devices = {"mock-fc-001": "flight_controller", "mock-rig-001": "test_rig"}
        self._clock = clock
        self._leases: dict[str, _Lease] = {}
        self._generation = 0
        self._lock = Lock()

    def _Device_Check(self, device_ref: str) -> ServiceReply | None:
        if type(device_ref) is not str or device_ref not in self._devices:
            return ServiceReply(DeviceServiceResult.NOT_FOUND, detail="Unknown mock device reference")
        return None

    def Device_List(self) -> ServiceReply:
        return ServiceReply(DeviceServiceResult.OK, [
            {"device_ref": ref, "kind": kind, "transport": "memory-only",
             "device_id": "unknown", "boot_id": "unknown", "connected": False}
            for ref, kind in self._devices.items()])

    def Device_ReadStatus(self, device_ref: str) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        return ServiceReply(DeviceServiceResult.OK, {
            "device_ref": device_ref, "device_id": "unknown", "boot_id": "unknown",
            "connected": False, "readiness": "unknown", "motion_enabled": False,
            "source": "fixed-mock-snapshot", "live": False,
            "connection_lease": self.Lease_Read(device_ref).data})

    def Device_ReadCapabilities(self, device_ref: str) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        return ServiceReply(DeviceServiceResult.OK, {
            "device_ref": device_ref,
            "log_file_service": {
                "file_service_version": 1, "supported": int(device_ref == "mock-fc-001"),
                "max_chunk": self._chunk_bytes, "delete_supported": 0, "telemetry_bulk": 0,
                "device_id": "unknown", "boot_id": "unknown"},
            "service_permissions": {"read_status": True, "read_collection_status": True,
                                    "real_connect": False, "write_commands": False,
                                    "delete_logs": False, "flash": False, "motion": False}})

    def Collection_ReadStatus(self, device_ref: str) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        return ServiceReply(DeviceServiceResult.OK, {
            "device_ref": device_ref, "state": "mock-idle", "active": False,
            "sample_count": 0, "last_sample_at": None, "source": "fixed-mock-snapshot",
            "start_supported": False, "stop_supported": False})

    def _Log_Check(self, device_ref: str, file_id: int | None = None) -> ServiceReply | None:
        if error := self._Device_Check(device_ref):
            return error
        if device_ref != "mock-fc-001":
            return ServiceReply(DeviceServiceResult.UNSUPPORTED, detail="No mock log service on this device")
        if file_id is not None and (type(file_id) is not int or file_id != 1):
            return ServiceReply(DeviceServiceResult.NOT_FOUND, detail="Only golden file_id 1 exists")
        return None

    def Log_List(self, device_ref: str) -> ServiceReply:
        if error := self._Log_Check(device_ref):
            return error
        return ServiceReply(DeviceServiceResult.OK, {
            "contract": "silverstar.log-file-service", "protocol_version": 1,
            "device_id": "unknown", "boot_id": "unknown",
            "fixture": "contract-golden-transport-only", "valid_sslog_recording": False,
            "entries": [{"file_id": 1, "size": self._golden["size"], "closed": 1}],
            "end": 1, "next_cursor": 0})

    def Log_ReadMetadata(self, device_ref: str, file_id: int) -> ServiceReply:
        if file_id is None:
            return ServiceReply(DeviceServiceResult.BAD_ARGUMENT, detail="file_id is required")
        if error := self._Log_Check(device_ref, file_id):
            return error
        return ServiceReply(DeviceServiceResult.OK, {
            "file_id": 1, "token": self._golden["token"], "size": self._golden["size"],
            "crc32": self._golden["crc32"], "format": "SSLOG", "format_version": "0.0", "closed": 1})

    def _Log_ReadChunk(self, offset: int) -> bytes:
        # No peer, wire commands or stored-state instructions are executed.
        return self._payload[offset:offset + self._chunk_bytes]

    def Log_DownloadTemporary(self, device_ref: str, file_id: int) -> ServiceReply:
        metadata = self.Log_ReadMetadata(device_ref, file_id)
        if metadata.result != DeviceServiceResult.OK:
            return metadata
        meta = metadata.data
        # This adapter is deliberately restricted to the bounded golden fixture.
        # There is no reconnect/resume, file path input or actual LOGFILE transport.
        payload = b"".join(self._Log_ReadChunk(offset)
                           for offset in range(0, meta["size"], self._chunk_bytes))
        if (len(payload) != meta["size"] or
                f"{zlib.crc32(payload):08X}" != meta["crc32"]):
            return ServiceReply(DeviceServiceResult.INTEGRITY_ERROR, detail="Golden size/CRC mismatch")
        digest = hashlib.sha256(payload).hexdigest()
        package: Path | None = None
        try:
            package = Path(tempfile.mkdtemp(prefix="silverstar-device-service-mock-"))
            logs = package / "logs"
            logs.mkdir()
            partial = logs / "flight.sslog.part"
            with partial.open("xb") as stream:
                stream.write(payload)
            partial.replace(logs / "flight.sslog")
            manifest = {
                "schema_version": 1, "format": "silverstar.session-export",
                "session_id": package.name, "created_at": datetime.now(timezone.utc).isoformat(),
                "source_app": {"name": "SilverStar_DeviceService", "version": "0.0.0-mock"},
                "protocols": {"log_file_service": 1, "sslog": "0.0"},
                "files": [{"path": "logs/flight.sslog", "role": "flight_log", "format": "SSLOG",
                           "format_version": "0.0", "size_bytes": len(payload), "sha256": digest}]}
            with (package / "manifest.json.part").open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=True, indent=2)
                stream.write("\n")
            (package / "manifest.json.part").replace(package / "manifest.json")
        except OSError:
            return ServiceReply(DeviceServiceResult.IO_ERROR,
                                {"incomplete_temporary_package": str(package) if package else None},
                                "Temporary sample publication failed; do not use partial files")
        return ServiceReply(DeviceServiceResult.OK, {
            "package_directory": str(package), "manifest_path": str(package / "manifest.json"),
            "file_path": str(package / "logs" / "flight.sslog"), "size_bytes": len(payload),
            "sha256": digest, "device_id": "unknown", "boot_id": "unknown",
            "fixture": "contract-golden-transport-only", "valid_sslog_recording": False,
            "resume_supported": False, "source_deleted": False})

    def _Lease_Current(self, device_ref: str) -> _Lease | None:
        lease = self._leases.get(device_ref)
        if lease is not None and lease.deadline <= self._clock():
            del self._leases[device_ref]
            return None
        return lease

    def Lease_Read(self, device_ref: str) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        with self._lock:
            lease = self._Lease_Current(device_ref)
            return ServiceReply(DeviceServiceResult.OK, {
                "scope": "single-python-object-only", "hardware_exclusion": False,
                "owner": lease.owner if lease else None,
                "generation": lease.generation if lease else None})

    def Lease_Acquire(self, device_ref: str, owner: str, ttl_seconds: float = 10.0) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        if (type(owner) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", owner) is None or
                type(ttl_seconds) not in (int, float) or
                not 1 <= ttl_seconds <= 60):
            return ServiceReply(DeviceServiceResult.BAD_ARGUMENT, detail="Invalid owner or TTL (1..60 s)")
        with self._lock:
            if self._Lease_Current(device_ref) is not None:
                return ServiceReply(DeviceServiceResult.BUSY, detail="Mock connection already has an owner")
            self._generation += 1
            lease = _Lease(owner, self._generation, self._clock() + ttl_seconds)
            self._leases[device_ref] = lease
            return ServiceReply(DeviceServiceResult.OK, {"owner": owner, "generation": lease.generation,
                                                        "ttl_seconds": ttl_seconds})

    def Lease_Release(self, device_ref: str, owner: str, generation: int) -> ServiceReply:
        if error := self._Device_Check(device_ref):
            return error
        with self._lock:
            lease = self._Lease_Current(device_ref)
            if (lease is None or type(owner) is not str or type(generation) is not int or
                    lease.owner != owner or lease.generation != generation):
                return ServiceReply(DeviceServiceResult.STALE, detail="Expired or mismatched mock lease")
            del self._leases[device_ref]
            return ServiceReply(DeviceServiceResult.OK)

    def Request_Execute(self, request: dict) -> ServiceReply:
        """Explicit allowlist; data fields never select code, commands or paths."""
        if type(request) is not dict or type(request.get("operation")) is not str:
            return ServiceReply(DeviceServiceResult.BAD_ARGUMENT, detail="Expected an operation object")
        operations = {
            "devices": ((), self.Device_List),
            "status": (("device_ref",), self.Device_ReadStatus),
            "capabilities": (("device_ref",), self.Device_ReadCapabilities),
            "collection": (("device_ref",), self.Collection_ReadStatus),
            "logs": (("device_ref",), self.Log_List),
            "metadata": (("device_ref", "file_id"), self.Log_ReadMetadata),
            "download": (("device_ref", "file_id"), self.Log_DownloadTemporary),
            "lease": (("device_ref",), self.Lease_Read)}
        selected = operations.get(request["operation"])
        if selected is None:
            return ServiceReply(DeviceServiceResult.UNSUPPORTED, detail="Operation is not in the mock read allowlist")
        fields, function = selected
        if set(request) != {"operation", *fields}:
            return ServiceReply(DeviceServiceResult.BAD_ARGUMENT, detail="Missing or unexpected fields")
        return function(*(request[field] for field in fields))


def Cli_Main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock-only API: no hardware, server or real commands")
    subcommands = parser.add_subparsers(dest="operation", required=True)
    subcommands.add_parser("devices")
    for operation in ("status", "capabilities", "collection", "logs", "metadata", "download", "lease"):
        command = subcommands.add_parser(operation)
        command.add_argument("device_ref", help="mock-fc-001 or mock-rig-001; never a COM/USB path")
        if operation in ("metadata", "download"):
            command.add_argument("file_id", type=int)
    subcommands.add_parser("lease-demo", help="Short-lived in-memory contention demonstration")
    arguments = vars(parser.parse_args(argv))
    service = MockDeviceService()
    if arguments["operation"] == "lease-demo":
        acquired = service.Lease_Acquire("mock-fc-001", "gshc")
        conflict = service.Lease_Acquire("mock-fc-001", "ai")
        released = service.Lease_Release("mock-fc-001", "gshc", acquired.data["generation"])
        transferred = service.Lease_Acquire("mock-fc-001", "ai")
        reply = ServiceReply(DeviceServiceResult.OK, {
            "scope": "single-python-object-only", "hardware_exclusion": False,
            "gshc_acquire": acquired.Reply_AsDict(), "ai_conflict": conflict.Reply_AsDict(),
            "gshc_release": released.Reply_AsDict(), "ai_acquire_after_release": transferred.Reply_AsDict()})
    else:
        reply = service.Request_Execute(arguments)
    print(json.dumps(reply.Reply_AsDict(), ensure_ascii=True, indent=2))
    return 0 if reply.result == DeviceServiceResult.OK else 1


if __name__ == "__main__":
    raise SystemExit(Cli_Main())
