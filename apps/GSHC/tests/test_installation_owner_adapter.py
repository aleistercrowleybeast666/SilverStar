"""Real MaintenanceOwner + real serial transport, with a compiled-C fake peer.

No pyserial device is opened. Every peer INFO/event/transaction uses the C DLL.
"""
import ctypes as c
from pathlib import Path
from threading import Event,Thread,get_ident
import sys
import time
import numpy as np

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'SCG/experiments/installation_capture_stream_0_1_3/implementation_v1'))
from c_binding import Library,snapshot
from services.installation_calibration_backend import InstallationBackend,InstallationResult
from services.installation_calibration_protocol import Request_Decode,Response,Response_Encode
from services.installation_calibration_worker import InstallationWorker
from transport.file_service_backend import FileServiceSerialTransport
from transport.installation_owner import InstallationOwnerProvider
from ui import file_transfer
from test_installation_calibration_backend import run_job,MockInstallationOwner
from services.installation_calibration_fit import FACES,FACE_AXES,Policy


class NativeImu(c.Structure):
    _fields_=[('sample_timestamp_us',c.c_uint64),('receive_timestamp_us',c.c_uint64),('sequence',c.c_uint32),
        ('accel_raw',c.c_int32*3),('gyro_raw',c.c_int32*3),('accel',c.c_float*3),('gyro',c.c_float*3),
        ('temperature',c.c_float),('valid_mask',c.c_uint32),('quality_flags',c.c_uint32)]


class NativeMag(c.Structure):
    _fields_=[('sample_timestamp_us',c.c_uint64),('receive_timestamp_us',c.c_uint64),('sequence',c.c_uint32),
        ('raw',c.c_int32*3),('physical',c.c_float*3),('temperature',c.c_float),('valid_mask',c.c_uint32),
        ('calibration_valid',c.c_uint8),('physical_id',c.c_uint16),('descriptor',c.c_uint16),('instance',c.c_uint8)]


class NativeProof(c.Structure):
    _fields_=[('epoch',c.c_uint32),('uncertainty_us',c.c_uint32),('every_native',c.c_uint8),
        ('measurement_time',c.c_uint8),('raw_definition',c.c_uint8),('body_units',c.c_uint8)]


def response(status,op,**fields):
    return Response_Encode(Response(status,op,tuple((key,str(value)) for key,value in fields.items())))


class CPeer:
    def __init__(self):
        self.lib=Library();self.lib.configure(snapshot());self.sid=None;self.rid=0;self.latest=None
        self.lib.dll.SystemInstallationCapture_Configure.argtypes=[c.POINTER(type(self.lib.config))]
        self.lib.dll.SystemInstallationCapture_Configure.restype=c.c_int
        assert self.lib.dll.SystemInstallationCapture_Configure(c.byref(self.lib.config))==0
        self.lib.dll.SystemInstallationCapture_ExecuteLine.argtypes=[c.c_char_p,c.POINTER(c.c_char),c.c_uint16,c.c_uint64]
        self.lib.dll.SystemInstallationCapture_ExecuteLine.restype=None
        self.index=0;self.now=0;self.hold_face=False;self.face_seen=Event();self.old_face=None
        self.late_face_on_cancel=False;self.drop_mag=False
        self.face='XP';self.native_index=0;self.rotation=MockInstallationOwner().rotation
        for name,kind in (('Imu',NativeImu),('Mag',NativeMag)):
            function=getattr(self.lib.dll,'SystemInstallationCapture_'+name+'Observe')
            function.argtypes=[c.POINTER(kind),c.POINTER(NativeProof),c.c_uint64];function.restype=None

    def command(self,data):
        if data==b'SYSTEM INFO\r\n':return b'OK SYSTEM INFO software=0.1.3\r\n'
        return self.command_c(data)

    def command_c(self,data):
        request=Request_Decode(data[:-2]);op,args=request.operation,request.arguments
        events=b''
        if op=='FACE':self.latest='FACE';self.rid=int(args[1]);self.index=0;self.face=args[2].split(':')[2]
        if op=='POLL' and self.latest=='FACE' and self.lib.status().state==3:
            self.now+=200000
            self.feed_native();self.index+=1
            lines=self.lib.drain()
            if self.drop_mag:lines=[line for line in lines if b' MAG ' not in line];self.drop_mag=False
            events=b''.join(lines)
        output=c.create_string_buffer(512)
        self.lib.dll.SystemInstallationCapture_ExecuteLine(data[:-2],output,511,self.now+300)
        reply=output.value+b'\r\n'
        if op=='FACE':
            self.old_face=reply;self.face_seen.set()
            if self.hold_face:return b''
        if op=='DO':
            self.latest='DO';self.rid=int(args[1])
            if self.late_face_on_cancel and self.old_face:reply=self.old_face+reply
        return events+reply

    def feed_native(self):
        # Synthetic physical producer only. Session, selection, metadata,
        # pairing, wire replies and cancellation all execute the real C code.
        a=np.array(FACE_AXES[self.face]);angle=[.13,.87,1.2,2.6,-.45,1.7][FACES.index(self.face)]
        basis=np.eye(3)[int(np.argmin(abs(a)))];tangent=np.cos(angle)*basis+np.sin(angle)*np.cross(a,basis)
        magnetic=self.rotation.T@(.45*a+np.sqrt(1-.45**2)*tangent)*48+np.array([3.,-2.,1.])
        imu=NativeImu();imu.sample_timestamp_us=self.now;imu.receive_timestamp_us=self.now+300
        imu.sequence=self.native_index;imu.accel[:]=tuple(a*9.80665);imu.valid_mask=3
        imu.accel_raw[:]=(1,2,3);imu.gyro_raw[:]=(4,5,6)
        mag=NativeMag();mag.sample_timestamp_us=self.now+100;mag.receive_timestamp_us=self.now+300
        mag.sequence=self.native_index;mag.raw[:]=(7,8,9);mag.physical[:]=tuple(magnetic);mag.valid_mask=3
        first=NativeProof(1,20,1,1,1,1);second=NativeProof(2,30,1,1,1,1)
        self.lib.dll.SystemInstallationCapture_ImuObserve(c.byref(imu),c.byref(first),self.now+300)
        self.lib.dll.SystemInstallationCapture_MagObserve(c.byref(mag),c.byref(second),self.now+300)
        self.native_index+=1
        assert self.lib.status().state in (3,4,5),self.lib.status().reason



class MemorySerial:
    def __init__(self,peer):
        self.peer=peer;self.buffer=bytearray();self.trace=[];self.closed=False;self.owner_thread=None
        self.disconnect=False;self.block_status=False;self.status_entered=Event();self.status_release=Event()
    def _record(self,kind,data=b''):
        assert not self.closed
        thread=get_ident()
        if self.owner_thread is None:self.owner_thread=thread
        assert self.owner_thread==thread
        self.trace.append((time.monotonic(),kind,data,thread));assert len(self.trace)<=10000
    def write(self,data):
        self._record('write',data);self.buffer.extend(self.peer.command(data));return len(data)
    def read(self,size):
        self._record('read')
        if self.disconnect:raise OSError('simulated unplug')
        if not self.buffer:time.sleep(.002);return b''
        result=bytes(self.buffer[:size]);del self.buffer[:size];return result
    def close(self):self._record('close');self.closed=True


def test_real_c_dispatcher_native_adapter_six_faces_fit_export_and_tf_image(owner_setup,tmp_path):
    owner,peer,serial,_=owner_setup
    backend=InstallationBackend(InstallationOwnerProvider(owner,enabled=True),allow_simulated=True)
    worker=InstallationWorker(backend);raw=tmp_path/'c-native-raw.jsonl';candidate=tmp_path/'complete.ssic'
    try:
        assert run_job(worker,'begin',archive_path=raw).result==InstallationResult.Ok
        assert 'runtime_imu' in __import__('json').loads(backend.binding.raw_json)
        for face in FACES:assert run_job(worker,'face',face=face,attempt=1).result==InstallationResult.Ok
        outcome=run_job(worker,'fit',policy=Policy(starts=16))
        assert outcome.result==InstallationResult.CandidateOnly,outcome.reason
        exported=run_job(worker,'export',path=candidate)
        assert exported.result==InstallationResult.CandidateOnly,exported.reason
        from services.installation_calibration_candidate import (Candidate_Decode,InstallationCandidateResult,
            InstallationCandidateStore,OfflineTfObjects)
        result,value=Candidate_Decode(candidate.read_bytes())
        assert result==InstallationCandidateResult.Ok and len(value['validation']['windows'])==6
        assert value['hardware_acceptance']=='NOT_PROVEN'
        store=InstallationCandidateStore(OfflineTfObjects(tmp_path/'offline-tf'))
        assert store.Save(candidate.read_bytes(),value['binding'])[0]==InstallationCandidateResult.Ok
        assert not exported.apply_allowed and backend.cleanup_confirmed
        assert peer.lib.status().resource_owner==0
        assert len({row[3] for row in serial.trace})==1
        assert not any(b' APPLY' in row[2] or b' SAVE' in row[2] or b'UPLOAD' in row[2] for row in serial.trace)
    finally:assert worker.Close().result==InstallationResult.Ok


def test_c_native_adapter_unknown_proof_invalidates_before_publication():
    peer=CPeer();lib=peer.lib;lib.begin();assert lib.face()==10
    sample=NativeImu();sample.valid_mask=3
    lib.dll.SystemInstallationCapture_ImuObserve(c.byref(sample),None,300)
    assert lib.status().state==8 and lib.status().reason==7
    assert lib.peek()[1]==b''
    lib.TestReset()


def test_c_wire_cancel_keeps_do_context_until_held_consumer_is_released():
    peer=CPeer();lib=peer.lib;sid=bytes(lib.sid).hex()
    binding='B-'+bytes(lib.status().binding).hex()[:30]
    assert b'OK INSTALL BEGIN' in peer.command(f'INSTALL BEGIN {sid} 1 {binding}\r\n'.encode())
    assert b'PENDING INSTALL FACE' in peer.command(f'INSTALL FACE {sid} 2 FIT_CHECK:SIX_FACE:XP:1\r\n'.encode())
    peer.now=200000;peer.feed_native();assert lib.peek()[0]==0
    assert b'PENDING INSTALL DO' in peer.command(f'INSTALL DO {sid} 3 CANCEL\r\n'.encode())
    assert lib.status().resource_owner==1
    assert b'cleanup_complete=0' in peer.command(f'INSTALL POLL {sid} 3\r\n'.encode())
    assert lib.EventCommit(0)==0
    assert lib.status().cleanup_complete==1 and lib.status().resource_owner==1
    reply=peer.command(f'INSTALL POLL {sid} 3\r\n'.encode())
    assert b'OK INSTALL DO' in reply and b'cleanup_complete=1' in reply
    assert lib.status().resource_owner==0
    assert peer.command(f'INSTALL DO {sid} 3 CANCEL\r\n'.encode())==reply
    lib.TestReset()


@pytest.fixture(scope='module')
def qt_application():
    app=QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def owner_setup(monkeypatch,qt_application):
    peer=CPeer();serial=MemorySerial(peer);idle=[]
    class StatusClient:
        def __init__(self,*_args,**_kwargs):pass
        def negotiate(self):return {'maintenance_required':'1','status_version':'1'}
        def status(self):
            idle.append(('status',time.monotonic()))
            if serial.block_status:serial.status_entered.set();serial.status_release.wait(.5)
            return None
    class Diagnostics:
        caps=None
        def __init__(self,*_args):pass
        def step(self):idle.append(('diag',time.monotonic()));return None
    monkeypatch.setattr(file_transfer,'FileServiceClient',StatusClient)
    monkeypatch.setattr(file_transfer,'RuntimeDiagnosticsClient',Diagnostics)
    def factory(*_args):return FileServiceSerialTransport('TEST_ONLY',115200,serial_factory=lambda **_kwargs:serial)
    owner=file_transfer.MaintenanceOwner('TEST_ONLY',115200,transport_factory=factory,installation_capture_enabled=True)
    owner.start();assert owner.connected.wait(2)
    deadline=time.monotonic()+2
    while not owner._maintenance_initialized and time.monotonic()<deadline:time.sleep(.005)
    assert owner._maintenance_initialized
    yield owner,peer,serial,idle
    owner.request_stop();assert owner.wait(3000)
    assert serial.closed
    peer.lib.TestReset()


def acquire(owner):
    provider=InstallationOwnerProvider(owner,enabled=True)
    for _ in range(100):
        lease=provider.Acquire('installation')
        if lease:return lease
        time.sleep(.005)
    raise AssertionError('owner did not admit a session within its idle gap')


def test_owner_adapter_is_default_off_and_never_registered_by_gui(owner_setup):
    owner,_,serial,_=owner_setup
    assert InstallationOwnerProvider(owner).Acquire('installation') is None
    owner._installation_capture_enabled=False
    assert InstallationOwnerProvider(owner,enabled=True).Acquire('installation') is None
    assert not any(row[2].startswith(b'INSTALL ') for row in serial.trace)


def test_real_owner_holds_one_reader_for_c_info_capture_and_cleanup(owner_setup,tmp_path):
    owner,peer,serial,idle=owner_setup
    backend=InstallationBackend(InstallationOwnerProvider(owner,enabled=True),allow_simulated=True)
    worker=InstallationWorker(backend)
    try:
        for _ in range(30):
            result=run_job(worker,'begin',archive_path=tmp_path/'real_owner_c.jsonl')
            if result.result!=InstallationResult.Busy:break
            time.sleep(.01)
        assert result.result==InstallationResult.Ok
        start=time.monotonic();before=len(idle)
        assert not owner.submit(None,list_only=True)
        assert not owner.submit_command('MAG 0 STREAM START')
        assert InstallationOwnerProvider(owner,enabled=True).Acquire('installation') is None
        result=run_job(worker,'face',face='XP',attempt=1)
        assert result.result==InstallationResult.Ok and len(backend.dataset.records)==6
        assert len(idle)==before
        assert run_job(worker,'close').result==InstallationResult.Ok
        assert peer.lib.status().resource_owner==0
        commands=[row[2] for row in serial.trace if row[1]=='write' and row[0]>=start]
        assert all(cmd.startswith(b'INSTALL ') for cmd in commands)
        assert not any(word in cmd for cmd in commands for word in (b'APPLY',b'SAVE',b'UPLOAD',b'LOGFILE'))
        assert serial.owner_thread!=get_ident()
    finally:worker.Close()


def test_cancelled_real_request_quarantines_late_face_and_confirms_c_cleanup(owner_setup,tmp_path):
    owner,peer,serial,_=owner_setup;peer.hold_face=True;peer.late_face_on_cancel=True
    backend=InstallationBackend(InstallationOwnerProvider(owner,enabled=True),allow_simulated=True);worker=InstallationWorker(backend)
    try:
        for _ in range(30):
            result=run_job(worker,'begin',archive_path=tmp_path/'cancelled_c.jsonl')
            if result.result!=InstallationResult.Busy:break
            time.sleep(.01)
        assert result.result==InstallationResult.Ok
        from services.installation_calibration_worker import InstallationJob
        assert worker.Submit(InstallationJob('face',(('face','XP'),('attempt',1)))).result==InstallationResult.Ok
        assert peer.face_seen.wait(2);worker.Cancel()
        deadline=time.monotonic()+3;result=None
        while time.monotonic()<deadline:
            result=worker.TakeResult()
            if result:break
            time.sleep(.005)
        assert result and result.result==InstallationResult.Cancelled
        assert backend.cleanup_confirmed and not backend.dataset.records
        assert peer.lib.status().cleanup_complete==1 and peer.lib.status().resource_owner==0
        assert any(row[2].endswith(b' CANCEL\r\n') for row in serial.trace if row[1]=='write')
    finally:worker.Close()


def test_timed_out_request_cannot_admit_late_success_or_second_owner(owner_setup):
    owner,peer,serial,_=owner_setup
    lease=acquire(owner)
    # First synchronize and bind normally, then leave one real FACE reply absent.
    cancel=Event()
    lease.Request(b'INSTALL CAPS\r\n',deadline=time.monotonic()+2,cancel=cancel)
    sid='1'*32;binding='B-'+bytes(peer.lib.status().binding).hex()[:30]
    lease.Request(f'INSTALL BEGIN {sid} 1 {binding}\r\n'.encode(),deadline=time.monotonic()+1,cancel=cancel)
    peer.hold_face=True
    with pytest.raises(TimeoutError):
        lease.Request(f'INSTALL FACE {sid} 2 FIT_CHECK:SIX_FACE:XP:1\r\n'.encode(),deadline=time.monotonic()+.05,cancel=cancel)
    serial.buffer.extend(peer.old_face)
    with pytest.raises((OSError,InterruptedError)):
        lease.Request(b'INSTALL CAPS\r\n',deadline=time.monotonic()+1,cancel=cancel)
    assert lease.Release() is False
    assert owner.wait(2000) and owner._installation_poisoned
    assert InstallationOwnerProvider(owner,enabled=True).Acquire('installation') is None


def test_request_reentry_is_rejected_before_the_serial_queue(owner_setup):
    owner,_,serial,_=owner_setup;lease=acquire(owner)
    assert lease._request_lock.acquire(False)
    before=len(serial.trace)
    try:
        with pytest.raises(RuntimeError,match='ONE_INSTALLATION_EXCHANGE'):
            lease.Request(b'INSTALL CAPS\r\n',deadline=time.monotonic()+1,cancel=Event())
    finally:lease._request_lock.release()
    assert len(serial.trace)==before and lease.Release()


def test_real_owner_does_not_admit_a_session_during_an_idle_exchange(owner_setup):
    owner,_,serial,_=owner_setup;serial.block_status=True
    assert serial.status_entered.wait(2)
    assert InstallationOwnerProvider(owner,enabled=True).Acquire('installation') is None
    serial.block_status=False;serial.status_release.set()
    lease=acquire(owner);assert lease.Release()


def test_disconnected_transport_cannot_release_a_fresh_second_reader(owner_setup):
    owner,_,serial,_=owner_setup;lease=acquire(owner);serial.disconnect=True
    with pytest.raises(OSError):lease.Request(b'INSTALL CAPS\r\n',deadline=time.monotonic()+1,cancel=Event())
    assert lease.Release() is False and owner.wait(2000)
    assert serial.closed and InstallationOwnerProvider(owner,enabled=True).Acquire('installation') is None


def test_wire_loss_of_a_real_c_part_never_publishes_a_complete_face(owner_setup,tmp_path):
    owner,peer,_,_=owner_setup;peer.drop_mag=True
    backend=InstallationBackend(InstallationOwnerProvider(owner,enabled=True),allow_simulated=True);worker=InstallationWorker(backend)
    try:
        for _ in range(30):
            result=run_job(worker,'begin',archive_path=tmp_path/'dropped_c_part.jsonl')
            if result.result!=InstallationResult.Busy:break
            time.sleep(.01)
        assert result.result==InstallationResult.Ok
        result=run_job(worker,'face',face='XP',attempt=1)
        assert result.result==InstallationResult.Failed and not backend.dataset.records
        assert not result.apply_allowed and backend.cleanup_confirmed
    finally:worker.Close()
