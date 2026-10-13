"""Fault-only synthetic ownership/claim tests, no real probe enumeration/open."""
import io
from threading import Event
import subprocess
import sys
import time
from unittest.mock import Mock, patch
import pytest

from transport.swd_session import SwdSession, SwdResult as R, SwdError
from transport._swd_openocd import OpenOcdMemAp
from test_swd_session import FakeMemory, PROBE, connected, tick


@pytest.mark.parametrize('reason',[R.Busy,R.InvalidRequest,R.TransportError])
def test_attach_refusal_closes_partial_backend_before_return(reason):
    backend=FakeMemory(Event())
    def refused(_):
        backend.opened+=1
        raise SwdError(reason,'injected partial claim failure')
    backend.open=refused
    session=SwdSession(_backend_factory=lambda _:backend)
    reply=session.Swd_Attach(PROBE)
    assert reply.result==reason and backend.closed==1
    assert session._backend is None and session._probe is None and not backend.reads
    assert session.Swd_Detach().result==R.Ok and backend.closed==1


def test_busy_during_read_invalidates_current_session_and_releases():
    session,backend,_=connected();tick(session)
    backend.failure=SwdError(R.Busy,'ownership lost')
    assert session.Swd_Snapshot().result==R.Busy and backend.closed==1
    assert session.Swd_Snapshot().result==R.NotAttached


def test_repeated_attach_busy_preserves_the_existing_owner():
    session,backend,_=connected()
    assert session.Swd_Attach(PROBE).result==R.Busy
    assert backend.closed==0 and backend.opened==1 and len(backend.reads)==3
    assert session.Swd_Detach().result==R.Ok and backend.closed==1


def test_broken_stdin_does_not_skip_process_reaping_or_other_streams():
    backend=OpenOcdMemAp(Event())
    process=backend.process=Mock()
    process.stdin.closed=False
    def broken_close():
        process.stdin.closed=True
        raise BrokenPipeError('injected broken pipe')
    process.stdin.close.side_effect=broken_close
    process.wait.return_value=0
    backend.close()
    process.wait.assert_called_once()
    process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()
    assert backend.process is None


def test_unexpected_open_result_cannot_publish_an_attached_target():
    backend=FakeMemory(Event());backend.open=lambda _:R.Busy
    session=SwdSession(_backend_factory=lambda _:backend)
    reply=session.Swd_Attach(PROBE)
    assert reply.result==R.TransportError and backend.closed==1 and not backend.reads


def test_failed_cleanup_after_refusal_is_explicit_and_retains_ownership():
    backend=FakeMemory(Event())
    backend.open=Mock(side_effect=SwdError(R.Busy,'claim refused'))
    backend.close=Mock(side_effect=OSError('cannot release'))
    session=SwdSession(_backend_factory=lambda _:backend)
    reply=session.Swd_Attach(PROBE)
    assert reply.result==R.ReleaseFailed and 'busy:' in reply.detail
    assert session._backend is backend and session._probe is None and not backend.reads
    assert session.Swd_Attach(PROBE).result==R.Busy
    assert backend.open.call_count==1
    backend.close=Mock(return_value=None)
    assert session.Swd_Detach().result==R.Ok


@pytest.mark.parametrize('message,result',[
    ('Warn : could not claim interface: LIBUSB_ERROR_BUSY',R.Busy),
    ('Warn : could not claim interface: Access denied',R.TransportError),
    ('Error: failed to claim interface: no device',R.TransportError),
])
def test_claim_failure_is_latched_and_blocks_every_api_memory_packet(message,result):
    backend=OpenOcdMemAp(Event());backend.process=Mock();backend.process.stdin=io.BytesIO()
    backend._log_line(message.encode())
    backend._log_line(b'SILVERSTAR_MEM_AP_INIT_COMPLETE')
    with pytest.raises(SwdError) as failure:backend.read(0x20000000,4)
    assert failure.value.result==result and backend.process.stdin.getvalue()==b''
    backend._log_line(b'Warn : could not claim interface: other failure')
    assert backend._failure.result==result  # Preserve the first cause.


@pytest.mark.parametrize('stderr,result',[
    (b'Warn : could not claim interface: Resource busy\nSILVERSTAR_MEM_AP_INIT_COMPLETE\n',R.Busy),
    (b'Warn : could not claim interface: Access denied',R.TransportError),
    (b'',R.TransportError),
])
def test_synthetic_startup_refusal_releases_before_session_reply(stderr,result):
    backend=OpenOcdMemAp(Event())
    process=Mock();process.stdin=io.BytesIO();process.stdout=io.BytesIO();process.stderr=io.BytesIO(stderr)
    process.wait.return_value=0;process.poll.return_value=0
    backend.open=lambda _:backend._start(['synthetic-only'])
    session=SwdSession(_backend_factory=lambda _:backend)
    with patch('transport._swd_openocd.subprocess.Popen',return_value=process):
        reply=session.Swd_Attach(PROBE)
    assert reply.result==result and session._backend is None and backend.process is None
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
    assert not any(t.is_alive() for t in backend._threads)


def test_startup_timeout_and_cancel_reap_only_the_owned_synthetic_child():
    for cancelled in (False,True):
        cancel=Event()
        if cancelled:cancel.set()
        backend=OpenOcdMemAp(cancel);backend.TIMEOUT=.05
        # This Python helper has no USB/device API; it models a stalled debugger.
        args=[sys.executable,'-u','-c','import time; time.sleep(60)']
        started=time.monotonic()
        try:
            with pytest.raises(SwdError) as failure:backend._start(args)
            assert failure.value.result==(R.Cancelled if cancelled else R.Timeout)
        finally:
            process=backend.process;backend.close()
        assert process.poll() is not None and time.monotonic()-started<3
        assert backend.process is None and not any(t.is_alive() for t in backend._threads)


def test_other_close_error_still_attempts_all_resources_and_reports_release_failure():
    backend=OpenOcdMemAp(Event());process=backend.process=Mock()
    process.stdin.closed=False;process.stdin.close.side_effect=OSError('stdin refused')
    process.wait.return_value=0;process.poll.return_value=0
    process.stdout.close.side_effect=OSError('stdout refused')
    with pytest.raises(SwdError) as failure:backend.close()
    assert failure.value.result==R.ReleaseFailed
    process.wait.assert_called_once();process.stderr.close.assert_called_once()
    assert backend.process is process  # Retain the failed owner for explicit retry.


def test_second_session_cannot_claim_same_parent_identity_in_this_process():
    session,backend,_=connected()
    factory=Mock();second=SwdSession(_backend_factory=factory)
    assert second.Swd_Attach(PROBE).result==R.Busy
    factory.assert_not_called()
    assert backend.closed==0 and second.Swd_Detach().result==R.Ok
    assert backend.closed==0  # A rejected caller must not release the existing owner.
    assert session.Swd_Detach().result==R.Ok
    next_backend=FakeMemory(Event())
    second=SwdSession(_backend_factory=lambda _:next_backend)
    assert second.Swd_Attach(PROBE).result==R.Ok
    assert second.Swd_Detach().result==R.Ok


def test_constructor_failure_releases_process_reservation():
    factory=Mock(side_effect=OSError('injected constructor failure'))
    session=SwdSession(_backend_factory=factory)
    assert session.Swd_Attach(PROBE).result==R.TransportError
    next_session,backend,_=connected()
    assert next_session.Swd_Detach().result==R.Ok and backend.closed==1


def test_close_cannot_return_a_failure_result_and_be_treated_as_released():
    session,backend,_=connected();original=backend.close
    backend.close=lambda:R.Busy
    assert session.Swd_Detach().result==R.ReleaseFailed
    other=SwdSession(_backend_factory=Mock())
    assert other.Swd_Attach(PROBE).result==R.Busy
    backend.close=original
    assert session.Swd_Detach().result==R.Ok


def test_stdin_not_closed_is_explicit_even_when_the_child_exited():
    backend=OpenOcdMemAp(Event());process=backend.process=Mock()
    process.stdin.closed=False;process.stdin.close.side_effect=BrokenPipeError('still open')
    process.wait.return_value=0;process.poll.return_value=0
    with pytest.raises(SwdError,match='stdin still open'):backend.close()
    process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()


def test_process_reservation_is_not_mistaken_for_cross_process_exclusion():
    session,backend,_=connected()
    try:
        code='''from threading import Event
from test_swd_session import FakeMemory,PROBE
from transport.swd_session import SwdSession,SwdResult
fake=FakeMemory(Event())
with SwdSession(_backend_factory=lambda _:fake) as session:
    assert session.Swd_Attach(PROBE).result==SwdResult.Ok
print('synthetic second process accepted')
'''
        run=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5)
        assert run.returncode==0 and 'second process accepted' in run.stdout
        assert backend.closed==0
    finally:
        assert session.Swd_Detach().result==R.Ok


def test_normal_startup_barrier_and_pipe_read_with_synthetic_child():
    backend=OpenOcdMemAp(Event())
    code='''import sys
sys.stderr.write('SILVERSTAR_MEM_AP_INIT_COMPLETE\\n');sys.stderr.flush()
packet=bytearray()
while True:
    byte=sys.stdin.buffer.read(1)
    if not byte:sys.exit(2)
    packet.extend(byte)
    if byte==b'#':packet.extend(sys.stdin.buffer.read(2));break
if packet!=b'$m20000000,4#4f':sys.exit(3)
sys.stdout.buffer.write(b'+$01020304#8a');sys.stdout.buffer.flush()
if sys.stdin.buffer.read(1)!=b'+':sys.exit(4)
sys.stdin.buffer.read()
'''
    try:
        backend._start([sys.executable,'-u','-c',code])
        assert backend.read(0x20000000,4)==b'\x01\x02\x03\x04'
    finally:
        process=backend.process;backend.close()
    assert process.returncode==0 and backend.process is None


def test_split_claim_message_is_terminal_before_startup_marker():
    class Chunks:
        def __init__(self):
            self.values=iter([b'Warn : could not claim inter',b'face: Resource busy\n',
                              b'SILVERSTAR_MEM_AP_INIT_COMPLETE\n',b''])
        def read(self,_):return next(self.values)
    backend=OpenOcdMemAp(Event());backend.process=Mock()
    backend.process.stderr=Chunks();backend.process.stdin=io.BytesIO()
    backend._receive_log()
    assert backend._startup.is_set() and backend._failure.result==R.Busy
    with pytest.raises(SwdError):backend.read(0x20000000,4)
    assert backend.process.stdin.getvalue()==b''


def test_wait_error_after_terminate_still_attempts_kill_and_closes_pipes():
    backend=OpenOcdMemAp(Event());process=backend.process=Mock()
    process.stdin=io.BytesIO();process.stdout=io.BytesIO();process.stderr=io.BytesIO()
    process.wait.side_effect=[subprocess.TimeoutExpired('synthetic',.3),OSError('reap failed'),0]
    process.poll.return_value=0
    with pytest.raises(SwdError) as failure:backend.close()
    assert failure.value.result==R.ReleaseFailed
    process.terminate.assert_called_once();process.kill.assert_called_once()
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
