"""Real GUI maintenance owner -> serial codec -> C active consumer/TF owner.

Physical provider, CAPS qualification and media are explicit test facades.
The exported candidate numerical/holdout contract has separate regressions.
"""
import ctypes as c
import os
import time

import pytest
from PySide6.QtWidgets import QApplication

from services.installation_calibration_backend import InstallationBackend, InstallationResult
from services.installation_calibration_worker import InstallationWorker
from transport.file_service_backend import FileServiceSerialTransport
from transport.installation_owner import InstallationOwnerProvider
from ui import file_transfer
from test_installation_calibration_backend import run_job
from test_installation_owner_adapter import MemorySerial


class ActivePeer:
    def __init__(self):
        self.dll=c.CDLL(os.environ['INSTALLATION_ACTIVE_DLL'])
        self.dll.Harness_Execute.argtypes=[c.c_char_p,c.POINTER(c.c_char)]
        self.dll.Harness_Execute.restype=c.c_uint8
        self.dll.Harness_Packet.argtypes=[c.POINTER(c.c_uint8)]
        self.dll.Harness_Reset()
        packet=(c.c_uint8*228)();self.dll.Harness_Packet(packet);self.packet=bytes(packet)
        self.corrupt_read=False;self.mismatched_context=False

    def command(self,data):
        if data==b'SYSTEM INFO\r\n':return b'OK SYSTEM INFO software=0.1.3\r\n'
        out=c.create_string_buffer(512)
        assert self.dll.Harness_Execute(data[:-2],out)==1
        response=out.value
        if data.startswith(b'INSTALL READ ') and self.corrupt_read:
            start=response.index(b'data=')+5
            response=response[:start]+(b'00' if response[start:start+2]!=b'00' else b'01')+response[start+2:]
        return response+b'\r\n'


@pytest.fixture
def active_owner(monkeypatch):
    app=QApplication.instance() or QApplication([])
    peer=ActivePeer();serial=MemorySerial(peer)
    class Status:
        def __init__(self,*args,**kwargs):pass
        def negotiate(self):return {'maintenance_required':'1','status_version':'1'}
        def status(self):return None
    class Diagnostics:
        caps=None
        def __init__(self,*args):pass
        def step(self):return None
    monkeypatch.setattr(file_transfer,'FileServiceClient',Status)
    monkeypatch.setattr(file_transfer,'RuntimeDiagnosticsClient',Diagnostics)
    def factory(*args):return FileServiceSerialTransport('SYNTHETIC_ACTIVE',115200,serial_factory=lambda **kwargs:serial)
    owner=file_transfer.MaintenanceOwner('SYNTHETIC_ACTIVE',115200,transport_factory=factory,installation_capture_enabled=True)
    owner.start();assert owner.connected.wait(2)
    deadline=time.monotonic()+2
    while not owner._maintenance_initialized and time.monotonic()<deadline:time.sleep(.005)
    assert owner._maintenance_initialized
    from services import installation_calibration_active_transfer as transfer
    monkeypatch.setattr(transfer,'_Candidate_Read',lambda path:peer.packet)
    backend=InstallationBackend(InstallationOwnerProvider(owner,enabled=True),allow_simulated=True)
    worker=InstallationWorker(backend)
    assert run_job(worker,'probe').result==InstallationResult.Ok
    yield peer,serial,owner,backend,worker
    worker.Close();owner.request_stop();assert owner.wait(3000)
    assert serial.closed


def test_real_active_upload_apply_save_reboot_readback_and_single_reader(active_owner):
    peer,serial,owner,backend,worker=active_owner
    result=run_job(worker,'apply',candidate_path='synthetic-validated-kind3')
    assert result.result==InstallationResult.Ok,result.reason
    assert result.detail['active']=='1' and result.detail['valid']=='1' and result.detail['saved']=='0'
    assert backend.status=='APPLIED_NOT_SAVED'
    result=run_job(worker,'save')
    assert result.result==InstallationResult.Ok,result.reason
    assert result.detail['saved_generation']=='1' and result.detail['loaded']=='0'
    assert backend.lease is None and backend.cleanup_confirmed
    peer.dll.Harness_Reboot()
    result=run_job(worker,'verify_saved',candidate_path='synthetic-validated-kind3')
    assert result.result==InstallationResult.Ok,result.reason
    assert result.detail['loaded']=='1' and result.detail['saved_generation']=='1'
    assert len({row[3] for row in serial.trace})==1
    assert any(row[2].startswith(b'INSTALL STATUS B-') for row in serial.trace if row[1]=='write')


@pytest.mark.parametrize('fault',[1,2])
def test_failed_write_or_committed_bad_readback_is_never_saved(active_owner,fault):
    peer,serial,owner,backend,worker=active_owner
    assert run_job(worker,'apply',candidate_path='fixture').result==InstallationResult.Ok
    peer.dll.Harness_Fault(fault)
    result=run_job(worker,'save')
    assert result.result==InstallationResult.Failed and backend.status!='SAVED_READBACK_VERIFIED'
    assert backend.lease is None


def test_wrong_readback_never_publishes_applied_success(active_owner):
    peer,serial,owner,backend,worker=active_owner
    peer.corrupt_read=True
    result=run_job(worker,'apply',candidate_path='fixture')
    assert result.result==InstallationResult.Failed
    assert 'READBACK' in result.reason and backend.lease is None
