"""Actual pinned pyOCD ST-Link classes on fake USB endpoints. No device access."""
from dataclasses import replace
from threading import Event
import struct
from unittest.mock import Mock
import pytest
from transport.probe_inventory import HostProbe
from transport.swd_session import SwdSession, SwdResult as R, SwdError, _ProbeOwners
from transport.swd_backends import ProbeKind_Get, SwdBackendKind, STLINK_PIDS
from transport import _swd_stlink as adapter
from transport._swd_pyocd import _LibraryOwner
from test_swd_session import tick
from test_swd_firmware import arm_elf, load
from test_swd_ui import swd_panel
from test_probe_ui import panel

SERIAL='0123456789ABCDEF01234567'


def probe(pid=0x3748,serial=SERIAL):
    return HostProbe(rf'USB\VID_0483&PID_{pid:04X}\{serial}','ST-Link','ST-Link',
                     f'0483:{pid:04X}',serial,'USB serial',('USBDevice / WinUSB',),'OK')


class FakeEndpoint:
    wMaxPacketSize=64
    def __init__(self,device,address): self.device=device;self.bEndpointAddress=address
    def write(self,data,timeout):
        d=self.device
        assert d.claimed and timeout==500
        raw=bytes(data);d.tx.append(raw)
        assert len(raw)==16
        cmd=raw[:2]
        if raw[0]==0xF1:
            d.response=struct.pack('>H',(d.hw<<12)|(d.jtag<<6)|3)+struct.pack('<HH',0x0483,d.idProduct)
        elif raw[0]==0xFB: d.response=bytes([d.hw,0,d.jtag,3,0,0,0,0])+struct.pack('<HH',0x0483,d.idProduct)
        elif raw[0]==0xF5: d.response=bytes([d.mode,0])
        elif raw[0]==0xF7: d.response=struct.pack('<II',1000,1375)
        elif cmd==b'\xF2\x30': d.mode=2;d.response=b'\x80\x00'
        elif cmd==b'\xF2\x21': d.mode=1;d.response=None
        elif cmd==b'\xF2\x45':
            port,reg=struct.unpack('<HH',raw[2:6]);value=d.dp if port==0xFFFF else d.ap
            d.response=struct.pack('<HHI',0x80,0,value)
        elif cmd in (b'\xF2\x07',b'\xF2\x0C'):
            addr,n=struct.unpack('<IH',raw[2:8]);d.mem_reads.append((addr,n))
            if d.cancel_on_memory: d.cancel_on_memory.set()
            if d.memory_error: raise d.memory_error
            d.response=bytes(d.memory.get(addr+i,(addr+i)&255) for i in range(n))
        elif cmd==b'\xF2\x3E': d.response=struct.pack('<HHII',d.fault,0,0x20000000,0)
        elif cmd in (b'\xF2\x63',b'\xF2\x61'): d.response=struct.pack('<II',0x80,1000)
        elif cmd in (b'\xF2\x43',b'\xF2\x4B',b'\xF2\x46'): d.response=b'\x80\x00'
        else: raise AssertionError('Unexpected wire command '+raw.hex())
        return 16
    def read(self,size,timeout):
        d=self.device
        if timeout==1:
            d.drains+=1
            if d.drain_packets:
                d.drain_packets-=1;return bytes(size)
            raise d.api.stusb.usb.core.USBTimeoutError('empty')
        assert timeout==500 and d.response is not None
        response,d.response=d.response,None
        return response[:-1] if d.short_response else response


class FakeDevice:
    idVendor=0x0483
    manufacturer='STMicroelectronics'
    product='ST-Link'
    def __init__(self,api,hw=2,pid=0x3748):
        self.api=api;self.hw=hw;self.jtag=32;self.idProduct=pid;self.serial_number=SERIAL
        self.mode=1;self.claimed=False;self.claims=self.releases=self.disposals=0
        self.tx=[];self.mem_reads=[];self.drains=self.drain_packets=0;self.response=None
        self.claim_error=self.release_error=self.memory_error=self.cancel_on_memory=None
        self.short_response=False;self.dp=0x2BA01477;self.ap=0x24770011;self.fault=0x80
        self.memory={}
        self.word(0xE000ED00,0x410FC241);self.word(0xE0042000,0x10070413);self.word(0xE000EDF0,0)
        info=api.stusb.STLinkUSBInterface.USB_PID_EP_MAP[pid]
        self.endpoints=[FakeEndpoint(self,info.out_ep),FakeEndpoint(self,info.in_ep)]
    def word(self,addr,value): self.memory.update({addr+i:v for i,v in enumerate(value.to_bytes(4,'little'))})
    def get_active_configuration(self):
        d=self
        class Configuration:
            def __getitem__(self,key):assert key==(0,0);return d.endpoints
        return Configuration()


@pytest.fixture
def rig(monkeypatch):
    api=adapter._LoadStlinkLibrary()  # Imports classes only; USB enumeration is patched below.
    devices=[]
    def claim(dev,interface):
        assert interface==0;dev.claims+=1
        if dev.claim_error: raise dev.claim_error
        dev.claimed=True
    def release(dev,interface):
        assert interface==0;dev.releases+=1
        if dev.release_error: raise dev.release_error
        dev.claimed=False
    def dispose(dev): dev.disposals+=1
    monkeypatch.setattr(api.stusb,'usb_find',lambda **kwargs:iter(devices))
    monkeypatch.setattr(api.stusb.usb.util,'claim_interface',claim)
    monkeypatch.setattr(api.stusb.usb.util,'release_interface',release)
    monkeypatch.setattr(api.stusb.usb.util,'dispose_resources',dispose)
    monkeypatch.setattr(adapter,'_LoadStlinkLibrary',lambda:api)
    sessions=[]
    def create(*,hw=2,pid=0x3748,target=None,firmware=None):
        device=FakeDevice(api,hw,pid);devices.append(device)
        session=SwdSession(target=target,firmware=firmware);sessions.append(session)
        return session,device
    yield create,devices,api
    for session in sessions:
        if session._backend and session._backend._interface:
            session._backend._interface._dev.release_error=None
        session.cancel.clear();session.Swd_Detach()
    assert not _LibraryOwner.locked() and not _ProbeOwners


@pytest.mark.parametrize('hw,pid',[(2,0x3748),(2,0x374B),(3,0x374E),(4,0x3757)])
@pytest.mark.parametrize('target,cpuid,dp',[('STM32F103C8',0x410FC231,0x2BA01477),
    ('STM32F407VET6',0x410FC241,0x2BA01477),('STM32C071FBP6',0x410CC601,0x6BA02477)])
def test_real_dependency_classes_read_and_release_without_core_control(rig,hw,pid,target,cpuid,dp):
    create,_,_=rig;session,device=create(hw=hw,pid=pid,target=target)
    device.word(0xE000ED00,cpuid);device.dp=dp
    try:
        reply=session.Swd_Attach(probe(pid))
        assert reply.result==R.Ok,reply.detail
        assert session._backend._session.board is None
        tick(session)
        reply=session.Swd_ReadMemory(0x20000001,7)
        assert reply.result==R.Ok and reply.data==bytes(range(1,8))
        assert (0x20000001,3) in device.mem_reads and (0x20000004,4) in device.mem_reads
    finally: assert session.Swd_Detach().result==R.Ok
    assert device.releases==1 and not device.claimed and device.mode==1
    assert all(p[:2] not in [b'\xF2\x08',b'\xF2\x0D',b'\xF2\x3C',b'\xF2\x48',b'\xF2\x55'] for p in device.tx)


def test_claim_busy_emits_zero_commands_and_releases_reservation(rig):
    create,_,api=rig;session,device=create();device.claim_error=api.stusb.usb.core.USBError('busy')
    reply=session.Swd_Attach(probe())
    assert reply.result==R.Busy and device.tx==[] and device.releases==0
    assert session._backend is None and not _LibraryOwner.locked()


@pytest.mark.parametrize('mode,result',[(2,R.Busy),(0,R.SafetyNotProven),(3,R.SafetyNotProven),(9,R.SafetyNotProven)])
def test_preexisting_modes_are_not_exited_or_initialized(rig,mode,result):
    create,_,_=rig;session,device=create();device.mode=mode
    assert session.Swd_Attach(probe()).result==result
    assert device.mode==mode and [p[0] for p in device.tx]==[0xF5] and device.releases==1


@pytest.mark.parametrize('change',['version','dp','ap','short','drain'])
def test_unsupported_or_damaged_preflight_cannot_read_target(rig,change):
    create,_,_=rig;session,device=create()
    if change=='version':device.jtag=24
    elif change=='dp':device.dp=0x6BA03477
    elif change=='ap':device.ap=0
    elif change=='short':device.short_response=True
    else:device.drain_packets=100
    assert session.Swd_Attach(probe()).result!=R.Ok
    assert not device.mem_reads and device.releases==1
    if change=='drain':assert device.drains==64 and device.tx==[]


def test_upstream_unbounded_drain_vs_bounded_wrapper(rig):
    create,_,api=rig;_,old=create();old.drain_packets=66
    intf=api.stusb.STLinkUSBInterface(old);intf._ep_in=old.endpoints[1]
    intf._flush_rx();assert old.drains==67  # Original silently accepts >64 packets.
    session,new=create();new.drain_packets=66
    # Select just the new fake device, avoiding intentional ambiguity.
    rig[1].remove(old)
    assert session.Swd_Attach(probe()).result==R.TransportError and new.drains==64


def test_ambiguous_identity_and_normalized_v2_serial(rig):
    create,devices,_=rig;session,first=create();_,second=create()
    assert session.Swd_Attach(probe()).result==R.InvalidRequest and not first.tx and not second.tx
    devices.remove(second);first.serial_number='123456ABCDEF'
    normalized=first.serial_number.encode('utf-16-le')[::2].hex().upper()
    assert session.Swd_Attach(probe(serial=normalized)).result==R.Ok
    session.Swd_Detach()


@pytest.mark.parametrize('fault',['timeout','unplug','cancel','ap_fault'])
def test_memory_fault_or_cancel_releases_and_does_not_publish(rig,fault):
    create,_,api=rig;session,device=create();assert session.Swd_Attach(probe()).result==R.Ok;tick(session)
    expected=R.TransportError
    if fault=='timeout':device.memory_error=api.stusb.usb.core.USBTimeoutError('timeout');expected=R.Timeout
    elif fault=='unplug':device.memory_error=api.stusb.usb.core.USBError('unplugged')
    elif fault=='cancel':device.cancel_on_memory=session.cancel;expected=R.Cancelled
    else:device.fault=0x11
    reply=session.Swd_ReadMemory(0x20000000,4)
    assert reply.result==expected and reply.snapshot is None and not reply.data
    assert session._backend is None and device.releases==1
    writes=[p for p in device.tx if p[:2]==b'\xF2\x46']
    assert len(writes)==(1 if fault=='ap_fault' else 0)
    if writes:assert writes[0][:10]==b'\xF2\x46\xFF\xFF\x00\x00\x1E\x00\x00\x00'


def test_release_failure_retains_owner_and_retry_can_complete(rig):
    create,_,_=rig;session,device=create();assert session.Swd_Attach(probe()).result==R.Ok
    device.release_error=OSError('release failed')
    assert session.Swd_Detach().result==R.ReleaseFailed and session._backend is not None
    assert _LibraryOwner.locked() and session.Swd_Attach(probe()).result==R.Busy
    device.release_error=None
    assert session.Swd_Detach().result==R.Ok and not _LibraryOwner.locked()


@pytest.mark.parametrize('cmd,read_size',[(b'\xF2\x3C\x02',None),(b'\xF2\x08',None),
    (b'\xF3\x07',None),(b'\xF4\x01',None),(b'\xF2\x4B\x01\x00',2),
    (b'\xF2\x4B\x00\x01',2),(b'\xF2\x46\xFF\xFF\x00\x00\x01\x00\x00\x00',2)])
def test_forbidden_commands_never_reach_usb(rig,cmd,read_size):
    create,_,_=rig;session,device=create();assert session.Swd_Attach(probe()).result==R.Ok
    count=len(device.tx)
    with pytest.raises(SwdError) as failure:session._backend._interface.transfer(cmd,readSize=read_size)
    assert failure.value.result==R.SafetyNotProven and len(device.tx)==count


def test_complete_elf_verification_and_diagnostics_use_the_same_service(rig,arm_elf):
    firmware=load(arm_elf);create,_,_=rig;session,device=create(firmware=firmware)
    for addr,data in firmware.segments:device.memory.update({addr+i:v for i,v in enumerate(data)})
    for entry in firmware.entries:
        for field in entry.fields:device.memory.update({field.address+i:v for i,v in enumerate((2).to_bytes(field.size,'little'))})
    assert session.Swd_Attach(probe()).result==R.Ok;tick(session)
    assert session.Swd_VerifyFirmware().result==R.Ok;tick(session)
    reply=session.Swd_Diagnostics()
    assert reply.result==R.Ok and len(reply.diagnostics)==4 and reply.snapshot.symbols=='matched'
    assert sum(n for a,n in device.mem_reads if 0x08000000<=a<0x10000000)==sum(len(data) for _,data in firmware.segments)


def test_unknown_probe_and_openocd_are_disabled_before_any_backend_creation():
    for selected in [probe(0x3748),replace(probe(),family='OpenOCD')]:
        if selected.family=='ST-Link':assert ProbeKind_Get(selected)==SwdBackendKind.Stlink
        else:
            factory=Mock();assert SwdSession(_backend_factory=factory).Swd_Attach(selected).result==R.Unsupported
            factory.assert_not_called()
    for pid in [0x3744,0x374D,0x9999]:
        with pytest.raises(SwdError):ProbeKind_Get(probe(pid))


def test_wrong_enumerated_pid_and_changed_identity_stop_before_claim(rig,monkeypatch):
    create,_,api=rig;session,device=create(pid=0x374E)
    assert session.Swd_Attach(probe()).result==R.TargetMismatch and device.claims==0 and not device.tx
    device.idProduct=0x3748
    original=adapter._Interface
    def changed(*args):
        interface=original(*args);device.serial_number='DIFFERENT';return interface
    monkeypatch.setattr(adapter,'_Interface',changed)
    assert session.Swd_Attach(probe()).result==R.TargetMismatch and device.claims==0 and not device.tx


def test_memory_without_admitted_window_or_outside_it_is_not_sent(rig):
    create,_,_=rig;session,device=create();assert session.Swd_Attach(probe()).result==R.Ok
    interface=session._backend._interface;count=len(device.tx)
    cmd=b'\xF2\x07'+struct.pack('<IHBBBB',0x20000000,4,0,0,0,0)
    with pytest.raises(SwdError):interface.transfer(cmd,readSize=4)
    interface.read_window=(0x20000004,4)
    with pytest.raises(SwdError):interface.transfer(cmd,readSize=4)
    interface.read_window=None
    assert len(device.tx)==count
    interface.read_window=(0x40000000,4)
    bad=b'\xF2\x07'+struct.pack('<IHBBBB',0x40000000,4,0,0,0,0)
    with pytest.raises(SwdError):interface.transfer(bad,readSize=4)
    interface.read_window=None
    assert len(device.tx)==count


def test_partial_open_failure_with_failed_release_stays_busy(rig):
    create,_,_=rig;session,device=create();device.drain_packets=100;device.release_error=OSError('held')
    assert session.Swd_Attach(probe()).result==R.ReleaseFailed and _LibraryOwner.locked()
    assert not device.tx and session.Swd_Attach(probe()).result==R.Busy
    device.release_error=None
    assert session.Swd_Detach().result==R.Ok


def test_library_ownership_cancel_and_operation_deadline_are_bounded(rig):
    create,_,_=rig;session,device=create()
    assert _LibraryOwner.acquire(False)
    try:assert session.Swd_Attach(probe()).result==R.Busy and not device.claims and not device.tx
    finally:_LibraryOwner.release()
    assert session.Swd_Attach(probe()).result==R.Ok
    backend=session._backend;backend._deadline=0
    with pytest.raises(SwdError) as error:backend._interface.transfer(b'\xF5',readSize=2)
    assert error.value.result==R.Timeout
    assert session.Swd_Detach().result==R.Ok


def test_stlink_experimental_warning_is_visible_before_connect(swd_panel):
    from transport.probe_inventory import ProbeInventory,ProbeInventoryResult
    window,probes,create=swd_panel
    probes.selection.apply(ProbeInventory(ProbeInventoryResult.Ready,(probe(),)))
    probes.selection.select(probe().identity)
    manager=create(Mock());manager.render()
    assert window.i18n.tr('swd.stlink_experimental') in window.maintenance_page.swd_target_status.text()


def test_minimum_v2_no_core_version_and_invalid_read_are_checked(rig):
    create,_,_=rig;session,device=create();device.jtag=28
    assert session.Swd_Attach(probe()).result==R.Ok
    backend=session._backend;count=len(device.tx)
    with pytest.raises(SwdError) as error:backend.read(0x40000000,4)
    assert error.value.result==R.InvalidRequest and backend._interface.read_window is None and len(device.tx)==count
