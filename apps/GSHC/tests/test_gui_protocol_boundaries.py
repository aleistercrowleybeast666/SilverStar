"""Offline GUI protocol boundaries; no native serial or SWD I/O."""
from threading import Event
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtCore import Qt
from services.device_export import ExportCancelled
from services.i18n import I18n
from services.file_service_client import FileServiceClient,FileServiceError,FileServiceResult
from services.maintenance_commands import ConsoleCommand_Validate
from transport.file_service_backend import FileServiceSerialTransport
from ui.file_transfer import MaintenanceOwner,_Console_Execute
from ui.maintenance_console import MaintenanceConsole
from test_file_service_client import MockTransport


def wire(responses):
    class Wire:
        def __init__(self):self.tx=[];self.chunks=[]
        def write(self,data):
            self.tx.append(data);self.chunks.extend(responses.get(data.decode().strip(),[]));return len(data)
        def read(self,size):return self.chunks.pop(0) if self.chunks else b''
    serial=Wire();transport=FileServiceSerialTransport.__new__(FileServiceSerialTransport)
    transport._serial=serial;transport._buffer=bytearray();transport._requests={}
    transport._sync_failed=False;transport._needs_sync=False
    return transport,serial


@pytest.mark.parametrize('command,response',[
    ('SYSTEM STARTUP GNSS','OK SYSTEM STARTUP GNSS id=2 present=1'),
    ('SYSTEM START RESULT','OK SYSTEM START RESULT state=COMPLETE request_id=3 result=FAILED'),
    ('GNSS 0 STATUS','OK GNSS 0 STATUS online=1'),
    ('GNSS 255 NAV SAT','OK GNSS 255 NAV SAT count=2'),
    ('BARO 0 SAMPLE DETAIL','OK BARO 0 SAMPLE DETAIL sequence=7'),
])
def test_console_prefix_with_instance_and_subcommand(command,response):
    transport,serial=wire({command:[b'EVENT CAL FACE result=PASSED\r\n',
        b'OK GNSS 3 STATUS online=0\r\n',b'OK SYSTEM STARTUP IMU id=1 present=1\r\n',
        b'OK SYSTEM START state=PENDING request_id=2\r\n',(response+'\r\n').encode()]})
    assert transport.exchange(command,.2,Event())==response
    assert serial.tx==[(command+'\r\n').encode()]


def test_poll_routes_original_operation_and_request_id():
    transport,serial=wire({
        'LOGFILE META 1':[b'OK LOGFILE LIST request_id=8 end=1\r\nPENDING LOGFILE META request_id=9\r\n'],
        'LOGFILE POLL 9':[b'OK LOGFILE META request_id=8 file_id=2\r\n',
            b'OK LOGFILE READ request_id=9 offset=0\r\n',b'OK LOGFILE META request_id=9 file_id=1\r\n']})
    assert transport.exchange('LOGFILE META 1',.2,Event())=='PENDING LOGFILE META request_id=9'
    assert transport.exchange('LOGFILE POLL 9',.2,Event())=='OK LOGFILE META request_id=9 file_id=1'
    assert transport._requests=={}


def test_caps_ignores_unrelated_errors_but_accepts_legacy_parse_rejection():
    transport,serial=wire({'LOGFILE CAPS':[b'ERR CAL STATUS code=BUSY\r\n',
        b'ERR LOGFILE META code=BAD_COMMAND\r\n',b'ERR LOGFILE PARSE code=BAD_MODULE\r\n']})
    with pytest.raises(FileServiceError) as caught:FileServiceClient(transport).negotiate()
    assert caught.value.result==FileServiceResult.UNSUPPORTED
    assert serial.tx==[b'LOGFILE CAPS\r\n'] and not transport._sync_failed


def test_timeout_or_cancel_after_write_requires_reconnect():
    transport,serial=wire({})
    with pytest.raises(TimeoutError):transport.exchange('LOGFILE STATUS',.01,Event())
    with pytest.raises(OSError,match='reconnect'):transport.exchange('LOGFILE CAPS',.01,Event())
    assert serial.tx==[b'LOGFILE STATUS\r\n']
    transport,serial=wire({});cancel=Event()
    def read(_):cancel.set();return b''
    serial.read=read
    with pytest.raises(ExportCancelled):transport.exchange('LOGFILE STATUS',.01,cancel)
    with pytest.raises(OSError,match='reconnect'):transport.exchange('LOGFILE CAPS',.01,Event())


def test_console_async_read_has_no_enter_or_filesystem_side_effect(tmp_path,monkeypatch):
    token='1-CBF43926-00000009';command=f'LOGFILE READ 1 {token} 0'
    transport,serial=wire({command:[b'PENDING LOGFILE READ request_id=11\r\n'],
        'LOGFILE POLL 11':[(f'OK LOGFILE READ request_id=11 file_id=1 token={token} offset=0 length=9 data=313233343536373839 crc32=CBF43926\r\n').encode()]})
    monkeypatch.chdir(tmp_path)
    response,error=_Console_Execute(transport,command,Event())
    assert not error and 'PENDING LOGFILE READ request_id=11' in response and 'data=313233343536373839' in response
    assert serial.tx==[(command+'\r\n').encode(),b'LOGFILE POLL 11\r\n']
    assert list(tmp_path.iterdir())==[]


def test_manual_read_does_not_enter_when_device_rejects():
    command='LOGFILE READ 1 1-CBF43926-00000009 0'
    transport,serial=wire({command:[b'ERR LOGFILE READ code=NOT_READY\r\n']})
    response,error=_Console_Execute(transport,command,Event())
    assert response=='ERR LOGFILE READ code=NOT_READY' and 'NOT_READY' in error
    assert serial.tx==[(command+'\r\n').encode()]


def test_queue_claim_spans_dequeue_to_execution_and_cancel():
    owner=MaintenanceOwner('MOCK',230400);owner.connected.set()
    assert owner.submit_command('GNSS 0 STATUS')
    request=owner.jobs.get_nowait();assert request.text=='GNSS 0 STATUS'
    assert not owner.submit(None,list_only=True) and not owner.submit_command('SYSTEM STATUS')
    owner.request_cancel();assert owner.job_cancel.is_set()
    owner.jobs.task_done();owner._Claim_Release()
    assert owner.submit(None,list_only=True)
    owner.request_stop();assert not owner.submit_command('SYSTEM STATUS')


def test_incomplete_command_closes_owner_without_reusing_old_connection(qtbot):
    class Wire(MockTransport):
        requires_reconnect=False
        def exchange(self,command,timeout,cancel):
            if command=='CAL STATUS':
                self.commands.append(command);self.requires_reconnect=True
                raise TimeoutError('incomplete command')
            return super().exchange(command,timeout,cancel)
    transport=Wire();owner=MaintenanceOwner('MOCK',230400,transport_factory=lambda *_:transport)
    results=[];connections=[]
    def connection(connected,detail):
        connections.append(connected)
        if connected:assert owner.submit_command('CAL STATUS')
    owner.connection_changed.connect(connection,Qt.DirectConnection)
    owner.command_result.connect(lambda *result:results.append(result),Qt.DirectConnection)
    owner.start()
    try:qtbot.waitUntil(lambda:not owner.isRunning(),timeout=3000)
    finally:
        owner.request_stop();assert owner.wait(3000)
    assert transport.closed and connections==[True,False]
    assert len(results)==1 and 'incomplete command' in results[0][2]
    assert not owner.connected.is_set() and not owner.submit_command('SYSTEM STATUS')
    assert transport.commands==['LOGFILE CAPS','CAL STATUS']


@pytest.mark.parametrize('text',['   ','SYSTEM START','SYSTEM START 1','CAL RESET','OUTPUT ARM','LOGFILE DELETE 1','SYSTEM STATUS\x00','SYSTEM STATUS\nCAL RESET'])
def test_raw_control_and_multiline_remain_unavailable(text):
    with pytest.raises(ValueError):ConsoleCommand_Validate(text,allow_raw=True)


def test_guided_console_uses_instance_grammar_and_retains_manual_text(qtbot,tmp_path):
    panel=MaintenanceConsole(I18n(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)))
    qtbot.addWidget(panel);panel.set_connection(True)
    panel.category.setCurrentIndex(panel.category.findData('GNSS'))
    panel.choice.setCurrentIndex(panel.choice.findData('GNSS NAV SAT'))
    panel.instance.setText('2');assert panel.raw.text()=='GNSS 2 NAV SAT' and panel.send.isEnabled()
    panel.instance.setText('');assert not panel.send.isEnabled()
    panel.raw.setText('UNKNOWN INSPECT');assert panel.send.isEnabled()
    panel.set_runtime_capabilities(dict(file_service_version='1',supported='1'))
    assert panel.raw.text()=='UNKNOWN INSPECT'
    panel.category.setCurrentIndex(panel.category.findData('LOGFILE'))
    panel.choice.setCurrentIndex(panel.choice.findData('LOGFILE READ'))
    assert not panel.send.isEnabled()
    panel.parameters.setText('1 1-CBF43926-00000009 0')
    assert panel.raw.text()=='LOGFILE READ 1 1-CBF43926-00000009 0' and panel.send.isEnabled()
    panel.set_connection(False);assert not panel.send.isEnabled()
    assert panel.choice.findData('LOGFILE READ')<0


def test_descriptor_format_does_not_invent_protocol_capability(qtbot,tmp_path):
    panel=MaintenanceConsole(I18n(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)));qtbot.addWidget(panel)
    panel.set_protocol_declaration({'version':1});assert '未声明' in panel.protocol_status.text()
    panel.set_protocol_declaration({'maintenance':{'profile':'maintenance.serial.0_1'}})
    assert '声明 0.1' in panel.protocol_status.text()
    panel.set_runtime_capabilities({'legacy_response':True})
    assert '版本待确认' in panel.protocol_status.text() and '声明与能力不同' not in panel.protocol_status.text()
    panel.set_runtime_capabilities({'legacy_response':True,'maintenance':'0.0'})
    assert '声明与能力不同' in panel.protocol_status.text()
    assert all(not row.file_v1 for row in panel._catalog)
    panel.set_protocol_declaration({'maintenance':{'profile':'maintenance.serial.0_0'}})
    panel.set_runtime_capabilities({'maintenance':'0.1','compatible':'0.0'})
    assert '声明与能力不同' not in panel.protocol_status.text()
