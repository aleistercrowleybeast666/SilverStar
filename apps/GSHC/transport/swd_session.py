"""Bounded SWD service shared by the GUI and local CLI.

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
    FirmwareMismatch = 'firmware_mismatch'


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
    target_evidence: str = 'device_family_id'
    firmware_status: str = 'not_imported'

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
    diagnostics: tuple = ()
    watches: tuple = ()
    firmware_sha256: str = ''
    watch_revision: int = 0
    budget: dict | None = None
    core_observation: str = ''
    watch_identity: dict | None = None


def _ValidateProbe(probe):
    from transport.swd_backends import ProbeKind_Get
    return ProbeKind_Get(probe)


def Target_FamilyIdGet(profile):
    """Only the already reviewed F405/407/415/417 identity-register family."""
    return 0x413 if profile is not None and profile.name.startswith(
        ('STM32F405','STM32F407','STM32F415','STM32F417')) else None


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

    def __init__(self, *, cancel=None, _backend_factory=None, target=None, firmware=None):
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
        self._target_name = target or (firmware.target.name if firmware else None)
        self._profile = None
        self._firmware = firmware
        self._firmware_status = 'unmatched' if firmware else 'not_imported'
        self._verify_attempted = False

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
            if (self._firmware and getattr(self._firmware,'image_identity',None) is not None
                    and self._firmware.provenance != 'build_bound'):
                return SwdReply(SwdResult.InvalidRequest, 'Image identity v2 requires a bound descriptor before attachment')
            if self._target_name is not None:
                from transport.swd_firmware import Target_Get
                self._profile = Target_Get(self._target_name)
                if self._firmware and self._profile != self._firmware.target:
                    return SwdReply(SwdResult.TargetMismatch, 'Selected target disagrees with imported firmware')
            self._acquire_process_owner(probe.identity)
            from transport.swd_backends import ProbeBackend_Create
            self._backend = self._factory(self.cancel) if self._factory else ProbeBackend_Create(probe,self.cancel)
            if self._profile is not None:
                self._backend.configure(self._profile)
            self._probe = probe
            self._started, self._bytes, self._samples = time.monotonic(), 0, 0
            self._last_sample = float('-inf')
            self._firmware_status = 'unmatched' if self._firmware else 'not_imported'
            self._verify_attempted = False
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
                    not (self._profile.Contains(address,length,'ram') if self._profile else
                         any(lo <= address < address + length <= hi for lo, hi in self._RAM))):
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
        self._firmware_status = 'unmatched' if self._firmware else 'not_imported'
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
                from transport.swd_firmware import DiagnosticError, DiagnosticResult
                result = (SwdResult.Unsupported if isinstance(exc,DiagnosticError) and exc.result==DiagnosticResult.Unsupported
                          else SwdResult.InvalidRequest if isinstance(exc,DiagnosticError) else SwdResult.TransportError)
                detail = str(exc)
            # Every backend exception can follow a partial claim. Local Busy,
            # invalid parameters and pre-I/O rate limiting return replies above.
            released = self._release()
            if released.result != SwdResult.Ok:
                return SwdReply(released.result, f'{result.value}: {detail}; release: {released.detail}')
            return SwdReply(result, detail[:600])
        finally:
            self._lock.release()

    def _budget(self, count, minimum_interval=.1):
        if self._backend is None or self._probe is None:
            raise SwdError(SwdResult.NotAttached, 'No target attached')
        now = time.monotonic()
        if (time.monotonic() - self._started >= self.MAX_SECONDS or
                self._samples >= self.MAX_SAMPLES or self._bytes + count > self.MAX_BYTES):
            raise SwdError(SwdResult.BudgetExceeded, 'Session time, sample or byte limit reached; explicitly reconnect')
        if now - self._last_sample < minimum_interval:
            return SwdReply(SwdResult.RateLimited, f'Minimum interval {minimum_interval:g}s; no request queued')
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

    def _snapshot(self, minimum_interval=.1):
        from datetime import datetime, timezone
        limited = self._budget(12,minimum_interval)
        if limited is not None:
            return limited
        started = time.monotonic_ns()
        cpuid = int.from_bytes(self._read(0xE000ED00, 4), 'little')
        # A selected official memory map verifies core capability, not package ID.
        if self._profile is not None:
            if not self._profile.CoreMatches(cpuid):
                raise SwdError(SwdResult.TargetMismatch, 'CPUID does not match selected target core')
            idcode = 0
        elif cpuid & 0xFF00FFF0 != 0x4100C240:
            raise SwdError(SwdResult.TargetMismatch, 'Target is not an Arm Cortex-M4')
        if self._profile is None or Target_FamilyIdGet(self._profile) is not None:
            idcode = int.from_bytes(self._read(0xE0042000, 4), 'little')
            if idcode & 0xFFF != 0x413:
                raise SwdError(SwdResult.TargetMismatch, 'Device ID is not STM32F405/407/415/417 (0x413); select an installed target')
        dhcsr = int.from_bytes(self._read(0xE000EDF0, 4), 'little')
        # DHCSR S_RESET_ST/S_RETIRE_ST are sticky read-clear bits. Document that
        # status observation consumes them; do not infer a continuous trace.
        state = ('reset_observed' if dhcsr & (1 << 25) else
                 'lockup' if dhcsr & (1 << 19) else
                 'halted' if dhcsr & (1 << 17) else
                 'sleeping' if dhcsr & (1 << 18) else 'running')
        received = time.monotonic_ns()
        snapshot = SwdSnapshot(self._probe.identity, self._profile.name if self._profile else 'STM32F405/407/415/417', cpuid,
                               idcode & 0xFFF, idcode >> 16, state, dhcsr, received,
                               datetime.now(timezone.utc).isoformat(), (received-started)/1e6,
                               symbols='matched' if self._firmware_status == 'matched' else 'unmatched',
                                target_evidence=('selected_part_core_and_family_verified' if idcode else 'selected_part_core_verified')
                                                if self._profile else 'device_family_id',
                               firmware_status=self._firmware_status)
        return SwdReply(SwdResult.Ok, snapshot=snapshot)

    def Swd_VerifyFirmware(self) -> SwdReply:
        def operation():
            if not self._firmware or not self._profile:
                return SwdReply(SwdResult.InvalidRequest, 'Import an ELF and target before attaching')
            if self._verify_attempted:
                return SwdReply(SwdResult.InvalidRequest, 'One firmware scan per connection; detach before retry')
            limited = self._budget(0)
            if limited: return limited
            self._verify_attempted = True
            self._firmware_status = 'unmatched'
            total = sum(len(data) for _,data in self._firmware.segments)
            if not 1 <= total <= 2097152:
                raise SwdError(SwdResult.BudgetExceeded, 'Flash verification exceeds 2 MiB')
            deadline = time.monotonic()+120
            compared = 0
            ranges = tuple((address, len(data)) for address, data in self._firmware.segments)
            for address, data in self._firmware.segments:
                if not self._profile.Contains(address,len(data),'flash'):
                    raise SwdError(SwdResult.InvalidRequest, 'ELF segment outside trusted flash')
                for offset in range(0,len(data),1024):
                    if time.monotonic() >= deadline:
                        raise SwdError(SwdResult.Timeout, 'Firmware verification exceeded 120 seconds')
                    expected = data[offset:offset+1024]
                    actual = self._read(address+offset,len(expected))
                    if actual != expected:
                        first = next(i for i, pair in enumerate(zip(expected, actual)) if pair[0] != pair[1])
                        self._firmware_status = 'mismatch'
                        identity = 'bound image' if getattr(self._firmware,'image_identity',None) else 'ELF'
                        return SwdReply(SwdResult.FirmwareMismatch,
                            f'Flash LMA differs at 0x{address+offset+first:08X}: {identity} {expected[first]:02X}, target {actual[first]:02X}; '
                            f'read block [0x{address+offset:08X},0x{address+offset+len(expected):08X}); '
                            f'{compared} prior bytes matched of {total}; scan stopped, diagnostic reads disabled',
                            address=address+offset+first)
                    compared += len(expected)
            self._firmware_status = 'matched'
            coverage = ', '.join(f'[0x{a:08X},0x{a+n:08X})' for a,n in ranges)
            identity = ('Bound ELF/HEX image including checked erased alignment gaps' if getattr(self._firmware,'image_identity',None)
                        else 'Complete ELF load contents')
            return SwdReply(SwdResult.Ok, f'{identity} matched ({compared}/{total} bytes); '
                            f'flash LMA ranges {coverage}; live non-atomic observation')
        return self._run(operation)

    def _watch_selection(self, identifiers):
        from silverstar_diagnostics.watch import MAX_WATCH
        if (type(identifiers) not in (tuple,list) or len(identifiers) > MAX_WATCH or
                any(type(item) is not str for item in identifiers) or len(set(identifiers)) != len(identifiers)):
            raise ValueError('Select at most 16 unique ELF catalog IDs')
        catalog = {item.id:item for item in self._firmware.watches} if self._firmware else {}
        if any(item not in catalog or catalog[item].unavailable for item in identifiers):
            raise ValueError('Unknown or unavailable ELF variable; no address expressions accepted')
        return tuple(catalog[item] for item in identifiers)

    def _watch_read(self, fields):
        from datetime import datetime, timezone
        from silverstar_diagnostics.watch import Value_Decode
        count = sum(field.size for field in fields)
        if count > 128 or self._bytes+count > self.MAX_BYTES:
            raise SwdError(SwdResult.BudgetExceeded, 'Watch RAM byte budget reached')
        if any(not self._profile.Contains(field.address,field.size,'ram') or field.size not in (1,2,4,8) for field in fields):
            raise SwdError(SwdResult.InvalidRequest, 'Watch outside trusted RAM scalar ranges')
        self._bytes += count
        rows = []
        for field in fields:
            started = time.monotonic_ns()
            data = self._read(field.address,field.size)
            value, state = Value_Decode(field,data)
            received = time.monotonic_ns()
            rows.append(dict(id=field.id,source=field.source,symbol=field.symbol,member=field.member,
                type=field.type_name,address=field.address,size=field.size,value=value,raw_hex=data.hex(),
                state=state,reason='RAM observation; no readiness or MCU sample age inferred',
                received_ns=received,captured_utc=datetime.now(timezone.utc).isoformat(),
                duration_ms=(received-started)/1e6,consistency='non_atomic_live_read',mcu_sample_age_ms=None))
        return tuple(rows)

    def _budget_report(self):
        return dict(bytes_used=self._bytes,bytes_limit=self.MAX_BYTES,samples_used=self._samples,
                    samples_limit=self.MAX_SAMPLES,seconds_used=max(0,time.monotonic()-self._started),seconds_limit=self.MAX_SECONDS)

    def Swd_ReadWatches(self, identifiers) -> SwdReply:
        """Read selected catalog scalars only; no MMIO or core-status reads.

        Match belongs to this connection. An unobserved reset/reflash cannot be
        detected by RAM reads alone; reattach/verify after a known target change.
        """
        def operation():
            try: fields = self._watch_selection(identifiers)
            except ValueError as exc: return SwdReply(SwdResult.InvalidRequest,str(exc))
            if self._firmware_status != 'matched':
                return SwdReply(SwdResult.FirmwareMismatch,'Watch reads require matched firmware in this connection')
            limited = self._budget(0,1.0)
            if limited: return limited
            return SwdReply(SwdResult.Ok,watches=self._watch_read(fields),
                            firmware_sha256=self._firmware.sha256,budget=self._budget_report(),
                            watch_identity=dict(probe_identity=self._probe.identity,target=self._profile.name,
                                firmware_status=self._firmware_status,match_scope='load_bytes_in_this_connection'),
                            core_observation='not_read; reset during RAM-only sampling is not detectable')
        return self._run(operation)

    def Swd_Inspect(self, identifiers=()) -> SwdReply:
        """One bounded summary + watch sample. Existing core status explicitly
        consumes DHCSR sticky history bits; watch locations themselves are RAM.
        """
        return self.Swd_Diagnostics(identifiers)

    def Swd_Diagnostics(self, identifiers=()) -> SwdReply:
        def operation():
            try: fields = self._watch_selection(identifiers)
            except ValueError as exc: return SwdReply(SwdResult.InvalidRequest,str(exc))
            if self._firmware_status != 'matched' or self._firmware is None:
                return SwdReply(SwdResult.FirmwareMismatch, 'Diagnostic reads require a matched firmware in this connection')
            reply = self._snapshot(1.0 if fields else .1)
            if reply.result != SwdResult.Ok: return reply
            if reply.snapshot.core_state == 'reset_observed':
                self._firmware_status = 'unmatched'
                return SwdReply(SwdResult.FirmwareMismatch, 'Reset observed; reconnect and verify firmware again')
            from transport.swd_firmware import Contract_Get
            specs = {entry['id']:entry for entry in Contract_Get()['entries']}
            rows = []
            for entry in self._firmware.entries:
                spec = specs[entry.id]
                row = dict(id=entry.id,group=spec['group'],name=spec['name'],fields={},
                           state='UNKNOWN',reason=entry.unavailable,consistency=spec['consistency'])
                if entry.fields:
                    lo = min(f.address for f in entry.fields)
                    hi = max(f.address+f.size for f in entry.fields)
                    if not self._profile.Contains(lo,hi-lo,'ram') or hi-lo > self.MAX_READ:
                        raise SwdError(SwdResult.InvalidRequest, 'Diagnostic row outside trusted RAM')
                    count = hi-lo+(8 if spec['consistency']=='sequence_even' else 0)
                    if self._bytes+count > self.MAX_BYTES:
                        raise SwdError(SwdResult.BudgetExceeded, 'Diagnostic RAM budget reached')
                    self._bytes += count
                    sequence = next((f for f in entry.fields if f.name=='sequence'),None)
                    before = self._read(sequence.address,4) if spec['consistency']=='sequence_even' else None
                    data = self._read(lo,hi-lo)
                    after = self._read(sequence.address,4) if before is not None else None
                    if before is not None and (before != after or int.from_bytes(before,'little') & 1):
                        row['reason'] = 'sequence_changed_or_writer_active'
                    else:
                        row['fields'] = {f.name:int.from_bytes(data[f.address-lo:f.address-lo+f.size],'little',signed=f.signed) for f in entry.fields}
                        if before is not None and row['fields']['sequence'] != int.from_bytes(before,'little'):
                            row['fields'] = {}; row['reason'] = 'sequence_changed'
                        else:
                            valid = bool(row['fields'].get(spec['valid']))
                            row['state'] = 'OBSERVED' if valid else 'UNKNOWN'
                            row['reason'] = 'ram_observation_not_readiness' if valid else 'not_published'
                row['received_ns'] = time.monotonic_ns()
                rows.append(row)
            from dataclasses import replace
            return replace(reply,diagnostics=tuple(rows),watches=self._watch_read(fields),
                           firmware_sha256=self._firmware.sha256,budget=self._budget_report(),
                           core_observation='CPUID / selected family ID / DHCSR; DHCSR consumes S_RESET_ST and S_RETIRE_ST')
        return self._run(operation)
