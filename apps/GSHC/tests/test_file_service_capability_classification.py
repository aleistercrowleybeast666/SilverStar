"""Narrow mandatory-CAPS classification regression, all transports synthetic."""
import pytest
from services.file_service_client import FileServiceClient,FileServiceError,FileServiceResult
from services.maintenance_api import MaintenanceRequest,Maintenance_Execute

BASE='OK LOGFILE CAPS file_service_version=1 supported=1 max_chunk=64 telemetry_bulk=0 device_id=unknown boot_id=unknown'
class Wire:
    def __init__(self,reply):self.reply=reply;self.commands=[];self.closed=False
    def exchange(self,command,*args):self.commands.append(command);return self.reply
    def close(self):self.closed=True

@pytest.mark.parametrize('key',['file_service_version','supported','max_chunk','telemetry_bulk','device_id','boot_id'])
def test_incomplete_v1_is_bad_response_and_never_publishes_capabilities(key):
    line=' '.join(x for x in BASE.split() if not x.startswith(key+'='))
    wire=Wire(line);client=FileServiceClient(wire)
    with pytest.raises(FileServiceError) as error:client.negotiate()
    assert error.value.result==FileServiceResult.BAD_RESPONSE
    assert client.capabilities is None and wire.commands==['LOGFILE CAPS']

@pytest.mark.parametrize('reply',[
    'OK LOGFILE CAPS file_service_version=2',
    'OK LOGFILE CAPS file_service_version=2 supported=1',
    'OK LOGFILE CAPS file_service_version=1 supported=0',
    BASE.replace('max_chunk=64','max_chunk=128'),
    BASE.replace('telemetry_bulk=0','telemetry_bulk=1'),
    'ERR LOGFILE CAPS request_id=0 code=UNSUPPORTED',
])
def test_real_unsupported_version_or_capability_remains_unsupported(reply):
    wire=Wire(reply)
    with pytest.raises(FileServiceError) as error:FileServiceClient(wire).negotiate()
    assert error.value.result==FileServiceResult.UNSUPPORTED

def test_shared_api_bad_response_releases_owner_without_enter_or_cancel():
    wire=Wire(BASE.replace('device_id=unknown ',''))
    result=Maintenance_Execute(MaintenanceRequest('list','OFFLINE_ONLY',enter_maintenance=True),_transport_factory=lambda *_:wire)
    assert result['result']=='bad_response' and result['release']=='closed'
    assert not result['maintenance_enter_attempted'] and result['capabilities'] is None and result['output']==''
    assert wire.commands==['LOGFILE CAPS']

def test_unknown_optional_fields_preserve_supported_v1():
    assert FileServiceClient(Wire(BASE+' future_option=kept')).negotiate()['future_option']=='kept'
