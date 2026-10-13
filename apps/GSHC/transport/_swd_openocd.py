"""Private MEM-AP/GDB-pipe adapter. Never use a cortex_m or board script.

Live admission intentionally remains closed until exact executable provenance,
reset-pin behaviour and exclusive probe ownership have been reviewed. There is
no user flag/environment variable to bypass this policy.
"""
from collections import deque
import hashlib
from pathlib import Path
import queue
import shutil
import subprocess
from threading import Event, Lock, Thread
import time

from transport.swd_session import SwdError, SwdResult, _ValidateProbe

# No executable has yet met the three admission requirements above. A future
# reviewed change must include provenance and ownership evidence, not just a hash.
_ADMITTED_EXECUTABLES = frozenset()
_STARTUP_MARKER = 'SILVERSTAR_MEM_AP_INIT_COMPLETE'


def _Configuration(probe):
    _ValidateProbe(probe)
    return [
        'adapter driver cmsis-dap', 'cmsis-dap backend usb_bulk',
        # The reviewed Horco profile exposes the bulk DAP interface as MI_00.
        # Never let a future multi-interface descriptor silently choose another.
        'cmsis-dap usb interface 0',
        'cmsis-dap vid_pid 0xfaed 0x4870', f'adapter serial {probe.serial}',
        'transport select swd', 'adapter speed 100', 'reset_config none',
        'gdb port pipe', 'tcl port disabled', 'telnet port disabled',
        'swd newdap ss cpu -expected-id 0x2ba01477',
        'dap create ss.dap -chain-position ss.cpu',
        'target create ss.mem mem_ap -dap ss.dap -ap-num 0 -gdb-port pipe',
        # mem_ap state is synthetic. It is never used as the CPU running state.
        'ss.mem configure -event gdb-attach {}',
        'ss.mem configure -event gdb-detach {}',
        'init',
    ]


class OpenOcdMemAp:
    TIMEOUT = 5.0
    MAX_PACKET = 4096

    def __init__(self, cancel):
        self.cancel = cancel
        self.process = None
        self._input = queue.Queue(maxsize=8192)
        self._overflow = Event()
        self._threads = []
        self._logs = deque(maxlen=32)
        self._startup = Event()
        self._failure = None
        self._submission_lock = Lock()

    def open(self, probe):
        commands = _Configuration(probe)
        executable = shutil.which('openocd')
        if executable is None:
            raise SwdError(SwdResult.MissingDependency, 'OpenOCD executable not found on PATH')
        # Check policy before Popen, USB enumeration, network binding or device open.
        digest = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
        if digest not in _ADMITTED_EXECUTABLES:
            raise SwdError(SwdResult.SafetyNotProven,
                'Live SWD blocked before opening a probe: exact OpenOCD provenance, '
                'reset-pin preservation and exclusive ownership are not proven. '
                f'Executable SHA256={digest}')
        arguments = [executable]
        for command in commands + ['echo ' + _STARTUP_MARKER]:
            arguments += ['-c', command]
        self._start(arguments)

    def _start(self, arguments):
        """Private launch seam used with synthetic child processes in tests.

        This barrier prevents API publication after a reported claim failure.
        It cannot make an external OpenOCD claim fail-stop before DAP traffic.
        """
        self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._threads = [Thread(target=self._receive, daemon=True),
                         Thread(target=self._receive_log, daemon=True)]
        for thread in self._threads:
            thread.start()
        deadline = time.monotonic() + self.TIMEOUT
        while time.monotonic() < deadline:
            self._check_failure()
            if self._startup.is_set():
                return
            self._startup.wait(.05)
        raise SwdError(SwdResult.Timeout, 'Debugger startup exceeded 5 seconds; no retry')

    def _receive(self):
        try:
            while True:
                value = self.process.stdout.read(1)
                if not value:
                    break
                try:
                    self._input.put_nowait(value)
                except queue.Full:
                    self._overflow.set()
                    break
        except (OSError, ValueError):
            pass
        finally:
            try:
                self._input.put_nowait(b'')
            except queue.Full:
                self._overflow.set()

    def _receive_log(self):
        pending = bytearray()
        try:
            while True:
                value = self.process.stderr.read(512)
                if not value:
                    break
                self._logs.append(value)
                pending.extend(value)
                while b'\n' in pending:
                    line, _, pending = pending.partition(b'\n')
                    self._log_line(line)
                if len(pending) > 4096:
                    self._log_line(pending)
                    pending.clear()
        except (OSError, ValueError):
            pass
        finally:
            if pending:
                self._log_line(pending)
            if not self._startup.is_set() and self._failure is None:
                self._failure = SwdError(SwdResult.TransportError, 'Debugger closed before initialization completed')

    def _log_line(self, raw):
        line = bytes(raw).decode('utf-8', errors='replace').strip()
        lower = line.lower()
        # Claim failure is terminal even when OpenOCD only labels it a warning.
        claim_failed = 'could not claim interface' in lower or 'failed to claim interface' in lower
        busy = 'libusb_error_busy' in lower or 'resource busy' in lower
        if claim_failed or busy:
            with self._submission_lock:
                if self._failure is None:
                    self._failure = SwdError(SwdResult.Busy if busy else SwdResult.TransportError,
                                             'Debugger claim refused: ' + line[:400])
        if line == _STARTUP_MARKER:
            self._startup.set()

    def _check_failure(self):
        if self.cancel.is_set():
            raise SwdError(SwdResult.Cancelled, 'SWD operation cancelled')
        if self._failure is not None:
            raise self._failure

    def _byte(self, deadline):
        while time.monotonic() < deadline:
            self._check_failure()
            if self._overflow.is_set():
                raise SwdError(SwdResult.TransportError, 'Debugger pipe overflow')
            try:
                value = self._input.get(timeout=min(.05, max(.001, deadline-time.monotonic())))
            except queue.Empty:
                continue
            if not value:
                detail = b''.join(self._logs).decode('utf-8', errors='replace')[-1000:]
                raise SwdError(SwdResult.TransportError, 'Debugger pipe closed: ' + detail)
            return value
        raise SwdError(SwdResult.Timeout, 'SWD operation exceeded 5 seconds; no retry')

    def _exchange(self, payload):
        # The only emitted RSP request is a bounded memory read. No monitor, run
        # control, registers, flash packets or user-supplied packet path exists.
        packet = b'$' + payload + b'#' + f'{sum(payload) & 255:02x}'.encode('ascii')
        try:
            with self._submission_lock:
                self._check_failure()
                self.process.stdin.write(packet)
                self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise SwdError(SwdResult.TransportError, str(exc)) from exc
        deadline = time.monotonic() + self.TIMEOUT
        # OpenOCD may emit console packets; cap their count and total wait.
        for _ in range(16):
            start = self._byte(deadline)
            if start == b'+':
                start = self._byte(deadline)
            if start != b'$':
                raise SwdError(SwdResult.TransportError, 'Unexpected RSP framing; no retransmission')
            body = bytearray()
            for _ in range(self.MAX_PACKET):
                value = self._byte(deadline)
                if value == b'#':
                    break
                body.extend(value)
            else:
                raise SwdError(SwdResult.TransportError, 'RSP packet too long')
            checksum = self._byte(deadline) + self._byte(deadline)
            if checksum.lower() != f'{sum(body) & 255:02x}'.encode('ascii'):
                raise SwdError(SwdResult.TransportError, 'RSP checksum mismatch')
            self.process.stdin.write(b'+')
            self.process.stdin.flush()
            if body.startswith(b'O'):
                continue
            return bytes(body)
        raise SwdError(SwdResult.TransportError, 'Too many console packets')

    def read(self, address, length):
        # Defence in depth: internal adapter must not grow arbitrary MMIO access.
        from transport.swd_session import SwdSession
        if type(address) is not int or type(length) is not int or not 1 <= length <= 1024:
            raise SwdError(SwdResult.InvalidRequest, 'Invalid memory read size or address')
        ram = any(lo <= address < address+length <= hi for lo, hi in SwdSession._RAM)
        diagnostic = length == 4 and address in (0xE000ED00, 0xE0042000, 0xE000EDF0)
        if type(address) is not int or type(length) is not int or not 1 <= length <= 1024 or not (ram or diagnostic):
            raise SwdError(SwdResult.InvalidRequest, 'Memory read outside the approved map')
        response = self._exchange(f'm{address:x},{length:x}'.encode('ascii'))
        if len(response) != length * 2 or any(c not in b'0123456789abcdefABCDEF' for c in response):
            raise SwdError(SwdResult.TransportError, 'Memory read rejected or malformed')
        return bytes.fromhex(response.decode('ascii'))

    def close(self):
        process = self.process
        if process is None:
            return
        # EOF ends pipe service. Do not send GDB D (resume semantics vary), kill,
        # monitor shutdown/reset, or anything to the MCU. terminate/kill below
        # refer only to this owned host child process, never a debug command.
        errors = []
        if process.stdin and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass  # A dead child must still be reaped and the other pipes closed.
            except Exception as exc:
                errors.append('stdin: ' + str(exc))
        try:
            process.wait(timeout=.3)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
            except OSError as exc:
                if process.poll() is None:
                    errors.append('terminate: ' + str(exc))
            try:
                process.wait(timeout=.7)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=1)
                except Exception as exc:
                    errors.append('kill/reap: ' + str(exc))
            except Exception as exc:
                errors.append('reap after terminate: ' + str(exc))
                try:
                    process.kill()
                    process.wait(timeout=1)
                except Exception as failure:
                    errors.append('kill/reap: ' + str(failure))
        except Exception as exc:
            errors.append('reap: ' + str(exc))
            try:
                process.kill()
                process.wait(timeout=1)
            except Exception as failure:
                errors.append('kill/reap: ' + str(failure))
        for thread in self._threads:
            if thread.ident is not None:
                try:
                    thread.join(timeout=.2)
                except RuntimeError as exc:
                    errors.append('reader join: ' + str(exc))
        for stream in (process.stdout, process.stderr):
            if stream:
                try:
                    stream.close()
                except Exception as exc:
                    errors.append('pipe: ' + str(exc))
        if process.stdin and not process.stdin.closed:
            errors.append('Owned debugger stdin still open')
        if process.poll() is None:
            errors.append('Owned debugger process still running')
        if any(t.is_alive() for t in self._threads):
            errors.append('Pipe reader did not stop')
        if errors:
            raise SwdError(SwdResult.ReleaseFailed, '; '.join(errors)[:600])
        self.process = None
