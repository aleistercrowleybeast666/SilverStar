"""Qt integration with synthetic targets; no hardware access."""
from threading import Event
import time
from unittest.mock import patch
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
from transport.swd_session import SwdSession, SwdReply, SwdResult as R
from ui.swd_connection import SwdConnectionManager
from test_probe_ui import panel
from test_swd_session import FakeMemory, PROBE


def wait_for(predicate):
    deadline=time.monotonic()+4
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents()
        time.sleep(.01)  # Allow real file/pipe I/O workers to reacquire the GIL.
    assert predicate()


@pytest.fixture
def swd_panel(panel):
    window, create = panel
    probes = create(lambda _:ProbeInventory(ProbeInventoryResult.Ready,(PROBE,)))
    wait_for(lambda:probes.worker is None and bool(probes.selection.identity))
    controller=probes.parent(); controller.probes=probes
    managers=[]
    def manager(factory):
        result=SwdConnectionManager(controller,factory)
        managers.append(result)
        window.on_close_requested=lambda: all([result.request_close(),probes.request_close()])
        return result
    yield window,probes,manager
    for result in managers:
        result.shutdown()
        wait_for(lambda:result.worker is None)


@pytest.mark.parametrize('language',['zh_CN','en_US'])
def test_explicit_attach_state_and_detach_keep_serial_independent(swd_panel,language):
    window,probes,create=swd_panel
    backends=[]
    def factory(**kwargs):
        backend=FakeMemory(kwargs['cancel']); backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory)
    page=window.maintenance_page
    window.i18n.set_language(language);window.retranslate_ui()
    assert not backends and page.btn_swd_attach.isEnabled()
    port=window.debug_port_combo.currentText(); serial_state=window.debug_status.text()
    page.btn_swd_attach.click()
    wait_for(lambda:manager.snapshot is not None)
    assert window.i18n.tr('swd.running') in page.swd_target_status.text()
    assert window.i18n.tr('swd.unmatched') in page.swd_target_status.text()
    assert window.i18n.tr('swd.non_atomic') in page.swd_target_status.text()
    assert not window.probe_combo.isEnabled() and not window.btn_probe_refresh.isEnabled()
    assert not probes.refresh() and not manager.attach()
    assert window.debug_status.text()==serial_state and window.debug_port_combo.currentText()==port
    page.btn_swd_detach.click()
    wait_for(lambda:manager.worker is None)
    assert manager.snapshot is None and manager.status=='swd.detached'
    assert backends[0].closed==1 and page.btn_swd_attach.isEnabled()
    assert window.probe_combo.isEnabled() and not page.btn_swd_detach.isEnabled()
    label=window.probe_status
    assert label.height()>=label.heightForWidth(label.width())


@pytest.mark.parametrize('result',[R.SafetyNotProven,R.Busy,R.MissingDependency,R.TargetMismatch,R.TransportError])
def test_failed_attach_never_displays_connected(swd_panel,result):
    window,probes,create=swd_panel
    class Refused:
        def __init__(self,**kwargs): self.closed=0
        def Swd_Attach(self,_): return SwdReply(result,'injected refusal')
        def Swd_Detach(self): self.closed+=1;return SwdReply(R.Ok)
    manager=create(Refused)
    assert manager.attach()
    wait_for(lambda:manager.worker is None)
    assert manager.status=='swd.'+result.value and manager.snapshot is None
    assert 'injected refusal' in window.maintenance_page.swd_target_status.text()
    assert not probes.target_active and window.maintenance_page.btn_swd_attach.isEnabled()


def test_close_during_attach_cancels_and_ignores_late_success(swd_panel):
    window,probes,create=swd_panel
    entered=Event();released=Event()
    class Delayed:
        def __init__(self,**kwargs): self.cancel=kwargs['cancel']
        def Swd_Attach(self,_):
            entered.set(); self.cancel.wait(3)
            return SwdReply(R.Ok)  # Deliberately late success, never restore target.
        def Swd_Detach(self): released.set();return SwdReply(R.Ok)
    manager=create(Delayed)
    manager.attach();wait_for(entered.is_set)
    window.close()
    wait_for(lambda:manager.worker is None and not window.isVisible())
    assert released.is_set() and manager.snapshot is None and manager.status=='swd.detached'
    assert not manager.attach()


def test_release_failure_is_retained_and_blocks_reconnect(swd_panel):
    window,probes,create=swd_panel
    class FailedRelease:
        def __init__(self,**_):pass
        def Swd_Attach(self,_):return SwdReply(R.TransportError,'read failed')
        def Swd_Detach(self):return SwdReply(R.ReleaseFailed,'release failed')
    manager=create(FailedRelease)
    manager.attach();wait_for(lambda:manager.worker is None)
    assert manager.status=='swd.release_failed' and manager._failed_owner
    assert probes.target_active and not manager.attach()
    assert not window.maintenance_page.btn_swd_attach.isEnabled()
    manager.request_close()
    assert manager.status=='swd.release_failed'


def test_legacy_admission_path_in_worker_is_bounded_and_opens_no_device(swd_panel,tmp_path):
    window,probes,create=swd_panel
    executable=tmp_path/'unapproved-openocd.exe'
    executable.write_bytes(b'not executable\0'*330000)
    from transport._swd_openocd import OpenOcdMemAp
    manager=create(lambda **kwargs: SwdSession(**kwargs, _backend_factory=OpenOcdMemAp))
    with patch('transport._swd_openocd.shutil.which',return_value=str(executable)),patch('subprocess.Popen') as popen:
        manager.attach();wait_for(lambda:manager.worker is None)
        assert manager.status=='swd.safety_not_proven'
        popen.assert_not_called()
        label=window.probe_status
        assert label.height()>=label.heightForWidth(label.width())


def test_default_pyocd_missing_dependency_in_worker_opens_no_device(swd_panel, tmp_path, monkeypatch):
    window, probes, create = swd_panel
    monkeypatch.setenv('SILVERSTAR_SWD_PYOCD_PATH', str(tmp_path))
    manager = create(SwdSession)
    manager.attach()
    wait_for(lambda: manager.worker is None)
    assert manager.status == 'swd.missing_dependency' and manager.snapshot is None
    assert not probes.target_active and window.maintenance_page.btn_swd_attach.isEnabled()
