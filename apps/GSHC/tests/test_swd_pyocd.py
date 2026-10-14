"""Actual pinned pyOCD classes with synthetic USB/register interfaces, never hardware."""
from dataclasses import replace
from array import array
from queue import Queue, Empty
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from transport._swd_pyocd import PyOcdMemAp, _LoadLibrary, _LibraryOwner, _BulkInterface, _SelectDevice
from transport.swd_session import SwdSession, SwdResult as R, SwdError
from test_swd_session import PROBE, tick


@pytest.fixture
def library():
    # No fallback/skip: this test run must contain the approved actual dependency.
    return _LoadLibrary()


class RegisterLink:
    """CMSIS-DAP register seam; real Probe, DebugPort and AccessPort execute above it."""
    supports_board_and_target_names = False
    has_swd_sequence = False

    def __init__(self, serial, interface):
        self.serial = serial
        self._interface = interface
        self._is_open = False
        self.vidpid = (0xFAED, 0x4870)
        self.vendor_name = 'synthetic'
        self.product_name = 'synthetic CMSIS-DAP'
        self.select = self.tar = 0
        self.csw = 0x23000052
        self.writes = []
        self.reads = []
        self.controls = []
        self.memory = {0xE000ED00: 0x410FC241, 0xE0042000: 0x10016413,
                       0xE000EDF0: 0x01000000, 0x20000000: 0x12345678}
        self.failure = None

    def get_unique_id(self): return self.serial
    def has_swo(self): return False
    def identify(self, _): return 1
    def set_deferred_transfer(self, _): pass
    def set_clock(self, hz): self.controls.append(('clock', hz))
    def swj_sequence(self, length, bits): self.controls.append(('swj', length, bits))
    def get_swj_mode(self): return self.port
    def open(self):
        self._interface.open()
        self._is_open = True
    def connect(self, port):
        self.port = port
        self.controls.append(('connect', port))
    def disconnect(self): self.controls.append(('disconnect',))

    def read_reg(self, reg, now=True):
        def read():
            raw = reg.value
            offset = (raw & 3) * 4
            self.reads.append((raw, self.select, self.tar))
            if self.failure:
                raise self.failure
            if raw < 4:
                return 0x2BA01477 if offset == 0 else 0xF0000000
            offset |= self.select & 0xF0
            if offset == 0xFC: return 0x24770011
            if offset == 0xF4: return 0
            if offset == 0xF8: return 0xE00FF003
            if offset == 0: return self.csw
            if offset == 0xC:
                result = self.memory.get(self.tar & ~3, 0)
                self.tar += 4
                return result
            raise AssertionError(('unexpected AP read', offset))
        return read() if now else read

    def write_reg(self, reg, value):
        raw = reg.value
        offset = (raw & 3) * 4
        self.writes.append((raw, self.select, value))
        if raw < 4:
            assert offset in (0, 4, 8), 'Unexpected DP control'
            if offset == 8: self.select = value
        else:
            offset |= self.select & 0xF0
            assert offset in (0, 4), 'Target-memory write or unexpected AP register'
            if offset == 0: self.csw = value
            else: self.tar = value

    def reg_read_repeat(self, count, reg, dap_index=0, now=True):
        read = lambda: [self.read_reg(reg) for _ in range(count)]
        return read() if now else read


@pytest.fixture
def synthetic(library):
    device = SimpleNamespace(idVendor=0xFAED, idProduct=0x4870, serial_number=PROBE.serial,
        product='CMSIS-DAP', manufacturer='synthetic', default_timeout=None,
        get_active_configuration=Mock(return_value='synthetic config'))
    ep_in = SimpleNamespace(wMaxPacketSize=512,
        read=Mock(side_effect=library.bulk.usb.core.USBTimeoutError('drain finished')))
    ep_out = SimpleNamespace(write=Mock(), wMaxPacketSize=512)
    interface = SimpleNamespace(bInterfaceNumber=0, endpoints=lambda: [ep_out, ep_in])
    api = SimpleNamespace(**vars(library))
    api.Link = RegisterLink
    with patch('transport._swd_pyocd._LoadLibrary', return_value=api), \
            patch.object(api.bulk, 'usb_find', return_value=[device]) as find, \
            patch.object(api.bulk.usb.util, 'find_descriptor', return_value=interface), \
            patch.object(api.bulk.usb.util, 'claim_interface') as claim, \
            patch.object(api.bulk.usb.util, 'release_interface') as release, \
            patch.object(api.bulk.usb.util, 'dispose_resources') as dispose:
        yield SimpleNamespace(api=api, device=device, interface=interface, ep_in=ep_in,
            ep_out=ep_out, find=find, claim=claim, release=release, dispose=dispose)
    assert not _LibraryOwner.locked(), 'A test leaked library ownership'


def test_actual_probe_dp_ap_normal_reads_and_only_transport_writes(synthetic):
    backend = PyOcdMemAp(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    reply = session.Swd_Attach(PROBE)
    assert reply.result == R.Ok, reply
    assert reply.snapshot.core_state == 'running' and reply.snapshot.symbols == 'unmatched'
    link = backend._link
    tick(session)
    reply = session.Swd_ReadMemory(0x20000000, 4)
    assert reply.result == R.Ok and reply.data == bytes.fromhex('78563412')
    assert session.Swd_Detach().result == R.Ok
    assert link.controls[-1] == ('disconnect',)
    assert not any(name[0] in ('reset', 'halt', 'resume') for name in link.controls)
    assert link.writes and all(raw < 4 or ((raw & 3) * 4 | select & 0xF0) in (0, 4)
                               for raw, select, _ in link.writes)
    synthetic.claim.assert_called_once_with(synthetic.device, 0)
    synthetic.release.assert_called_once_with(synthetic.device, 0)
    synthetic.dispose.assert_called_once_with(synthetic.device)


@pytest.mark.parametrize('part,cpuid,dp_version', [('STM32F103C8',0x411FC231,1),
    ('STM32F407VET6',0x410FC241,1),('STM32C071FBP6',0x410CC601,2)])
def test_official_target_profiles_share_actual_pyocd_read_only_path(synthetic,part,cpuid,dp_version):
    class Link(RegisterLink):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.memory[0xE000ED00]=cpuid
        def read_reg(self,reg,now=True):
            if reg.value==0:
                value=(0x2BA01477 & ~0xF000) | (dp_version<<12)
                return value if now else lambda:value
            return super().read_reg(reg,now)
    synthetic.api.Link=Link
    backend=PyOcdMemAp(Event())
    session=SwdSession(target=part,_backend_factory=lambda _:backend)
    reply=session.Swd_Attach(PROBE)
    assert reply.result==R.Ok and reply.snapshot.cpuid==cpuid
    assert reply.snapshot.target_evidence=='selected_part_core_verified'
    assert reply.snapshot.device_id==0  # No guessed family-specific MMIO read.
    link=backend._link
    tick(session)
    assert session.Swd_ReadMemory(0x20000000,4).result==R.Ok
    assert session.Swd_ReadMemory(0x40000000,4).result==R.InvalidRequest
    assert session.Swd_ReadMemory(0x08000000,4).result==R.InvalidRequest
    assert session.Swd_Detach().result==R.Ok
    assert link.controls[-1]==('disconnect',)
    assert all(raw<4 or ((raw & 3)*4 | select & 0xF0) in (0,4) for raw,select,_ in link.writes)


def test_actual_link_claim_failure_sends_no_packet_and_disposes(synthetic, library):
    synthetic.api.Link = library.Link
    synthetic.claim.side_effect = library.bulk.usb.core.USBError('owned by another client')
    session = SwdSession(_backend_factory=PyOcdMemAp)
    reply = session.Swd_Attach(PROBE)
    assert reply.result == R.Busy and 'claim refused' in reply.detail
    synthetic.ep_out.write.assert_not_called()
    synthetic.release.assert_not_called()
    synthetic.dispose.assert_called_once_with(synthetic.device)
    assert session._backend is None


def test_actual_link_partial_info_failure_releases_despite_false_open_flags(synthetic, library):
    synthetic.api.Link = library.Link
    with patch.object(library.Link, 'identify', side_effect=library.bulk.DAPAccessIntf.DeviceError('info failed')):
        reply = SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(PROBE)
    assert reply.result == R.TransportError and 'info failed' in reply.detail
    synthetic.release.assert_called_once_with(synthetic.device, 0)
    synthetic.dispose.assert_called_once_with(synthetic.device)


def test_options_only_session_does_not_load_user_script_board_or_target(synthetic, library):
    from pyocd.board.board import Board
    from pyocd.coresight.cortex_m import CortexM
    with patch.object(library.Session, '_load_user_script', side_effect=AssertionError('script executed')), \
            patch.object(library.Session, 'open', side_effect=AssertionError('session opened')), \
            patch.object(Board, '__init__', side_effect=AssertionError('board constructed')), \
            patch.object(CortexM, '__init__', side_effect=AssertionError('core constructed')):
        backend = PyOcdMemAp(Event())
        backend.open(PROBE)
        assert backend._session.board is None and backend._session.delegate is None
        backend.close()


@pytest.mark.parametrize('method', ['_connect', 'clear_sticky_err', 'power_up_debug', '_check_version'])
def test_actual_dp_failure_always_unlocks_and_releases(synthetic, library, method):
    created = []
    def probe(link):
        result = library.Probe(link)
        created.append(result)
        return result
    synthetic.api.Probe = probe
    backend = PyOcdMemAp(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    with patch.object(library.DebugPort, method, side_effect=RuntimeError('DP failed')):
        reply = session.Swd_Attach(PROBE)
    assert reply.result == R.TransportError
    assert not created[0]._lock._is_owned()
    synthetic.release.assert_called_once()
    assert session._backend is None


def test_power_ack_false_is_a_timeout_not_an_attached_target(synthetic, library):
    with patch.object(library.DebugPort, 'power_up_debug', return_value=False):
        reply = SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(PROBE)
    assert reply.result == R.Timeout
    synthetic.release.assert_called_once()


def test_memory_fault_invalidates_session_and_releases(synthetic, library):
    backend = PyOcdMemAp(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    assert session.Swd_Attach(PROBE).result == R.Ok
    tick(session)
    backend._link.failure = library.bulk.DAPAccessIntf.TransferFaultError('injected target fault')
    assert session.Swd_ReadMemory(0x20000000, 4).result == R.TransportError
    synthetic.release.assert_called_once()
    assert session.Swd_Snapshot().result == R.NotAttached


def test_cancel_after_claim_releases_without_run_control(synthetic):
    cancel = Event()
    backend = PyOcdMemAp(cancel)
    session = SwdSession(cancel=cancel, _backend_factory=lambda _: backend)
    synthetic.claim.side_effect = lambda *_: cancel.set()
    assert session.Swd_Attach(PROBE).result == R.Cancelled
    synthetic.release.assert_called_once()


def test_drain_is_bounded_and_partial_claim_is_released(synthetic):
    synthetic.ep_in.read.side_effect = None
    synthetic.ep_in.read.return_value = b'stale'
    assert SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(PROBE).result == R.TransportError
    assert synthetic.ep_in.read.call_count == 64
    synthetic.release.assert_called_once()


def test_release_failure_retains_resources_until_retry(synthetic):
    backend = PyOcdMemAp(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    assert session.Swd_Attach(PROBE).result == R.Ok
    synthetic.release.side_effect = OSError('release failed')
    reply = session.Swd_Detach()
    assert reply.result == R.ReleaseFailed and backend._interface._claimed and _LibraryOwner.locked()
    synthetic.dispose.assert_not_called()
    synthetic.release.side_effect = None
    assert session.Swd_Detach().result == R.Ok
    synthetic.dispose.assert_called_once()


def test_probe_absent_and_duplicate_serial_never_claim(synthetic):
    for devices in ([], [synthetic.device, replace_device(synthetic.device)]):
        synthetic.find.return_value = devices
        assert SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(PROBE).result == R.InvalidRequest
    synthetic.claim.assert_not_called()


def replace_device(device):
    return SimpleNamespace(**vars(device))


def test_no_interface_zero_or_hid_fallback(synthetic):
    synthetic.api.bulk.usb.util.find_descriptor.return_value = None
    assert SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(PROBE).result == R.Unsupported
    synthetic.claim.assert_not_called()


def test_wrong_probe_is_rejected_before_loading_dependencies():
    with patch('transport._swd_pyocd._LoadLibrary') as load:
        assert SwdSession(_backend_factory=PyOcdMemAp).Swd_Attach(replace(PROBE, family='J-Link')).result == R.Unsupported
        load.assert_not_called()


def test_missing_dependency_default_route_never_opens_a_device(tmp_path, monkeypatch):
    monkeypatch.setenv('SILVERSTAR_SWD_PYOCD_PATH', str(tmp_path))
    assert SwdSession().Swd_Attach(PROBE).result == R.MissingDependency


def test_actual_cmsis_dap_encoder_bulk_rx_dp_ap_and_identity_ram(synthetic, library):
    from pyocd.probe.pydapaccess.dap_access_api import DAPAccessIntf
    responses = Queue()
    model = RegisterLink(PROBE.serial, synthetic.interface)
    packets = []

    def send(data, timeout):
        data = bytes(data)
        if not data: return 0
        packets.append(data)
        command = data[0]
        assert command not in (0xA, 0x10), 'Reset target/pin command forbidden'
        if command == 0:
            value = {0xF0: b'\x01', 0xFE: b'\x01', 0xFF: b'\x00\x02',
                     4: b'2.0.0\x00'}.get(data[1], b'')
            reply = bytes([0, len(value)]) + value
        elif command in (5, 6):
            count = data[2] if command == 5 else int.from_bytes(data[2:4], 'little')
            cursor = 3 if command == 5 else 5
            reads = b''
            for _ in range(count):
                request = data[cursor] if command == 5 else data[4]
                if command == 5: cursor += 1
                assert not request & 0xF0
                reg = DAPAccessIntf.REG(((request & 0xC) >> 2) + (4 if request & 1 else 0))
                if request & 2:
                    reads += model.read_reg(reg).to_bytes(4, 'little')
                else:
                    model.write_reg(reg, int.from_bytes(data[cursor:cursor+4], 'little'))
                    cursor += 4
            reply = bytes([5, count, 1]) + reads if command == 5 else bytes([6, count & 255, count >> 8, 1]) + reads
        else:
            assert command in (1, 2, 3, 4, 0x11, 0x12, 0x13), ('unexpected command', command)
            reply = bytes([command, 1 if command == 2 else 0])
        responses.put(reply)
        return len(data)

    def receive(size, timeout):
        try:
            return array('B', responses.get(timeout=timeout/1000))
        except Empty:
            raise library.bulk.usb.core.USBTimeoutError('synthetic packet timeout')

    synthetic.ep_in.read.side_effect = receive
    synthetic.ep_out.write.side_effect = send
    synthetic.api.Link = library.Link
    backend = PyOcdMemAp(Event())
    session = SwdSession(_backend_factory=lambda _: backend)
    try:
        reply = session.Swd_Attach(PROBE)
        assert reply.result == R.Ok, reply
        tick(session)
        reply = session.Swd_ReadMemory(0x20000000, 4)
        assert reply.result == R.Ok and reply.data == bytes.fromhex('78563412')
    finally:
        assert session.Swd_Detach().result == R.Ok
    assert any(p[0] == 6 and not p[4] & 2 for p in packets), 'Actual encoder uses DP/AP configuration block writes'
    assert model.writes and packets[-1] == b'\x03'
    synthetic.release.assert_called_once()


def test_selection_cancel_disposes_metadata_handle_without_claim(synthetic):
    with pytest.raises(SwdError) as error:
        _SelectDevice(synthetic.api, PROBE.serial,
            Mock(side_effect=SwdError(R.Cancelled, 'cancelled during enumeration')))
    assert error.value.result == R.Cancelled
    synthetic.dispose.assert_called_once_with(synthetic.device)
    synthetic.claim.assert_not_called()


@pytest.mark.parametrize('direction', ['write','read'])
def test_native_usb_timeout_is_explicit(synthetic, library, direction):
    interface = _BulkInterface(library, synthetic.device, lambda: None)
    interface.open()
    try:
        if direction == 'write':
            synthetic.ep_out.write.side_effect = library.bulk.usb.core.USBTimeoutError('timed out')
            operation = lambda: interface.write([0])
        else:
            operation = interface.read  # Actual upstream queue timeout, no response.
        with pytest.raises(SwdError) as error:
            operation()
        assert error.value.result == R.Timeout
    finally:
        interface.close()
