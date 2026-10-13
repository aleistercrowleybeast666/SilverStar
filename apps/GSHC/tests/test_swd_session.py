"""Synthetic target only. These tests never open a USB, HID, serial or SWD device."""
from dataclasses import replace
import io
import queue
from threading import Event
from unittest.mock import Mock, patch
import pytest

from transport.probe_inventory import HostProbe, ProbeInventory, ProbeInventoryResult
from transport.swd_session import SwdSession, SwdResult as R, SwdError
from transport._swd_openocd import OpenOcdMemAp, _Configuration


PROBE = HostProbe(r'USB\VID_FAED&PID_4870\123', 'Horco CMSIS-DAP', 'CMSIS-DAP',
                  'FAED:4870', '123', 'USB serial', ('WINUSB',), 'OK')


class FakeMemory:
    def __init__(self, cancel):
        self.cancel = cancel
        self.opened = self.closed = 0
        self.reads = []
        self.failure = None
        self.words = {0xE000ED00: 0x410FC241, 0xE0042000: 0x10016413, 0xE000EDF0: 0}

    def open(self, probe):
        self.opened += 1

    def read(self, address, length):
        self.reads.append((address, length))
        if self.failure:
            raise self.failure
        return self.words.get(address, 0).to_bytes(4, 'little') if address in self.words else bytes(length)

    def close(self):
        self.closed += 1


def connected():
    backend = FakeMemory(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    reply = session.Swd_Attach(PROBE)
    assert reply.result == R.Ok
    return session, backend, reply


def tick(session):
    session._last_sample -= 1


@pytest.mark.parametrize('dhcsr,state', [(0, 'running'), (1 << 17, 'halted'),
    (1 << 18, 'sleeping'), (1 << 19, 'lockup'), (1 << 25, 'reset_observed')])
def test_identification_state_and_detach_never_run_control(dhcsr, state):
    backend = FakeMemory(Event()); backend.words[0xE000EDF0] = dhcsr
    session = SwdSession(_backend_factory=lambda _: backend)
    reply = session.Swd_Attach(PROBE)
    assert reply.result == R.Ok and reply.snapshot.core_state == state
    assert reply.snapshot.target == 'STM32F405/407/415/417'
    assert reply.snapshot.symbols == 'unmatched'
    assert reply.snapshot.consistency == 'non_atomic_live_read' and reply.snapshot.age_ms >= 0
    assert backend.reads == [(0xE000ED00, 4), (0xE0042000, 4), (0xE000EDF0, 4)]
    assert session.Swd_Detach().result == session.Swd_Detach().result == R.Ok
    assert backend.closed == 1 and backend.words[0xE000EDF0] == dhcsr
    assert session.Swd_Snapshot().result == R.NotAttached


@pytest.mark.parametrize('probe,result', [(None, R.InvalidRequest),
    (replace(PROBE, serial='123;reset'), R.Unsupported),
    (replace(PROBE, identity='USB\\other'), R.InvalidRequest),
    (replace(PROBE, family='J-Link'), R.Unsupported),
    (replace(PROBE, usb_id='0483:3748'), R.Unsupported),
    (replace(PROBE, identity_kind='location'), R.Unsupported)])
def test_probe_admission_before_backend_creation(probe, result):
    factory = Mock()
    assert SwdSession(_backend_factory=factory).Swd_Attach(probe).result == result
    factory.assert_not_called()


@pytest.mark.parametrize('address,length', [(0x40000000, 4), (0x08000000, 16),
    (0xE000ED00, 4), (0x2001FFFF, 2), (0x1000FFFF, 2), (0x20000000, 1025),
    (0x20000000, 0), (True, 4), (0x20000000, True), ('bad', 4), (-1, 4)])
def test_ram_validation_has_no_backend_access(address, length):
    session, backend, _ = connected()
    count = len(backend.reads)
    assert session.Swd_ReadMemory(address, length).result == R.InvalidRequest
    assert len(backend.reads) == count and backend.closed == 0
    session.Swd_Detach()


@pytest.mark.parametrize('address,length', [(0x20000000, 1024), (0x2001FFFF, 1), (0x10000000, 64)])
def test_bounded_ram_returns_raw_bytes_without_symbols(address, length):
    session, backend, _ = connected(); tick(session)
    reply = session.Swd_ReadMemory(address, length)
    assert reply.result == R.Ok and reply.data == bytes(length) and reply.address == address
    assert reply.received_ns and reply.consistency == 'non_atomic_live_read'
    assert not hasattr(session, 'write_memory') and not hasattr(session, 'reset')
    session.Swd_Detach()


def test_rate_busy_and_budget_do_not_queue_or_retry():
    session, backend, _ = connected()
    assert session.Swd_Snapshot().result == R.RateLimited
    assert len(backend.reads) == 3
    assert session._lock.acquire(False)
    assert session.Swd_Snapshot().result == session.Swd_Detach().result == R.Busy
    session._lock.release()
    assert session.Swd_Attach(PROBE).result == R.Busy and backend.opened == 1
    session._bytes = session.MAX_BYTES
    assert session.Swd_Snapshot().result == R.BudgetExceeded and backend.closed == 1


@pytest.mark.parametrize('field,value', [('_samples',600), ('_started',0)])
def test_sample_and_time_limit_invalidate(field, value):
    session, backend, _ = connected(); setattr(session,field,value)
    assert session.Swd_Snapshot().result == R.BudgetExceeded and backend.closed == 1


@pytest.mark.parametrize('reason', [R.Timeout, R.Cancelled, R.TransportError])
def test_fault_invalidates_and_releases_without_retry(reason):
    session, backend, _ = connected(); tick(session)
    backend.failure = SwdError(reason, 'injected')
    assert session.Swd_Snapshot().result == reason
    assert backend.closed == 1 and len(backend.reads) == 4
    assert session.Swd_Snapshot().result == R.NotAttached


def test_cancellation_during_attach_and_context_exception_release():
    cancel = Event(); cancel.set(); factory = Mock()
    assert SwdSession(cancel=cancel,_backend_factory=factory).Swd_Attach(PROBE).result == R.Cancelled
    factory.assert_not_called()
    session, backend, _ = connected()
    with pytest.raises(ValueError):
        with session:
            raise ValueError('caller failed')
    assert backend.closed == 1


@pytest.mark.parametrize('address,value,count', [(0xE000ED00,0,1),(0xE0042000,0x419,2)])
def test_target_mismatch_stops_before_other_reads(address,value,count):
    backend = FakeMemory(Event()); backend.words[address] = value
    session = SwdSession(_backend_factory=lambda _:backend)
    assert session.Swd_Attach(PROBE).result == R.TargetMismatch
    assert len(backend.reads) == count and backend.closed == 1


def test_short_read_and_release_failure_reported_and_retryable():
    session, backend, _ = connected(); tick(session)
    backend.read = lambda *_:b'\0'
    assert session.Swd_Snapshot().result == R.TransportError and backend.closed == 1
    session, backend, _ = connected()
    original_close = backend.close
    backend.close = Mock(side_effect=OSError('injected release failure'))
    assert session.Swd_Detach().result == R.ReleaseFailed
    assert session.Swd_Attach(PROBE).result == R.Busy
    backend.close = original_close
    assert session.Swd_Detach().result == R.Ok


def test_live_adapter_is_blocked_before_process_or_device_open(tmp_path):
    executable = tmp_path/'openocd.exe'; executable.write_bytes(b'unaudited binary')
    with patch('transport._swd_openocd.shutil.which',return_value=str(executable)), patch('subprocess.Popen') as popen:
        reply = SwdSession().Swd_Attach(PROBE)
        assert reply.result == R.SafetyNotProven and 'SHA256=' in reply.detail
        popen.assert_not_called()
    with patch('transport._swd_openocd.shutil.which',return_value=None):
        assert SwdSession().Swd_Attach(PROBE).result == R.MissingDependency


def test_configuration_no_board_scripts_core_driver_or_network():
    commands = _Configuration(PROBE)
    assert 'reset_config none' in commands and 'cmsis-dap backend usb_bulk' in commands
    assert 'cmsis-dap usb interface 0' in commands
    assert 'gdb port pipe' in commands
    assert 'tcl port disabled' in commands and 'telnet port disabled' in commands
    assert any('mem_ap' in command and '-gdb-port pipe' in command for command in commands)
    assert not any(word in ' '.join(commands) for word in ('cortex_m','source ','reset halt','resume','flash ','3333'))


def adapter_response(payload):
    backend = OpenOcdMemAp(Event())
    backend.process = Mock(); backend.process.stdin = io.BytesIO()
    wire = b'+$' + payload + b'#' + f'{sum(payload)&255:02x}'.encode()
    for byte in wire: backend._input.put_nowait(bytes([byte]))
    return backend


def test_rsp_is_memory_read_only_and_checks_checksum():
    backend = adapter_response(b'01020304')
    assert backend.read(0x20000000,4) == b'\x01\x02\x03\x04'
    assert backend.process.stdin.getvalue().startswith(b'$m20000000,4#')
    backend = adapter_response(b'01020304')
    with backend._input.mutex:
        backend._input.queue[-1] = b'Z'
    with pytest.raises(SwdError,match='checksum'): backend.read(0x20000000,4)


@pytest.mark.parametrize('payload', [b'E01',b'',b'zzzzzzzz',b'0011'])
def test_rsp_rejects_error_short_or_malformed_memory(payload):
    backend = adapter_response(payload)
    with pytest.raises(SwdError): backend.read(0x20000000,4)


def test_rsp_timeout_cancel_eof_overflow_and_size_limits():
    backend = adapter_response(b'0')
    backend._input = queue.Queue(); backend.TIMEOUT=.01
    with pytest.raises(SwdError) as error: backend.read(0x20000000,4)
    assert error.value.result == R.Timeout
    backend.cancel.set()
    with pytest.raises(SwdError) as error: backend.read(0x20000000,4)
    assert error.value.result == R.Cancelled
    backend.cancel.clear(); backend._input.put(b'')
    with pytest.raises(SwdError,match='closed'): backend.read(0x20000000,4)
    backend._overflow.set()
    with pytest.raises(SwdError,match='overflow'): backend.read(0x20000000,4)
    with pytest.raises(SwdError): backend.read(0x40000000,4)
    with pytest.raises(SwdError): backend.read('bad',4)


def test_cli_exact_selection_json_and_release(capsys):
    from swd_cli import SwdCli_Run
    import json
    backend=FakeMemory(Event())
    inventory=lambda _:ProbeInventory(ProbeInventoryResult.Ready,(PROBE,))
    factory=lambda:SwdSession(_backend_factory=lambda _:backend)
    assert SwdCli_Run(['snapshot','--probe',PROBE.identity],_inventory=inventory,_session=factory)==0
    output=json.loads(capsys.readouterr().out)
    assert output['snapshot']['symbols']=='unmatched' and output['release']['result']=='ok'
    assert backend.closed==1
    assert SwdCli_Run(['snapshot','--probe','wrong'],_inventory=inventory,_session=factory)==2
    assert json.loads(capsys.readouterr().out)['result']=='invalid_request' and backend.opened==1


def test_owned_pipe_child_is_closed_and_reaped(tmp_path):
    import subprocess
    import sys
    from threading import Thread
    backend=OpenOcdMemAp(Event())
    # A Python echo process, not OpenOCD; it cannot communicate with a target.
    backend.process=subprocess.Popen([sys.executable,'-u','-c',
        'import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b"end"); sys.stdout.buffer.flush()'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    process=backend.process
    backend._threads=[Thread(target=backend._receive,daemon=True),Thread(target=backend._receive_log,daemon=True)]
    for thread in backend._threads:thread.start()
    backend.close()
    assert backend.process is None and process.poll()==0
    assert not any(t.is_alive() for t in backend._threads)
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed


def test_owned_unresponsive_child_is_terminated_within_bound():
    import subprocess
    import sys
    import time
    backend=OpenOcdMemAp(Event())
    backend.process=subprocess.Popen([sys.executable,'-u','-c','import time; time.sleep(60)'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    process=backend.process;started=time.monotonic()
    backend.close()
    assert process.poll() is not None and time.monotonic()-started < 3


def test_pipe_stream_integration_has_no_control_packets():
    import subprocess
    import sys
    from threading import Thread
    backend=OpenOcdMemAp(Event())
    code='''import sys
packet=bytearray()
while True:
    byte=sys.stdin.buffer.read(1)
    if not byte:sys.exit(2)
    packet.extend(byte)
    if byte==b'#':
        packet.extend(sys.stdin.buffer.read(2));break
if packet != b'$m20000000,4#4f':sys.exit(3)
sys.stdout.buffer.write(b'+$01020304#8a');sys.stdout.buffer.flush()
if sys.stdin.buffer.read(1)!=b'+':sys.exit(4)
sys.stdin.buffer.read()
'''
    backend.process=subprocess.Popen([sys.executable,'-u','-c',code],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    process=backend.process
    backend._threads=[Thread(target=backend._receive,daemon=True),Thread(target=backend._receive_log,daemon=True)]
    for thread in backend._threads:thread.start()
    try:
        assert backend.read(0x20000000,4)==b'\x01\x02\x03\x04'
    finally:backend.close()
    assert process.poll()==0
