"""Progress is evidence of bytes received, never evidence of verification."""
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import zlib

import pytest

from services.file_service_client import FileServiceClient, FileServiceError
from services.device_export import ExportCancelled
from services.file_service_jobs import LogExportJob
from services.transfer_progress import TransferProgress, ProgressThrottle, BatchProgress
from test_file_service_client import MockTransport
from transport.file_service_backend import FileServiceSerialTransport


def test_batch_uses_total_bytes_and_never_resets_between_files(tmp_path):
    class Client:
        cancel = Event()
        catalog_sizes = {1:1,2:9}
        def _check(self):assert not self.cancel.is_set()
        def status(self):return SimpleNamespace(age_ms=0,lifecycle=2)
        def enter_maintenance(self):pass
        def list_closed(self):return [1,2]
        def download(self,identifier,root,*,progress,byte_progress):
            data = b'x'*self.catalog_sizes[identifier]
            byte_progress(0,None,'metadata')
            byte_progress(len(data),len(data),'receiving')
            byte_progress(len(data),len(data),'verifying')
            path = root/f'mission_{identifier:06d}_1-{zlib.crc32(data):08X}-{len(data):08X}.sslog'
            path.write_bytes(data)
            byte_progress(len(data),len(data),'verified')
            return path
    events=[]
    report=LogExportJob(tmp_path,maintenance_authorized=True).run(Client(),byte_progress=events.append)
    received=[item for item in events if item.stage=='receiving']
    assert [(item.received,item.total) for item in received]==[(1,10),(10,10)]
    assert [item.received for item in events]==sorted(item.received for item in events)
    assert events[-1].stage=='verified' and not any(item.stage=='complete' for item in events)
    assert Path(report.output,'manifest.json').is_file()


def test_unknown_total_remains_unknown_until_all_metadata_is_known():
    events=[];batch=BatchProgress((1,2),{},events.append)
    batch.update(1,3,3,'receiving');batch.completed=3
    batch.update(2,0,None,'metadata');batch.update(2,4,4,'receiving')
    assert events[0].total is None and events[1].total is None
    assert (events[-1].received,events[-1].total)==(7,7)


def test_throttle_limits_chunks_but_emits_stages_and_terminal_immediately():
    now=[0.0];events=[];throttle=ProgressThrottle(events.append,clock=lambda:now[0])
    for count in range(101):
        now[0]=count*.001;throttle(TransferProgress(count,100,'receiving',1,1))
    throttle(TransferProgress(100,100,'verifying',1,1))
    throttle(TransferProgress(100,100,'failed',1,1))
    assert len(events)<=4
    assert [item.stage for item in events[-2:]]==['verifying','failed']


def test_client_reports_verification_after_final_validated_chunk(tmp_path):
    events=[];wire=MockTransport(bytes(range(160)))
    path=FileServiceClient(wire).download(1,tmp_path,byte_progress=lambda *item:events.append(item))
    assert events[:2]==[(0,None,'capabilities'),(0,None,'metadata')]
    assert (160,160,'receiving') in events
    assert events[-2:]==[(160,160,'verifying'),(160,160,'verified')]
    assert path.read_bytes()==wire.data


def test_corrupt_chunk_cannot_earn_received_bytes_or_verified_status(tmp_path):
    events=[];wire=MockTransport()
    wire.mutate=lambda line:line.replace('crc32=CBF43926 data=','crc32=00000000 data=')
    with pytest.raises(FileServiceError):
        FileServiceClient(wire).download(1,tmp_path,byte_progress=lambda *item:events.append(item))
    assert all(done==0 for done,_,_ in events)
    assert not any(stage in {'verified','complete'} for _,_,stage in events)
    assert not list(tmp_path.glob('*.sslog'))


def test_short_serial_tail_does_not_wait_for_full_128_byte_read():
    class SerialModel:
        def __init__(self):self.data=bytearray(b'OK SYSTEM INFO firmware=0.1.3\r\n');self.tail_waits=0
        @property
        def in_waiting(self):return len(self.data)
        def read(self,size):
            if size>len(self.data):self.tail_waits+=1
            data=bytes(self.data[:size]);del self.data[:size];return data
    old=SerialModel();expected=old.read(128)
    wire=SerialModel();transport=FileServiceSerialTransport.__new__(FileServiceSerialTransport)
    transport._serial=wire;observed=[];transport.receive_observer=observed.append
    assert transport._read(128)==expected and observed==[expected]
    assert old.tail_waits==1 and wire.tail_waits==0


def test_serial_taint_retains_last_command_and_sends_no_second_request():
    class Serial:
        in_waiting=0
        def __init__(self):self.sent=[]
        def write(self,data):self.sent.append(data);return len(data)
        def read(self,size):return b''
        def close(self):pass
    serial=Serial();transport=FileServiceSerialTransport('TEST',115200,serial_factory=lambda **_:serial)
    transport._needs_sync=False
    with pytest.raises(TimeoutError):transport.exchange('SYSTEM STATUS',.001,Event())
    with pytest.raises(OSError,match='last incomplete command: SYSTEM STATUS'):
        transport.exchange('SYSTEM INFO',.001,Event())
    assert serial.sent==[b'SYSTEM STATUS\r\n'] and transport.requires_reconnect


def test_cancel_while_meta_is_pending_explains_empty_output_directory(tmp_path):
    wire=MockTransport();cancel=Event();events=[]
    def pending_meta(line):
        if line.startswith('OK LOGFILE META '):
            cancel.set()
            return f'PENDING LOGFILE META request_id={wire.request_id}'
        return line
    wire.mutate=pending_meta
    client=FileServiceClient(wire,cancel=cancel)
    job=LogExportJob(tmp_path,file_ids=(1,),maintenance_authorized=True)
    with pytest.raises(ExportCancelled):job.run(client,byte_progress=events.append)
    assert job.output.is_dir() and list(job.output.iterdir())==[]
    assert events[-1].stage=='metadata' and events[-1].received==0
    assert not any(' READ ' in command or ' DELETE ' in command for command in wire.commands)
    assert wire.data==b'123456789'


def test_worker_failure_flushes_latest_confirmed_bytes_within_refresh_interval(tmp_path,monkeypatch):
    import re
    from PySide6.QtWidgets import QApplication
    from ui import file_transfer
    app=QApplication.instance() or QApplication([])
    wire=MockTransport(bytes(range(200)))
    wire.mutate=lambda line:re.sub(r'crc32=[0-9A-F]{8} data=','crc32=00000000 data=',line) if line.startswith('OK LOGFILE READ ') and 'offset=128 ' in line else line
    monkeypatch.setattr(file_transfer,'ProgressThrottle',lambda emit:ProgressThrottle(emit,clock=lambda:0))
    worker=file_transfer.DownloadWorker('SYNTHETIC',115200,tmp_path,transport_factory=lambda *_:wire)
    events=[];failures=[]
    worker.byte_progress.connect(events.append);worker.failed.connect(failures.append)
    worker.run()
    assert failures and events[-1].stage=='failed' and events[-1].received==128
    assert next(tmp_path.glob('SilverStar_download_*/*.partial')).stat().st_size==128
    assert not list(tmp_path.glob('SilverStar_download_*/*.sslog'))
    assert wire.closed and wire.data==bytes(range(200))
    worker.deleteLater();app.processEvents()
