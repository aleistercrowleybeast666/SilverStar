"""Direct worker tests: no QApplication/window/thread or native hardware starts."""
from PySide6.QtCore import Qt
import pytest
import ui.file_transfer as module
from services.file_service_client import FileServiceError,FileServiceResult

@pytest.mark.parametrize('result,legacy_expected,label',[
    (FileServiceResult.BAD_RESPONSE,False,'unavailable'),
    (FileServiceResult.BUSY,False,'unavailable'),
    (FileServiceResult.UNSUPPORTED,True,'unsupported'),
])
def test_only_genuine_unsupported_uses_legacy_fallback(monkeypatch,result,legacy_expected,label):
    calls=[];messages=[]
    class Wire:
        def close(self):calls.append('closed')
    class Client:
        def __init__(self,*a,**k):pass
        def negotiate(self):raise FileServiceError(result,'fixture')
    class Legacy:
        def __init__(self,*a,**k):calls.append('legacy')
    monkeypatch.setattr(module,'FileServiceClient',Client)
    monkeypatch.setattr(module,'LegacyFirmwareStatusClient',Legacy)
    monkeypatch.setattr(module,'RuntimeDiagnosticsClient',lambda *a:None)
    owner=module.MaintenanceOwner('OFFLINE',230400,transport_factory=lambda *_:Wire())
    def receive(available,detail):
        messages.append((available,detail));owner.request_stop()
    owner.service_status.connect(receive,Qt.DirectConnection)
    owner.run()
    assert ('legacy' in calls)==legacy_expected and calls[-1]=='closed'
    assert len(messages)==1 and messages[0][0] is False and label in messages[0][1]

def test_success_message_discloses_quarantined_probe(monkeypatch):
    messages=[];closed=[]
    class Wire:
        startup_diagnostics={'performed':True,'quarantined_bytes':197,'authoritative':False,'raw_hex':'00'}
        def close(self):closed.append(True)
    class Client:
        def __init__(self,*a,**k):pass
        def negotiate(self):return dict(maintenance_required='1',status_version='1')
    monkeypatch.setattr(module,'FileServiceClient',Client)
    monkeypatch.setattr(module,'RuntimeDiagnosticsClient',lambda *a:None)
    owner=module.MaintenanceOwner('OFFLINE',230400,transport_factory=lambda *_:Wire())
    def receive(available,detail):messages.append((available,detail));owner.request_stop()
    owner.service_status.connect(receive,Qt.DirectConnection);owner.run()
    assert closed==[True] and len(messages)==1 and messages[0][0] is True
    assert '197 B' in messages[0][1] and 'fresh CAPS accepted' in messages[0][1]
