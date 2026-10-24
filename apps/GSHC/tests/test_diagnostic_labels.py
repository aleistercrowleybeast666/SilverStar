from types import SimpleNamespace
import pytest
from ui.diagnostic_labels import DiagnosticValue_Format,DiagnosticReason_Format,WatchValue_Format
from services.maintenance_commands import ConsoleCommand_Validate,ConsoleCommand_ResponsePrefix

ZH=SimpleNamespace(language='zh_CN')
EN=SimpleNamespace(language='en_US')


def test_all_blockers_and_unknown_bits_are_retained_without_start_authorization():
    text=DiagnosticValue_Format('task.preparation','start_blocking_mask',0x80000180,ZH)
    assert '校准尚未就绪' in text and '对准尚未就绪' in text
    assert '未知位 0x80000000' in text and '(0x80000180)' in text
    assert '允许START' not in text
    assert 'START授权' in DiagnosticValue_Format('task.preparation','ready',1,ZH)


def test_startup_warning_bits_are_device_order_not_capability_order():
    # SystemStartup_ReportFinalize: 1 << SystemStartupDeviceId; bit0 is output.
    assert '输出' in DiagnosticValue_Format('task.preparation','warning_mask',1,ZH)
    assert 'GNSS' in DiagnosticValue_Format('task.preparation','warning_mask',4,ZH)


@pytest.mark.parametrize('raw,label',[(0,'空闲'),(1,'等待放置'),(2,'采样'),(3,'检查'),(4,'就绪'),(5,'失败')])
def test_calibration_enum_has_meaning_and_raw_value(raw,label):
    text=WatchValue_Format('System/Calibration/Src/system_calibration.c::s_status.state',raw,ZH)
    assert label in text and f'({raw})' in text


def test_unknown_values_and_unrecognized_symbols_are_not_invented():
    assert '未知码 (255)' == DiagnosticValue_Format('calibration','state',255,ZH)
    assert '未知码 (2)' == DiagnosticValue_Format('thread.logger','log_fault',2,ZH)
    assert WatchValue_Format('other.c::s_status.state',1,ZH)=='1'
    assert DiagnosticReason_Format('new_reason_57',ZH)=='new_reason_57'
    assert '具体原因未提供' in DiagnosticReason_Format('io_fault',ZH)
    assert 'Finalized (3)' == DiagnosticValue_Format('thread.logger','finalization',3,EN)


@pytest.mark.parametrize('command',['SYSTEM STATUS','SYSTEM DIAG 16','CAL DETAIL','SYSTEM START RESULT','SYSTEM STARTUP GNSS','LOGFILE STATUS'])
def test_reviewed_queries(command):
    assert ConsoleCommand_Validate(command.lower())==command
    assert ConsoleCommand_ResponsePrefix(command)==('SYSTEM DIAG' if command.startswith('SYSTEM DIAG') else command)


@pytest.mark.parametrize('command',['SYSTEM START','CAL START SIX_FACE','CAL RESET','LOGFILE ENTER','LOGFILE DELETE 1','SYSTEM CONSOLE IO CLEAR','SYSTEM DIAG 17','SYSTEM DIAG -1','SYSTEM STATUS\nCAL RESET','UNKNOWN'])
def test_control_unknown_and_out_of_range_commands_cannot_enter_queue(command):
    with pytest.raises(ValueError):ConsoleCommand_Validate(command)


def test_actual_transport_matches_cal_response_without_opening_serial():
    from threading import Event
    from transport.file_service_backend import FileServiceSerialTransport
    sent=[];chunks=[b'EVENT CAL DIAG reason=NO_STREAM\r\nOK CAL STATUS state=WAIT_FACE ready=0\r\n']
    def write(data):sent.append(data);return len(data)
    transport=FileServiceSerialTransport.__new__(FileServiceSerialTransport)
    transport._serial=SimpleNamespace(write=write,read=lambda _:chunks.pop(0) if chunks else b'')
    transport._buffer=bytearray();transport._synchronize=lambda _:None
    assert transport.exchange('CAL STATUS',.1,Event())=='OK CAL STATUS state=WAIT_FACE ready=0'
    assert sent==[b'CAL STATUS\r\n']


def test_console_cause_is_only_translated_from_actual_known_fields():
    from ui.diagnostic_labels import ConsoleResponse_Summary
    text=ConsoleResponse_Summary('CAL STATUS','OK CAL STATUS state=WAIT_FACE ready=0',ZH)
    assert '等待放置校准面 (WAIT_FACE)' in text and '未准备就绪 (0)' in text
    assert ConsoleResponse_Summary('CAL STATUS','ERR CAL STATUS code=UNKNOWN',ZH)==''
