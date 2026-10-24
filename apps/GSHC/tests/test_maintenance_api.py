"""Structured automation and shared GUI job faults; synthetic transport only."""
import json
import time
import zlib
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from maintenance_cli import MaintenanceCli_Run
from services.file_service_client import FileServiceClient, FileServiceError
from services.file_service_jobs import LogExportJob
from services.maintenance_api import Maintenance_Execute, MaintenanceRequest
from test_file_service_client import MockTransport


class MultiWire(MockTransport):
    def __init__(self):
        super().__init__()
        self.logs={1:b'first-closed-log',2:bytes(range(200))}

    def exchange(self,command,timeout,cancel):
        if command.startswith('LOGFILE POLL') and self.pending:
            op=self.pending[1]
            if op=='LIST':
                self.commands.append(command)
                cursor=int(self.pending[2]);ids=list(self.logs)
                prefix=f'OK LOGFILE LIST request_id={self.request_id}'
                return prefix+(' end=1 next_cursor=0' if cursor==len(ids) else
                    f' file_id={ids[cursor]} size={len(self.logs[ids[cursor]])} closed=1 next_cursor={cursor+1} end=0')
            if op in ('META','READ'):
                identifier=int(self.pending[2]);original=self.data
                self.data=self.logs[identifier]
                try:return super().exchange(command,timeout,cancel).replace('file_id=1 ',f'file_id={identifier} ')
                finally:self.data=original
        return super().exchange(command,timeout,cancel)


def execute(wire,operation='probe',**kwargs):
    return Maintenance_Execute(MaintenanceRequest(operation,'COM_MOCK',**kwargs),_transport_factory=lambda *_:wire)


@pytest.mark.parametrize('operation',['probe','status'])
def test_discovery_and_status_never_enter_or_submit_file_work(operation):
    wire=MultiWire();reply=execute(wire,operation)
    assert reply['result']=='ok' and wire.closed
    assert all(command in ('LOGFILE CAPS','LOGFILE STATUS') for command in wire.commands)
    assert not reply['maintenance_enter_attempted'] and reply['source_logs_preserved']


@pytest.mark.parametrize('operation',['list','download'])
def test_missing_explicit_authorization_does_not_open_port(operation,tmp_path):
    factory=Mock(side_effect=AssertionError('Unauthorized request opened a port'))
    kwargs={'destination':str(tmp_path)} if operation=='download' else {}
    reply=Maintenance_Execute(MaintenanceRequest(operation,'COM_MOCK',**kwargs),_transport_factory=factory)
    assert reply['result']=='maintenance_required' and reply['release']=='not_opened'
    factory.assert_not_called()


def test_selected_copy_has_crc_sha_manifest_and_preserves_every_remote_log(tmp_path):
    wire=MultiWire();before=dict(wire.logs)
    reply=execute(wire,'download',destination=str(tmp_path),file_ids=(2,),enter_maintenance=True)
    assert reply['result']=='ok' and reply['maintenance_enter_attempted']
    output=Path(reply['output']);logs=list(output.glob('*.sslog'))
    assert len(logs)==1 and logs[0].read_bytes()==wire.logs[2] and wire.logs==before
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['files'][0]['file_id']==2
    assert manifest['files'][0]['crc32']==f'{zlib.crc32(wire.logs[2]):08X}'
    assert not manifest['recorded_descriptor_included'] and not manifest['decoder_package_included']
    assert not any('DELETE' in command or command.startswith('LOGFILE READ 1 ') for command in wire.commands)


def test_all_closed_copy_is_explicit_and_uses_a_fresh_catalog(tmp_path):
    wire=MultiWire()
    reply=execute(wire,'download',destination=str(tmp_path),enter_maintenance=True)
    assert reply['result']=='ok' and reply['export']['selected_ids']==(1,2)
    assert len(list(Path(reply['output']).glob('*.sslog')))==2
    assert not any('DELETE' in command for command in wire.commands)


def test_stale_selection_and_active_lifecycle_fail_before_read_or_enter(tmp_path):
    wire=MultiWire()
    reply=execute(wire,'download',destination=str(tmp_path),file_ids=(9,),enter_maintenance=True)
    assert reply['result']=='stale' and not any(' READ ' in command for command in wire.commands)
    wire=MultiWire();wire.mutate=lambda text:text.replace('lifecycle=2','lifecycle=4')
    reply=execute(wire,'list',enter_maintenance=True)
    assert reply['result']=='busy' and not reply['maintenance_enter_attempted']
    assert 'LOGFILE ENTER' not in wire.commands


def test_whole_job_deadline_bounds_pending_mailbox_and_closes():
    class Pending(MultiWire):
        def exchange(self,command,timeout,cancel):
            if command.startswith('LOGFILE POLL'):
                self.commands.append(command)
                return f'PENDING LOGFILE LIST request_id={self.request_id}'
            return super().exchange(command,timeout,cancel)
    wire=Pending();started=time.monotonic()
    reply=execute(wire,'list',enter_maintenance=True,timeout=.12)
    assert reply['result']=='timeout' and time.monotonic()-started<1 and wire.closed
    assert wire.commands[-1]=='LOGFILE CANCEL'


def test_pending_log_closure_is_bounded_and_never_lists():
    wire=MultiWire()
    wire.mutate=lambda text:text.replace('maintenance=2','maintenance=1')
    reply=execute(wire,'list',enter_maintenance=True,timeout=.12)
    assert reply['result']=='timeout' and wire.closed and reply['maintenance_enter_attempted']
    assert not any(command.startswith('LOGFILE LIST') for command in wire.commands)


def test_cancel_crc_failure_and_close_failure_never_report_success(tmp_path):
    wire=MultiWire();cancel=Event();cancel.set()
    reply=Maintenance_Execute(MaintenanceRequest('probe','COM_MOCK'),cancel=cancel,_transport_factory=lambda *_:wire)
    assert reply['result']=='cancelled' and not wire.commands
    wire=MultiWire();wire.mutate=lambda text:text.replace('crc32=','crc32=00000000') if ' data=' in text else text
    reply=execute(wire,'download',destination=str(tmp_path),file_ids=(2,),enter_maintenance=True)
    assert reply['result']=='bad_response' and not list(Path(reply['output']).glob('manifest.json'))
    assert list(Path(reply['output']).glob('*.partial'))
    wire=MultiWire();wire.close=Mock(side_effect=OSError('close refused'))
    assert execute(wire)['result']=='release_failed'


def test_local_modification_before_manifest_is_rejected(tmp_path):
    client=FileServiceClient(MultiWire());download=client.download
    def altered(*args,**kwargs):
        path=download(*args,**kwargs);path.write_bytes(b'changed locally');return path
    client.download=altered
    job=LogExportJob(tmp_path,file_ids=(2,),maintenance_authorized=True)
    with pytest.raises(FileServiceError,match='changed before manifest'):
        job.run(client)
    assert not (job.output/'manifest.json').exists()


def test_cli_returns_one_structured_json_result_and_requires_selection(capsys,tmp_path):
    wire=MultiWire()
    runner=lambda request:Maintenance_Execute(request,_transport_factory=lambda *_:wire)
    code=MaintenanceCli_Run(['download','--port','COM_MOCK','--destination',str(tmp_path),
        '--mission','2','--enter-maintenance'],_execute=runner)
    assert code==0 and json.loads(capsys.readouterr().out)['export']['selected_ids']==[2]
    with pytest.raises(SystemExit):MaintenanceCli_Run(['download','--port','COM_MOCK','--destination',str(tmp_path)],_execute=runner)
