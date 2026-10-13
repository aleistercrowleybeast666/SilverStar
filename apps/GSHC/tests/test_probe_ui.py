"""Real Qt widgets with synthetic inventories; no probe or serial interface opens."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch
import pytest
from PySide6.QtCore import QObject, QPoint, QRect, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from ui.main_window import MainWindow
from ui.probe_selection import ProbeSelectionManager
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult as Result
from test_probe_inventory import parsed, nodes


def wait_for(predicate):
    deadline = time.monotonic()+4
    while not predicate() and time.monotonic()<deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def panel(tmp_path):
    application = QApplication.instance() or QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.is_file(): QFontDatabase.addApplicationFont(str(font))
    application.setFont(QFont('Microsoft YaHei',10))
    window = MainWindow(I18n(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)))
    window.render_timer.stop(); window.gl_view.hide()
    controller = QObject(window); controller.window = window
    managers=[]
    def create(enumerator):
        manager=ProbeSelectionManager(controller,enumerator)
        managers.append(manager)
        window.on_close_requested=manager.request_close
        return manager
    window.resize(1280,800); window.show(); application.processEvents()
    yield window,create
    for manager in managers:
        manager.shutdown()
        wait_for(lambda: manager.worker is None)
    window.close(); window.deleteLater(); application.processEvents()


def test_single_probe_auto_select_has_no_connection_side_effect(panel):
    window,create=panel
    window.set_ports(['COM9','COM100'])
    window.port_combo.setCurrentText('COM100')
    window.debug_port_combo.setCurrentText('COM9')
    with patch('transport.serial_backend.serial.Serial') as serial_open:
        manager=create(lambda _: parsed(nodes('A')))
        wait_for(lambda: manager.worker is None and manager.selection.identity!='')
        assert window.probe_combo.currentData().endswith('\\A')
        assert window.probe_status.text()==window.i18n.tr('probe.selected')
        assert window.i18n.tr('probe.boundary') in window.maintenance_page.swd_status.text()
        assert window.port_combo.currentText()=='COM100' and window.debug_port_combo.currentText()=='COM9'
        serial_open.assert_not_called()


def test_multiple_choice_reorder_removal_and_replug(panel):
    window,create=panel
    current=[parsed(nodes('A')+nodes('B'))]
    manager=create(lambda _:current[0])
    wait_for(lambda: manager.worker is None and len(manager.selection.probes)==2)
    assert window.probe_combo.currentData()==''
    chosen=manager.selection.probes[1].identity
    window.probe_combo.setCurrentIndex(window.probe_combo.findData(chosen))
    current[0]=parsed(list(reversed(nodes('A')+nodes('B'))))
    manager.refresh(); wait_for(lambda:manager.worker is None)
    assert window.probe_combo.currentData()==chosen
    current[0]=parsed(nodes('A'))
    manager.refresh(); wait_for(lambda:manager.worker is None)
    assert window.probe_combo.currentData()=='' and manager.status=='probe.removed'
    current[0]=parsed(nodes('B'))
    manager.refresh(); wait_for(lambda:manager.worker is None)
    assert window.probe_combo.currentData()==''


@pytest.mark.parametrize('result', [Result.Empty,Result.Failed,Result.MissingDependency])
def test_failures_are_distinct_and_retry_succeeds(panel,result):
    window,create=panel
    current=[ProbeInventory(result,detail='test host result')]
    manager=create(lambda _:current[0])
    wait_for(lambda:manager.worker is None and manager.status=='probe.'+result.value)
    assert window.btn_probe_refresh.isEnabled() and not window.probe_combo.isEnabled()
    current[0]=parsed(nodes('A'))
    window.btn_probe_refresh.click()
    wait_for(lambda:manager.worker is None and bool(manager.selection.identity))
    assert manager.status=='probe.selected'


def test_repeated_refresh_and_close_during_late_completion(panel):
    window,create=panel
    entered=Event(); cancelled=Event(); calls=[]
    def delayed(cancel):
        calls.append(1); entered.set()
        cancel.wait(3); cancelled.set()
        return parsed(nodes('LATE'))  # A late success must never restore selection.
    manager=create(delayed)
    wait_for(entered.is_set)
    assert manager.status=='probe.busy' and not window.btn_probe_refresh.isEnabled()
    for _ in range(20):
        assert not manager.refresh()
        window.btn_probe_refresh.click()
    assert len(calls)==1
    window.close()
    wait_for(lambda:manager.worker is None)
    assert cancelled.is_set() and manager.selection.identity==''
    assert manager.status=='probe.cancelled' and not window.isVisible()
    assert not manager.refresh()


@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('width',[1024,1280,1920])
def test_header_wraps_without_clipping_or_overlap(panel,language,width):
    window,create=panel
    manager=create(lambda _:parsed(nodes('A')))
    wait_for(lambda:manager.worker is None and bool(manager.selection.identity))
    window.i18n.set_language(language); window.retranslate_ui()
    window.resize(width,800); QTest.qWait(30)
    assert window.width()==width  # A former wide row must not pin minimum width.
    rect=lambda w: QRect(w.mapTo(window,QPoint()),w.size())
    bar=rect(window.header_bar)
    groups=[rect(w) for w in (window.header_connection_group,window.debug_connection_group,window.probe_group)]
    for group in groups: assert bar.contains(group)
    for i,one in enumerate(groups):
        for two in groups[i+1:]: assert not one.intersects(two)
    assert groups[0].left()-bar.left()<=16
    assert 0<=bar.right()-rect(window.btn_probe_refresh).right()<=20
    for control in (window.probe_title,window.probe_combo,window.btn_probe_refresh,window.probe_status):
        assert groups[2].contains(rect(control))
    assert window.probe_combo.currentData().endswith('\\A')
