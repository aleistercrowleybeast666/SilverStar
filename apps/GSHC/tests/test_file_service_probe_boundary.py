"""Model the observed latent packet: idle reads cannot expose it; target TX can."""
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import pytest
import transport.file_service_backend as backend
from services.device_export import ExportCancelled
from services.file_service_client import FileServiceClient, FileServiceError, FileServiceResult
from services.maintenance_api import MaintenanceRequest, Maintenance_Execute

TASK=Path(__file__).resolve().parent
ROWS=json.loads((TASK/'fixtures/maintenance_probe_r03.json').read_text())['responses']
INFO=(ROWS[0]['response']+'\r\n').encode();CAP=(ROWS[1]['response']+'\r\n').encode()
STATUS=(ROWS[2]['response']+'\r\n').encode()

class Clock:
    value=0.0
    def monotonic(self):return self.value

class Bridge:
    def __init__(self,clock,*,latent=b'',caps=CAP,probe=INFO,flood=False,step=.05,cancel=None,io_error=False,short=False):
        self.clock=clock;self.latent=latent;self.caps=caps;self.probe=probe;self.flood=flood
        self.step=step;self.cancel=cancel;self.io_error=io_error;self.short=short
        self.rx=bytearray();self.tx=[];self.closed=False;self.purges=0
    def write(self,payload):
        self.tx.append(bytes(payload))
        command=bytes(payload).decode().strip()
        response=self.probe if command=='SYSTEM INFO' else STATUS if command=='LOGFILE STATUS' else self.caps
        if self.latent:
            response=self.latent+response[:64]+response[120:];self.latent=b''
        self.rx.extend(response)
        return len(payload)-int(self.short)
    def read(self,size):
        self.clock.value+=self.step
        if self.io_error:raise OSError('Simulated unplug')
        if self.cancel is not None:self.cancel.set()
        if self.flood:return b'X'*min(128,size)
        data=bytes(self.rx[:size]);del self.rx[:size];return data
    def close(self):self.closed=True
    def reset_input_buffer(self):self.purges+=1

def create(monkeypatch,**kwargs):
    clock=Clock();bridge=Bridge(clock,**kwargs)
    monkeypatch.setattr(backend,'time',SimpleNamespace(monotonic=clock.monotonic))
    transport=backend.FileServiceSerialTransport('OFFLINE',230400,serial_factory=lambda **_:bridge)
    return clock,bridge,transport

@pytest.mark.parametrize('latent',[CAP[:64],b'LOG INFO SYSTEM '+b'X'*48,b'Horco CMSIS-DAP V2\r\n'+b'X'*44,b'\xff'*64])
def test_latent_corrupt_probe_is_quarantined_then_fresh_caps_are_required(monkeypatch,latent):
    clock,wire,transport=create(monkeypatch,latent=latent)
    client=FileServiceClient(transport);caps=client.negotiate()
    assert caps['source_commit']=='67cc0263cc089584abb4f40028a9d3918dd7203e'
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']
    assert transport.startup_diagnostics==dict(performed=True,authoritative=False,
        quarantined_bytes=len(latent)+len(INFO)-56,raw_hex=(latent+INFO[:64]+INFO[120:]).hex())
    assert wire.purges==0

def test_clean_probe_is_also_non_authoritative_and_recorded(monkeypatch):
    clock,wire,transport=create(monkeypatch)
    FileServiceClient(transport).negotiate()
    assert transport.startup_diagnostics['authoritative'] is False
    assert transport.startup_diagnostics['raw_hex']==INFO.hex()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']

def test_subsequent_exchange_has_no_probe_or_retry(monkeypatch):
    clock,wire,transport=create(monkeypatch)
    client=FileServiceClient(transport);client.negotiate();client.negotiate()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n',b'LOGFILE CAPS\r\n']

def test_prepare_job_reestablishes_boundary_before_new_caps(monkeypatch):
    clock,wire,transport=create(monkeypatch)
    client=FileServiceClient(transport);client.negotiate()
    wire.latent=CAP[:64];transport.prepare_job();client.negotiate()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']*2
    assert wire.purges==0

@pytest.mark.parametrize('bad',[CAP[:64]+CAP[120:],CAP[:64]+CAP[:64]+CAP[120:],CAP.replace(b'device_id=unknown ',b''),CAP.replace(b'boot_id=unknown ',b'')])
def test_authoritative_caps_corruption_still_fails_without_retry_or_enter(monkeypatch,bad):
    clock,wire,transport=create(monkeypatch,caps=bad,latent=CAP[:64])
    with pytest.raises(FileServiceError) as caught:FileServiceClient(transport).negotiate()
    assert caught.value.result==FileServiceResult.BAD_RESPONSE
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']

@pytest.mark.parametrize('bad',[b'OK LOGFILE CAPS file_service_version=2\r\n',b'OK LOGFILE CAPS supported=0\r\n'])
def test_unsupported_capabilities_remain_unsupported(monkeypatch,bad):
    clock,wire,transport=create(monkeypatch,caps=bad)
    with pytest.raises(FileServiceError) as caught:FileServiceClient(transport).negotiate()
    assert caught.value.result==FileServiceResult.UNSUPPORTED
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']

def test_cancel_before_open_boundary_sends_nothing(monkeypatch):
    clock,wire,transport=create(monkeypatch);cancel=Event();cancel.set()
    with pytest.raises(ExportCancelled):transport.exchange('LOGFILE CAPS',2,cancel)
    assert wire.tx==[]

def test_cancel_during_probe_sends_no_service_request(monkeypatch):
    cancel=Event();clock,wire,transport=create(monkeypatch,cancel=cancel)
    with pytest.raises(ExportCancelled):transport.exchange('LOGFILE CAPS',2,cancel)
    assert wire.tx==[b'SYSTEM INFO\r\n']

@pytest.mark.parametrize('probe',[b'',b'LOG INFO no complete probe\r\n',b'OK LOGFILE CAPS supported=1\r\n',b'OK SYSTEM INFO incomplete_without_newline'])
def test_unfinished_or_wrong_probe_stops_without_authoritative_query(monkeypatch,probe):
    clock,wire,transport=create(monkeypatch,probe=probe)
    with pytest.raises(TimeoutError):transport.exchange('LOGFILE CAPS',2,Event())
    expected=[b'SYSTEM INFO\r\n']*(2 if not probe else 1)
    assert wire.tx==expected and clock.value<=2.06
    with pytest.raises(OSError,match='reconnect'):transport.exchange('LOGFILE CAPS',2,Event())
    assert wire.tx==expected


def test_first_probe_dropped_retries_only_probe_at_same_baud_with_original_deadline(monkeypatch):
    clock,wire,transport=create(monkeypatch,probe=b'')
    original=wire.write
    def write(payload):
        if wire.tx:
            wire.probe=INFO
        return original(payload)
    wire.write=write
    FileServiceClient(transport).negotiate()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']
    assert 1.0<=clock.value<2.0 and transport.baudrate==230400
    assert wire.purges==0 and not transport.requires_reconnect
    assert transport.startup_diagnostics['probe_attempts']==2
    assert transport.startup_diagnostics['authoritative'] is False


def test_late_duplicate_probe_is_quarantined_before_fresh_caps(monkeypatch):
    clock,wire,transport=create(monkeypatch,probe=b'')
    original=wire.write
    def write(payload):
        if wire.tx:
            wire.probe=INFO+INFO
        return original(payload)
    wire.write=write
    FileServiceClient(transport).negotiate()
    assert transport.startup_diagnostics['raw_hex']==(INFO+INFO).hex()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']


@pytest.mark.parametrize('padding',[b'\r\n',b'\r',b'\n\r\n'])
def test_delimiter_only_opening_retries_once_after_quiet_and_requires_new_caps(monkeypatch,padding):
    clock,wire,transport=create(monkeypatch,probe=padding)
    original=wire.write
    def write(payload):
        if wire.tx:wire.probe=INFO+INFO
        return original(payload)
    wire.write=write
    FileServiceClient(transport).negotiate()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n']
    assert 1.0<=clock.value<2.0 and wire.purges==0
    assert transport.startup_diagnostics['raw_hex']==(padding+INFO+INFO).hex()


@pytest.mark.parametrize('partial',[b'\r\nOK S',b'\r\n\x00',b'\r\n '])
def test_any_non_delimiter_payload_is_not_treated_as_an_empty_probe(monkeypatch,partial):
    clock,wire,transport=create(monkeypatch,probe=partial)
    with pytest.raises(TimeoutError):transport.exchange('LOGFILE CAPS',2,Event())
    assert wire.tx==[b'SYSTEM INFO\r\n'] and clock.value<=2.06


def test_delimiter_only_exhaustion_keeps_deadline_and_reconnect_gate(monkeypatch):
    clock,wire,transport=create(monkeypatch,probe=b'\r\n')
    with pytest.raises(TimeoutError,match='no_response_payload'):
        transport.exchange('LOGFILE CAPS',2,Event())
    assert wire.tx==[b'SYSTEM INFO\r\n']*2 and clock.value<=2.06
    assert transport.requires_reconnect

def test_fast_flood_has_byte_bound(monkeypatch):
    clock,wire,transport=create(monkeypatch,flood=True,step=.001)
    with pytest.raises(OSError,match='bound'):transport.exchange('LOGFILE CAPS',2,Event())
    assert wire.tx==[b'SYSTEM INFO\r\n'] and transport.startup_diagnostics['quarantined_bytes']==4224
    assert len(transport.startup_diagnostics['raw_hex'])==8192

def test_continuous_flood_has_time_bound(monkeypatch):
    clock,wire,transport=create(monkeypatch,flood=True,step=.1)
    with pytest.raises(TimeoutError):transport.exchange('LOGFILE CAPS',2,Event())
    assert wire.tx==[b'SYSTEM INFO\r\n'] and clock.value<=2.06

def test_disconnect_and_short_write_stop_without_service_request(monkeypatch):
    for kwargs in (dict(io_error=True),dict(short=True)):
        clock,wire,transport=create(monkeypatch,**kwargs)
        with pytest.raises(OSError):transport.exchange('LOGFILE CAPS',2,Event())
        assert wire.tx==[b'SYSTEM INFO\r\n']

def test_invalid_command_does_not_even_send_probe(monkeypatch):
    clock,wire,transport=create(monkeypatch)
    with pytest.raises(ValueError):transport.exchange('LOGFILE CAPS\nSTART',2,Event())
    assert wire.tx==[]

def test_shared_api_preserves_raw_probe_diagnostics_and_release(monkeypatch):
    clock,wire,transport=create(monkeypatch,latent=CAP[:64])
    result=Maintenance_Execute(MaintenanceRequest('status','OFFLINE'),_transport_factory=lambda *_:transport)
    assert result['result']=='ok' and result['release']=='closed' and wire.closed
    assert result['link_synchronization']['authoritative'] is False
    assert result['link_synchronization']['raw_hex']==(CAP[:64]+INFO[:64]+INFO[120:]).hex()
    assert wire.tx==[b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n',b'LOGFILE STATUS\r\n']
