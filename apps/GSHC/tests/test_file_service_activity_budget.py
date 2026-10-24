"""Long healthy transfers must outlive one transaction without waiting forever."""
import json
from threading import Event
import pytest

from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError
from services.file_service_jobs import LogExportJob, TransferBudgetCancel
from services.maintenance_api import MaintenanceRequest, Maintenance_Execute
from test_file_service_client import MockTransport


class Clock:
    value=0.0
    def monotonic(self):return self.value


class ClockWire(MockTransport):
    def __init__(self,clock):
        super().__init__(bytes(range(256))*4)
        self.clock=clock
    def exchange(self,command,timeout,cancel):
        self.clock.value+=.2
        return super().exchange(command,timeout,cancel)


def test_healthy_bytes_renew_job_beyond_old_total_deadline(tmp_path,monkeypatch):
    clock=Clock()
    monkeypatch.setattr('services.file_service_jobs.time.monotonic',clock.monotonic)
    wire=ClockWire(clock)
    report=LogExportJob(tmp_path,file_ids=(1,),maintenance_authorized=True,timeout=2).run(FileServiceClient(wire))
    assert clock.value>2
    manifest=json.loads((tmp_path/report.output/'manifest.json').read_text())
    assert len(manifest['files'])==1 and manifest['files'][0]['size_bytes']==len(wire.data)
    assert not any('DELETE' in command for command in wire.commands)


def test_shared_api_does_not_reimpose_expired_total_deadline(tmp_path,monkeypatch):
    clock=Clock()
    monkeypatch.setattr('services.file_service_jobs.time.monotonic',clock.monotonic)
    wire=ClockWire(clock)
    request=MaintenanceRequest('download','SIMULATED',destination=str(tmp_path),file_ids=(1,),enter_maintenance=True,timeout=2)
    reply=Maintenance_Execute(request,_transport_factory=lambda *_:wire)
    assert clock.value>2 and reply['result']=='ok' and wire.closed
    assert reply['verified_files'][0]['size_bytes']==len(wire.data)


def budget(clock,seconds=2,**kwargs):
    def sleep(delay):clock.value+=delay
    return TransferBudgetCancel(Event(),seconds,clock=clock.monotonic,sleep=sleep,**kwargs)


def test_idle_cannot_be_revived_by_late_activity():
    clock=Clock();lease=budget(clock)
    clock.value=2
    with pytest.raises(TimeoutError,match='inactivity'):lease.Activity_Record()
    assert lease.last_activity==0


@pytest.mark.parametrize('phase',['Transaction','Phase'])
def test_activity_never_extends_absolute_request_or_ready_phase(phase):
    clock=Clock();lease=budget(clock)
    getattr(lease,phase+'_Begin')()
    for value in (.5,1,1.5):
        clock.value=value;lease.Activity_Record()
    clock.value=2
    with pytest.raises(TimeoutError,match='deadline'):lease.Activity_Record()


def test_total_cap_survives_successful_transactions():
    clock=Clock();lease=budget(clock,total_seconds=4)
    for value in (1,2,3):
        clock.value=value;lease.Transaction_Begin();lease.Activity_Record();lease.Transaction_End()
    clock.value=4
    with pytest.raises(TimeoutError,match='safety cap'):lease.Activity_Record()


def test_cancel_interrupts_backoff_without_renewing_lease():
    clock=Clock();lease=budget(clock)
    def sleep(delay):
        clock.value+=delay
        if clock.value>=.015:lease.event.set()
    lease.sleep=sleep
    assert lease.wait(1) and .015<=clock.value<=.02
    with pytest.raises(ExportCancelled):lease.Activity_Record()
    assert lease.last_activity==0


def test_repeated_valid_pending_expires_and_releases_request_bound():
    clock=Clock();lease=budget(clock)
    class PendingWire:
        def exchange(self,*_):
            clock.value+=.4
            return 'PENDING LOGFILE META request_id=1'
    client=FileServiceClient(PendingWire(),cancel=lease)
    with pytest.raises(TimeoutError,match='transaction deadline'):client.metadata(1)
    assert lease.transaction_deadline is None and lease.last_activity>1


@pytest.mark.parametrize('reply',[
    'PENDING LOGFILE READ request_id=1',
    'PENDING LOGFILE META request_id=0',
    'PENDING LOGFILE META request_id=1 request_id=1',
])
def test_invalid_pending_never_renews_activity(reply):
    clock=Clock();lease=budget(clock)
    class InvalidWire:
        def exchange(self,*_):clock.value=1;return reply
    with pytest.raises(FileServiceError):FileServiceClient(InvalidWire(),cancel=lease).metadata(1)
    assert lease.last_activity==0 and lease.transaction_deadline is None


@pytest.mark.parametrize('size',[0,1,63,64,65,511,512,513])
def test_download_boundary_sizes_still_verify(tmp_path,size):
    wire=MockTransport(bytes(index%256 for index in range(size)))
    report=LogExportJob(tmp_path,file_ids=(1,),maintenance_authorized=True,timeout=2).run(FileServiceClient(wire))
    assert (tmp_path/report.output/report.files[0]['path']).read_bytes()==wire.data
    assert report.files[0]['size_bytes']==size


def test_healthy_transfer_exceeds_old_gui_300_second_bound(tmp_path,monkeypatch):
    clock=Clock();monkeypatch.setattr('services.file_service_jobs.time.monotonic',clock.monotonic)
    wire=ClockWire(clock);wire.data=bytes(range(256))*200
    report=LogExportJob(tmp_path,file_ids=(1,),maintenance_authorized=True).run(FileServiceClient(wire))
    assert clock.value>300 and len(report.files)==1
    assert (tmp_path/report.output/report.files[0]['path']).read_bytes()==wire.data
