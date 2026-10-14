"""Bounded, symbol-free SWD service shared by the GUI and local CLI.

Target access is opt-in and fail-closed. No Qt, serial, reset, halt, resume,
flash, register-write or arbitrary debugger-command operation is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from threading import Event, Lock
import time

from transport.probe_inventory import HostProbe


# Only coordinates callers of SwdSession in this Python process. It is not an
# OS device claim and does not exclude another process or a direct HID client.
_ProbeOwners = {}
_ProbeOwnersLock = Lock()
_MAX_PROCESS_OWNERS = 32


class SwdResult(Enum):
    Ok = 'ok'
    InvalidRequest = 'invalid_request'
    Unsupported = 'unsupported'
    MissingDependency = 'missing_dependency'
    SafetyNotProven = 'safety_not_proven'
    Busy = 'busy'
    RateLimited = 'rate_limited'
    NotAttached = 'not_attached'
    Cancelled = 'cancelled'
    Timeout = 'timeout'
    TransportError = 'transport_error'
    TargetMismatch = 'target_mismatch'
    BudgetExceeded = 'budget_exceeded'
    ReleaseFailed = 'release_failed'


class SwdError(Exception):
    def __init__(self, result: SwdResult, detail: str):
        super().__init__(detail)
        self.result = result


@dataclass(frozen=True)
class SwdSnapshot:
    probe_identity: str
    target: str
    cpuid: int
    device_id: int
    revision_id: int
    core_state: str
    dhcsr: int
    received_ns: int
    captured_utc: str
    duration_ms: float
    symbols: str = 'unmatched'
    consistency: str = 'non_atomic_live_read'

    @property
    def age_ms(self):
        return max(0.0, (time.monotonic_ns() - self.received_ns) / 1e6)


@dataclass(frozen=True)
class SwdReply:
    result: SwdResult
    detail: str = ''
    snapshot: SwdSnapshot | None = None
    data: bytes = b''
    address: int | None = None
    received_ns: int | None = None
    captured_utc: str = ''
    duration_ms: float = 0.0
    consistency: str = 'non_atomic_live_read'


def _ValidateProbe(probe):
    if not isinstance(probe, HostProbe) or not probe.identity or len(probe.identity) > 512:
        raise SwdError(SwdResult.InvalidRequest, 'An explicit host probe identity is required')
    # First adapter profile is deliberately narrow; descriptor discovery is wider.
    if probe.usb_id.upper() != 'FAED:4870' or probe.family != 'CMSIS-DAP':
        raise SwdError(SwdResult.Unsupported, 'Only the Horco FAED:4870 CMSIS-DAP profile is implemented')
    if probe.identity_kind != 'USB serial' or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', probe.serial):
        raise SwdError(SwdResult.Unsupported, 'A stable, command-safe USB serial identity is required')
    expected = rf'USB\VID_FAED&PID_4870\{probe.serial}'
    if probe.identity.upper() != expected.upper():
        raise SwdError(SwdResult.InvalidRequest, 'Probe serial does not match the selected USB identity')


class SwdSession:
    """Single owner, no pending queue; concurrent calls return Busy.

    Every transport failure invalidates the session. Cancel is a threading.Event.
    The backend is an internal dependency seam for deterministic host tests.
    A context manager always attempts bounded resource release.
    """
    MAX_READ = 1024
    MAX_BYTES = 65536
    MAX_SAMPLES = 600
    MAX_SECONDS = 600
    # F405/F407/F415/F417 shared ID 0x413: never claim an exact F407 part.
    _RAM = ((0x20000000, 0x20020000), (0x10000000, 0x10010000))

    def __init__(self, *, cancel=None, _backend_factory=None):
        self.cancel = cancel if cancel is not None else Event()
        self._factory = _backend_factory
        self._backend = None
        self._lock = Lock()
        self._probe = None
        self._owned_probe_identity = ''
        self._started = 0.0
        self._bytes = 0
        self._samples = 0
        self._last_sample = float('-inf')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        reply = self.Swd_Detach()
        if reply.result != SwdResult.Ok:
            raise SwdError(reply.result, reply.detail)

    def Swd_Attach(self, probe: HostProbe) -> SwdReply:
        def operation():
            if self._backend is not None:
                # A local repeated request must not release the current owner.
                return SwdReply(SwdResult.Busy, 'Detach the current target before attaching')
            _ValidateProbe(probe)
            self._acquire_process_owner(probe.identity)
            from transport._swd_pyocd import PyOcdMemAp
            self._backend = (self._factory or PyOcdMemAp)(self.cancel)
            self._probe = probe
            self._started, self._bytes, self._samples = time.monotonic(), 0, 0
            self._last_sample = float('-inf')
            if self._backend.open(probe) is not None:
                raise SwdError(SwdResult.TransportError, 'Backend open must succeed with None or raise SwdError')
            return self._snapshot()
        return self._run(operation)

    def Swd_Snapshot(self) -> SwdReply:
        return self._run(self._snapshot)

    def Swd_ReadMemory(self, address: int, length: int) -> SwdReply:
        def operation():
            # MMIO/flash/aliases are excluded; even reads can clear peripheral flags.
            if (type(address) is not int or type(length) is not int or
                    not 1 <= length <= self.MAX_READ or
                    not any(lo <= address < address + length <= hi for lo, hi in self._RAM)):
                return SwdReply(SwdResult.InvalidRequest, 'Read must fit one approved RAM region, 1..1024 bytes')
            limited = self._budget(length)
            if limited is not None:
                return limited
            from datetime import datetime, timezone
            started = time.monotonic_ns()
            data = self._read(address, length)
            received = time.monotonic_ns()
            return SwdReply(SwdResult.Ok, data=data, address=address, received_ns=received,
                captured_utc=datetime.now(timezone.utc).isoformat(), duration_ms=(received-started)/1e6)
        return self._run(operation)

    def Swd_Detach(self) -> SwdReply:
        if not self._lock.acquire(blocking=False):
            return SwdReply(SwdResult.Busy, 'Operation in progress; cancel then retry detach')
        try:
            return self._release()
        finally:
            self._lock.release()

    def _release(self):
        backend, self._backend = self._backend, None
        self._probe = None
        if backend is not None:
            try:
                if backend.close() is not None:
                    raise SwdError(SwdResult.ReleaseFailed, 'Backend close must return None after complete release')
            except Exception as exc:
                # Retain ownership so a later detach can retry cleanup.
                self._backend = backend
                return SwdReply(SwdResult.ReleaseFailed, str(exc)[:400])
        with _ProbeOwnersLock:
            if _ProbeOwners.get(self._owned_probe_identity) is self:
                del _ProbeOwners[self._owned_probe_identity]
            self._owned_probe_identity = ''
        return SwdReply(SwdResult.Ok, 'Detached; no resume/reset operation requested')

    def _acquire_process_owner(self, identity):
        key = identity.upper()
        with _ProbeOwnersLock:
            if key in _ProbeOwners:
                raise SwdError(SwdResult.Busy, 'Probe is held by another SwdSession in this Python process')
            if len(_ProbeOwners) >= _MAX_PROCESS_OWNERS:
                raise SwdError(SwdResult.Busy, 'Within-process probe session capacity reached')
            _ProbeOwners[key] = self
            self._owned_probe_identity = key

    def _run(self, operation):
        if not self._lock.acquire(blocking=False):
            return SwdReply(SwdResult.Busy, 'Another operation owns the session')
        try:
            try:
                if self.cancel.is_set():
                    raise SwdError(SwdResult.Cancelled, 'Operation cancelled')
                return operation()
            except SwdError as exc:
                result, detail = exc.result, str(exc)
            except Exception as exc:
                result, detail = SwdResult.TransportError, str(exc)
            # Every backend exception can follow a partial claim. Local Busy,
            # invalid parameters and pre-I/O rate limiting return replies above.
            released = self._release()
            if released.result != SwdResult.Ok:
                return SwdReply(released.result, f'{result.value}: {detail}; release: {released.detail}')
            return SwdReply(result, detail[:600])
        finally:
            self._lock.release()

    def _budget(self, count):
        if self._backend is None or self._probe is None:
            raise SwdError(SwdResult.NotAttached, 'No target attached')
        now = time.monotonic()
        if (time.monotonic() - self._started >= self.MAX_SECONDS or
                self._samples >= self.MAX_SAMPLES or self._bytes + count > self.MAX_BYTES):
            raise SwdError(SwdResult.BudgetExceeded, 'Session time, sample or byte limit reached; explicitly reconnect')
        if now - self._last_sample < .1:
            return SwdReply(SwdResult.RateLimited, 'At most 10 operations/second; no request queued')
        self._last_sample = now
        self._samples += 1
        self._bytes += count

    def _read(self, address, length):
        if self.cancel.is_set():
            raise SwdError(SwdResult.Cancelled, 'Operation cancelled')
        data = self._backend.read(address, length)
        if self.cancel.is_set():
            raise SwdError(SwdResult.Cancelled, 'Operation cancelled during read')
        if not isinstance(data, bytes) or len(data) != length:
            raise SwdError(SwdResult.TransportError, 'Incomplete memory read')
        return data

    def _snapshot(self):
        from datetime import datetime, timezone
        limited = self._budget(12)
        if limited is not None:
            return limited
        started = time.monotonic_ns()
        cpuid = int.from_bytes(self._read(0xE000ED00, 4), 'little')
        # Check Cortex-M4 before reading the STM32-specific debug register.
        if cpuid & 0xFF00FFF0 != 0x4100C240:
            raise SwdError(SwdResult.TargetMismatch, 'Target is not an Arm Cortex-M4')
        idcode = int.from_bytes(self._read(0xE0042000, 4), 'little')
        if idcode & 0xFFF != 0x413:
            raise SwdError(SwdResult.TargetMismatch, 'Device ID is not STM32F405/407/415/417 (0x413)')
        dhcsr = int.from_bytes(self._read(0xE000EDF0, 4), 'little')
        # DHCSR S_RESET_ST/S_RETIRE_ST are sticky read-clear bits. Document that
        # status observation consumes them; do not infer a continuous trace.
        state = ('reset_observed' if dhcsr & (1 << 25) else
                 'lockup' if dhcsr & (1 << 19) else
                 'halted' if dhcsr & (1 << 17) else
                 'sleeping' if dhcsr & (1 << 18) else 'running')
        received = time.monotonic_ns()
        snapshot = SwdSnapshot(self._probe.identity, 'STM32F405/407/415/417', cpuid,
                               idcode & 0xFFF, idcode >> 16, state, dhcsr, received,
                               datetime.now(timezone.utc).isoformat(), (received-started)/1e6)
        return SwdReply(SwdResult.Ok, snapshot=snapshot)
