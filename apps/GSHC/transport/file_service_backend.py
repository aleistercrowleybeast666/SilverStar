"""Exclusive maintenance UART/USB Console; constructed only in a worker thread."""
from __future__ import annotations

import logging
import re
import time
from threading import Event

import serial
from services.device_export import ExportCancelled
from transport.serial_options import SerialBaud_Parse


_logger = logging.getLogger(__name__)


class BlockReceiveTimeout(TimeoutError):
    """Only a frame receive deadline, never a transaction/cancellation budget."""
    recovery_kind = 'timeout'


class BlockFramingError(OSError):
    """A damaged binary boundary; recovery requires a new correlated frame."""
    recovery_kind = 'framing'


class FileServiceSerialTransport:
    def __init__(self, port: str, baudrate: int, *, serial_factory=serial.Serial) -> None:
        if not port.strip() or type(baudrate) is not int or SerialBaud_Parse(str(baudrate)) == 0:
            raise ValueError("Select an explicit maintenance UART/USB port and baud rate")
        self._serial = serial_factory(port=port, baudrate=baudrate, timeout=0.05, write_timeout=0.5)
        self.baudrate = baudrate
        self.receive_observer = None  # Called only by the serial owner thread.
        self.trace = None  # Optional bounded recorder, attached by the owner.
        self._buffer = bytearray()
        self._needs_sync = True
        self._sync_failed = False
        self._pending_command = ''
        self._requests = {}
        self.startup_diagnostics = {"performed": False, "authoritative": False,
                                    "quarantined_bytes": 0, "raw_hex": ""}
        self._installation_pending = None
        self.installation_quarantine = []

    def _read(self, size):
        available = getattr(self._serial,'in_waiting',None)
        count = min(size,max(1,available)) if type(available) is int else size
        data = self._serial.read(count)
        trace = getattr(self,'trace',None)
        if data and trace is not None:
            trace.raw('rx',data)
        observer = getattr(self, 'receive_observer', None)
        if data and observer is not None:
            observer(data)
        return data

    def _write(self, payload):
        written = self._serial.write(payload)
        trace = getattr(self,'trace',None)
        if trace is not None:
            trace.raw('tx',payload[:max(0,written)])
        return written

    def close(self) -> None:
        self._serial.close()

    @property
    def requires_reconnect(self):
        return self._sync_failed

    def prepare_job(self) -> None:
        # Called by the sole owner only after the previous transaction ended.
        self._needs_sync = True

    def _synchronize(self, cancel: Event) -> None:
        if self._sync_failed:
            raise OSError("Maintenance startup synchronization failed; reconnect required"
                          + " [last incomplete command: " + self._pending_command + "]")
        if not self._needs_sync:
            return
        self._sync_failed = True
        self._pending_command = 'startup SYSTEM INFO probe'
        received = bytearray(self._buffer)
        self._buffer.clear()
        # Some bridges expose an old partial packet only when new target output
        # arrives. An idle drain/PurgeComm cannot establish this boundary.
        # This one read-only probe is quarantined, never used as identity/status.
        probe = b"SYSTEM INFO\r\n"
        if self._write(probe) != len(probe):
            raise OSError("Incomplete maintenance synchronization probe write")
        started = quiet_since = time.monotonic()
        seen_response = False
        probe_attempts = 1
        while time.monotonic() - started < 2.0:
            if cancel.is_set():
                raise ExportCancelled("Maintenance operation cancelled")
            chunk = self._read(128)
            now = time.monotonic()
            if chunk:
                received.extend(chunk)
                self.startup_diagnostics.update(performed=True,
                    quarantined_bytes=len(received), raw_hex=bytes(received[:4096]).hex())
                if len(received) > 4096:
                    raise OSError("Maintenance synchronization stream exceeded its bound")
                quiet_since = now
                for marker in (b"OK SYSTEM INFO ", b"ERR SYSTEM INFO "):
                    index = received.find(marker)
                    if index >= 0 and b"\n" in received[index:]:
                        seen_response = True
            elif seen_response and now - quiet_since >= 0.1:
                if cancel.is_set():
                    raise ExportCancelled("Maintenance operation cancelled")
                self._needs_sync = self._sync_failed = False
                _logger.warning("Maintenance link resynchronized: %d initial bytes quarantined; "
                    "not identity/status; fresh request required; raw=%s",
                    len(received), bytes(received).hex())
                return
            # A bridge may drop the first write while its VCP is opening. Only
            # retry this read-only, non-authoritative probe, once, if no payload
            # arrived. A short CR/LF-only prefix is opening delimiter noise, not
            # a partial response; require quiet before retrying it. Every other
            # byte still blocks retry. Keep the original deadline and quarantine
            # late/duplicate probe replies before any fresh service request.
            empty_probe = len(received) <= 64 and not received.strip(b'\r\n')
            if (empty_probe and probe_attempts == 1 and now - started >= 1.0
                    and now - quiet_since >= 0.1):
                if cancel.is_set():
                    raise ExportCancelled("Maintenance operation cancelled")
                probe_attempts = 2
                self.startup_diagnostics.update(performed=True, probe_attempts=2)
                if self._write(probe) != len(probe):
                    raise OSError("Incomplete maintenance synchronization probe write")
        reason = ('no_response_payload' if not received.strip(b'\r\n') else
                  'incomplete_or_wrong_response' if not seen_response else 'no_quiet_boundary')
        self.startup_diagnostics.update(failure_reason=reason, probe_attempts=probe_attempts)
        raise TimeoutError("Maintenance synchronization probe did not finish/quiet; no service request sent"
                           f" [reason={reason}; rx_bytes={len(received)}; probes={probe_attempts}]")

    def check_alive(self) -> None:
        # A bounded idle read detects unplug/driver errors in the owner thread.
        self._read(128)

    def installation_exchange(self, payload, deadline, cancel):
        """Bounded event+reply exchange; only the sole serial owner may call it.

        No generic exchange retry, extra reader or business fallback is used.
        A tainted exchange permits only correlated CANCEL/its POLL cleanup.
        """
        from services.installation_calibration_protocol import Request_Decode, Response_Decode
        request = Request_Decode(payload.removesuffix(b"\r\n"))
        op, args = request.operation, request.arguments
        if type(deadline) not in (int,float) or not 0<deadline-time.monotonic()<=120:
            raise ValueError("INSTALLATION_DEADLINE")
        if cancel.is_set(): raise ExportCancelled("Installation exchange cancelled")
        sid = args[0] if op in ("BEGIN","FACE","POLL","DO","STATUS") else None
        rid = args[1] if op in ("BEGIN","FACE","POLL","DO") else None
        cleanup = op=="DO" or (op=="POLL" and self._installation_pending==("DO",sid,rid))
        if self._sync_failed and not cleanup: raise OSError("INSTALLATION_RECONNECT_REQUIRED")
        if self._needs_sync: self._synchronize(cancel)
        if time.monotonic()>=deadline: raise TimeoutError("INSTALLATION_SYNC_DEADLINE")
        if op in ("FACE","DO"): self._installation_pending=(op,sid,rid)
        expected = self._installation_pending[0] if op=="POLL" and self._installation_pending else op
        if op=="POLL" and self._installation_pending!=(expected,sid,rid):
            raise ValueError("INSTALLATION_POLL_CONTEXT")
        self._sync_failed=True
        self._pending_command='INSTALL '+op
        if self._write(payload)!=len(payload): raise OSError("Incomplete installation command write")
        events=[]; discarded=0
        while time.monotonic()<deadline:
            if cancel.is_set(): raise ExportCancelled("Installation exchange cancelled")
            self._buffer.extend(self._read(128))
            if len(self._buffer)>1024: raise OSError("INSTALLATION_BUFFER_LIMIT")
            while b"\n" in self._buffer:
                raw,_,remaining=self._buffer.partition(b"\n");self._buffer=bytearray(remaining)
                line=bytes(raw).removesuffix(b"\r")
                if not line: continue
                if len(line)>511 or not line.isascii(): raise OSError("INSTALLATION_LINE_LIMIT")
                if line.startswith(b"EVENT INSTALL "):
                    fields=dict(item.split(b"=",1) for item in line.split()[3:] if b"=" in item)
                    if sid is not None and fields.get(b"sid")==sid.encode():
                        events.append(line)
                        if len(events)>127: raise OSError("INSTALLATION_BATCH_LIMIT")
                        continue
                else:
                    try: reply=Response_Decode(line,expected,sid,rid)
                    except ValueError: reply=None
                    if reply is not None:
                        if cancel.is_set(): raise ExportCancelled("Installation cancelled at matched reply")
                        if time.monotonic()>=deadline: raise TimeoutError("INSTALLATION_LATE_REPLY")
                        self._sync_failed=False
                        return tuple(events+[line])
                    if op=="CAPS" and line.startswith(b"ERR SYSTEM PARSE "):
                        self._sync_failed=False
                        return (line,)
                discarded+=1
                self.installation_quarantine.append(line.hex())
                if len(self.installation_quarantine)>32: self.installation_quarantine.pop(0)
                if discarded>32: raise OSError("INSTALLATION_UNRELATED_LIMIT")
        raise TimeoutError("Installation response timed out; outcome unknown")

    def exchange(self, command: str, timeout: float, cancel: Event) -> str:
        started = time.monotonic()
        response = error = ''
        try:
            response = self._exchange(command,timeout,cancel)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            trace = getattr(self,'trace',None)
            if trace is not None:
                trace.exchange(command,response,time.monotonic()-started,error)

    def _exchange(self, command: str, timeout: float, cancel: Event) -> str:
        if cancel.is_set():
            raise ExportCancelled("Maintenance operation cancelled")
        if not command or len(command) > 191 or not command.isascii() or any(ord(c)<32 or ord(c)==127 for c in command):
            raise ValueError("Invalid maintenance command")
        from services.maintenance_commands import ConsoleCommand_ResponsePrefix
        try:
            console_prefix = ConsoleCommand_ResponsePrefix(command)
        except ValueError:
            console_prefix = None
        self._synchronize(cancel)
        # After any incomplete exchange, a late reply must never become the next
        # operation's evidence. Only accepting a complete correlated line clears it.
        self._sync_failed = True
        self._pending_command = command
        payload = (command + "\r\n").encode("ascii")
        if self._write(payload) != len(payload):
            raise OSError("Incomplete maintenance command write")
        deadline = time.monotonic() + timeout
        discarded = 0
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise ExportCancelled("Maintenance operation cancelled")
            chunk = self._read(128)
            self._buffer.extend(chunk)
            if len(self._buffer) > 1024:
                raise OSError("Maintenance response buffer exceeded its bound")
            while True:
                item = self._Reply_Next()
                if item is None:
                    break
                kind, raw = item
                if kind == 'block':
                    # A bounded stale/replayed frame is quarantined, never text.
                    discarded += 1
                    if discarded > 4:
                        raise OSError('Too many unrelated binary blocks')
                    continue
                line = raw.decode("ascii", errors="strict").strip()
                line = line.removeprefix('> ')
                if command == "LOGFILE CAPS" and line.startswith("ERR "):
                    words=line.split()
                    codes={word.partition('=')[2] for word in words[3:] if word.startswith('code=')}
                    if words[1:3] in (['SYSTEM','PARSE'],['LOGFILE','PARSE']) and codes & {'BAD_MODULE','BAD_COMMAND','UNSUPPORTED'}:
                        self._sync_failed = False
                        return line
                if console_prefix is not None and not command.startswith("LOGFILE "):
                    matched_command = console_prefix
                    for prefix in ("OK " + matched_command + " ", "ERR " + matched_command + " "):
                        if line.startswith(prefix) or line.startswith("> " + prefix):
                            self._sync_failed = False
                            return line.removeprefix("> ")
                    # A generic parse error is unavailable, never a status.
                    if line.startswith("ERR "):
                        self._sync_failed = False
                        return line
                    discarded += 1
                    if discarded > 32:
                        raise OSError("Too many unrelated maintenance lines")
                    continue
                # Console may emit a prompt, command echo or diagnostic line.
                # Only complete protocol responses are returned to the client.
                if self._FileReply_Matches(command, line):
                    self._sync_failed = False
                    return line
                discarded += 1
                if discarded > 32:
                    raise OSError("Too many unrelated maintenance lines")
        raise TimeoutError("Maintenance response timed out; reconnect and renegotiate")

    def _Reply_Next(self):
        """Extract one bounded line or zero-delimited COBS record, without decoding."""
        from services.file_service_block import WIRE_LIMIT
        if not self._buffer:
            return None
        if self._buffer[0] == 0:
            end = self._buffer.find(0, 1)
            if end < 0:
                if len(self._buffer) >= WIRE_LIMIT:
                    raise BlockFramingError('Oversized binary block')
                return None
            if end + 1 > WIRE_LIMIT or end == 1:
                raise BlockFramingError('Invalid binary block extent')
            raw = bytes(self._buffer[1:end])
            del self._buffer[:end+1]
            return 'block', raw
        end = self._buffer.find(b'\n')
        zero = self._buffer.find(0)
        if zero >= 0 and (end < 0 or zero < end):
            raise BlockFramingError('Unframed bytes before binary block; reconnect required')
        if end < 0:
            if len(self._buffer) > 512:
                raise OSError('Oversized maintenance response')
            return None
        if end > 511:
            raise OSError('Oversized maintenance response')
        raw = bytes(self._buffer[:end])
        del self._buffer[:end+1]
        return 'line', raw

    def block_poll(self, request_id: int, timeout: float, cancel: Event):
        """Sole-owner POLL: full corrupt frames may replay; truncation taints the link."""
        key = str(request_id)
        if self._requests.get(key) != 'BLOCK':
            raise ValueError('No correlated BLOCK request')
        self._synchronize(cancel)
        if cancel.is_set():
            raise ExportCancelled('Block transfer cancelled')
        command = f'LOGFILE POLL {request_id}'
        self._sync_failed = True
        self._pending_command = command
        payload = (command + '\r\n').encode('ascii')
        if self._write(payload) != len(payload):
            raise OSError('Incomplete BLOCK POLL write')
        return self._Block_Receive(request_id, timeout, cancel, command)

    def batch_receive(self, request_id: int, timeout: float, cancel: Event):
        """Receive one negotiated batch record without sending per-block POLL."""
        if self._requests.get(str(request_id)) != 'BATCH' or self._sync_failed:
            raise ValueError('No usable correlated BATCH request')
        self._sync_failed = True
        self._pending_command = f'LOGFILE BATCH receive {request_id}'
        return self._Block_Receive(request_id, timeout, cancel, f'LOGFILE POLL {request_id}')

    def _Block_Receive(self, request_id, timeout, cancel, command):
        deadline = time.monotonic() + min(30.0, max(0.001, timeout))
        discarded = 0
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise ExportCancelled('Block transfer cancelled')
            item = self._Reply_Next()
            if item is None:
                self._buffer.extend(self._read(128))
                if len(self._buffer) > 1024:
                    raise OSError('Block response buffer limit')
                continue
            kind, raw = item
            if kind == 'block':
                from services.file_service_block import Block_Decode
                try:
                    decoded = Block_Decode(raw)
                except ValueError:
                    decoded = None  # Client checks integrity before any file write.
                if decoded is not None and decoded.request_id != request_id:
                    discarded += 1
                    if discarded > 4:
                        raise OSError('Too many stale BLOCK completions')
                    continue
                self._sync_failed = False
                return raw
            line = raw.decode('ascii', errors='strict').strip()
            if self._FileReply_Matches(command, line):
                self._sync_failed = False
                return line
            discarded += 1
            if discarded > 8:
                raise OSError('Too many unrelated BLOCK replies')
        raise BlockReceiveTimeout('Incomplete BLOCK response; reconnect required')

    def batch_recover(self, request_id, command, expected, deadline, cancel):
        """Drain one bounded BATCH, then prove a new nonce/CRC/identity boundary.

        Text and quiet time only bound quarantine; neither proves synchronization.
        Only a complete matching new-nonce first frame restores normal parsing.
        Firmware admits a new BATCH only after the previous producer finishes.
        CANCEL is reserved for abort: it invalidates the firmware META cache.
        No PurgeComm, input flush, port reopen, baud change or deadline renewal.
        """
        if self._requests.get(str(request_id)) != 'BATCH' or not self._sync_failed:
            raise ValueError('No damaged owned BATCH to recover')
        fields = command.split()
        transfer, sequence, file_id, whole, size, offset = expected
        if (len(fields) != 7 or fields[:2] != ['LOGFILE', 'BATCH']
                or len(command) > 191 or not command.isascii()
                or any(ord(c) < 32 or ord(c) == 127 for c in command)
                or (int(fields[5], 16), int(fields[6]), int(fields[2]), int(fields[4]))
                != (transfer, sequence, file_id, offset)):
            raise ValueError('Invalid BATCH recovery identity')
        started = time.monotonic()
        record = dict(previous_request=request_id, offset=offset,
                      transfer=f'{transfer:016X}', initial_buffer_hex=bytes(self._buffer).hex(),
                      discarded_candidates=0, received_bytes=0, outcome='failed')
        try:
            self._Recovery_Drain(min(deadline, started + 2.0), cancel, record)
            if cancel.is_set():
                raise ExportCancelled('Batch recovery cancelled')
            if time.monotonic() >= deadline:
                raise TimeoutError('BATCH recovery absolute deadline')
            payload = (command + '\r\n').encode('ascii')
            if self._write(payload) != len(payload):
                raise OSError('Incomplete recovery BATCH write')
            raw, block = self._Recovery_FirstFrame(
                expected, request_id, min(deadline, time.monotonic() + 2.0), cancel, record)
            if cancel.is_set():
                raise ExportCancelled('Batch recovery cancelled at matched frame')
            if time.monotonic() >= deadline:
                raise TimeoutError('Late recovered BATCH frame')
            self._requests.pop(str(request_id))
            self._requests[str(block.request_id)] = 'BATCH'
            # Re-feed this independently verified first record to the client,
            # which applies its normal per-record and whole-file checks.
            self._buffer[:0] = b'\0' + raw + b'\0'
            self._sync_failed = False
            record.update(outcome='new_nonce_frame_verified', request_id=block.request_id)
            return block.request_id
        except Exception:
            # This request owns the lease. Stop any replacement producer, even
            # when the local cancellation flag is set; no success is inferred.
            try:
                self._write(b'LOGFILE CANCEL\r\n')
                record['abort_sent'] = True
            except OSError as error:
                record['abort_error'] = str(error)
            raise
        finally:
            record['seconds'] = time.monotonic() - started
            if self.trace is not None:
                self.trace.event('batch_recovery', **record)

    def _Recovery_Drain(self, deadline, cancel, record):
        quarantined = bytearray(self._buffer)
        self._buffer.clear()
        command = b'SYSTEM INFO\r\n'
        if cancel.is_set():
            raise ExportCancelled('Batch recovery cancelled')
        if self._write(command) != len(command):
            raise OSError('Incomplete recovery quarantine probe write')
        quiet_since = time.monotonic()
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise ExportCancelled('Batch recovery cancelled')
            chunk = self._read(128)
            if chunk:
                quarantined.extend(chunk)
                quiet_since = time.monotonic()
                if len(quarantined) > 4096:
                    raise OSError('BATCH quarantine byte limit')
            elif (time.monotonic() - quiet_since >= .1
                  and b'OK SYSTEM INFO ' in quarantined
                  and b'\n' in quarantined[quarantined.find(b'OK SYSTEM INFO '):]):
                record['quarantined_bytes'] = len(quarantined)
                record['quarantine_hex'] = quarantined.hex()
                return  # A drain hint only. Fresh binary identity is still required.
        raise TimeoutError('BATCH quarantine probe did not finish')

    def _Recovery_FirstFrame(self, expected, old_request, deadline, cancel, record):
        from services.file_service_block import Block_Decode, WIRE_LIMIT
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise ExportCancelled('Batch recovery cancelled')
            start = self._buffer.find(0)
            if start < 0:
                if len(self._buffer) > 512:
                    raise OSError('BATCH recovery text limit')
            else:
                del self._buffer[:start]  # Retained in bounded trace; never authoritative.
                end = self._buffer.find(0, 1)
                if end >= 0:
                    raw = bytes(self._buffer[1:end])
                    del self._buffer[:end]  # This zero may also start the next candidate.
                    if not raw:
                        continue
                    record['discarded_candidates'] += 1
                    if record['discarded_candidates'] > 12:
                        raise OSError('BATCH recovery candidate limit')
                    try:
                        block = Block_Decode(raw)
                    except ValueError:
                        continue
                    identity = (block.transfer, block.sequence, block.file_id,
                                block.whole_crc, block.size, block.offset)
                    if block.transfer == expected[0]:
                        if identity != expected or block.request_id <= old_request:
                            raise ValueError('Recovered BATCH identity/offset mismatch')
                        record['discarded_candidates'] -= 1
                        del self._buffer[:1]  # Valid record's ending delimiter.
                        return raw, block
                    continue  # Complete late record with the revoked old nonce.
                if len(self._buffer) >= WIRE_LIMIT:
                    raise OSError('BATCH recovery candidate extent limit')
            chunk = self._read(128)
            record['received_bytes'] += len(chunk)
            if record['received_bytes'] > 8192:
                raise OSError('BATCH recovery byte limit')
            self._buffer.extend(chunk)
        raise BlockReceiveTimeout('No complete new-nonce BATCH frame before recovery deadline')

    def block_complete(self, request_id: int):
        if self._requests.pop(str(request_id), None) != 'BLOCK':
            raise ValueError('BLOCK completion context changed')

    def batch_complete(self, request_id: int):
        if self._requests.pop(str(request_id), None) != 'BATCH':
            raise ValueError('BATCH completion context changed')

    def block_invalidate(self):
        self._sync_failed = True
        self._pending_command = 'BLOCK absolute transaction deadline'

    def batch_abort(self, request_id):
        """Best-effort revocation of this owner's batch; no cleanup claim."""
        if self._requests.get(str(request_id)) != 'BATCH':
            return
        self._sync_failed = True
        try:
            written = self._write(b'LOGFILE CANCEL\r\n')
            if written != len(b'LOGFILE CANCEL\r\n'):
                raise OSError('Incomplete BATCH abort write')
        except OSError:
            _logger.exception('BATCH cancellation unconfirmed; reconnect required')
        if self.trace is not None:
            self.trace.event('batch_abort', request_id=request_id, cleanup_confirmed=False)

    def _FileReply_Matches(self, command, line):
        parts, reply = command.split(), line.split()
        if len(parts)<2 or len(reply)<3 or reply[0] not in ('OK','ERR','PENDING') or reply[1]!='LOGFILE':
            return False
        op = parts[1]
        fields = dict(pair.split('=',1) for pair in reply[3:] if '=' in pair)
        request_id = fields.get('request_id','')
        if op=='POLL':
            if len(parts)!=3 or request_id!=parts[2]:return False
            expected = self._requests.get(request_id)
            if expected is not None and reply[2]!=expected:return False
        elif reply[2]!=op:
            return False
        elif op in ('LIST','META','READ','BLOCK','BATCH') and reply[0]!='ERR':
            # Submission must acknowledge a new bounded asynchronous request.
            if reply[0]!='PENDING' or not re.fullmatch(r'[1-9][0-9]{0,9}',request_id):return False
            if request_id in self._requests:return False
            self._requests[request_id]=op
            if len(self._requests)>32:
                raise OSError('Too many outstanding maintenance requests')
        if op=='POLL' and reply[0]!='PENDING':self._requests.pop(request_id,None)
        if op=='CANCEL' and reply[0]=='OK':self._requests.clear()
        return True


__all__ = ["FileServiceSerialTransport"]
