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
        assert window.i18n.tr('probe.boundary') in window.probe_status.toolTip()
        assert window.port_combo.currentText()=='COM100' and window.debug_port_combo.currentText()=='COM9'
        serial_open.assert_not_called()


def test_multiple_choice_reorder_removal_and_replug(panel):
    window,create=panel
    current=[parsed(nodes('A')+nodes('B'))]
    manager=create(lambda _:current[0])
    wait_for(lambda: manager.worker is None and len(manager.selection.probes)==2)
    assert window.probe_combo.currentData()==''
    assert manager.status=='probe.available'
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


@pytest.mark.parametrize('language',['zh_CN','en_US'])
def test_probe_labels_distinguish_discovery_selection_and_empty_after_rescan(panel,language):
    window,create=panel
    window.i18n.set_language(language); window.retranslate_ui()
    assert window.probe_status.text()==window.i18n.tr('probe.not_scanned')
    current=[parsed(nodes('A'))]
    manager=create(lambda _:current[0])
    wait_for(lambda:manager.worker is None and bool(manager.selection.identity))
    assert window.probe_status.text()==window.i18n.tr('probe.selected')
    assert window.i18n.tr('probe.boundary') in window.probe_status.toolTip()
    assert window.i18n.tr('maintenance.firmware_source') in window.maintenance_page.firmware_summary.text()
    assert window.i18n.tr('maintenance.firmware_not_received') in window.maintenance_page.firmware_summary.text()
    window.probe_combo.setCurrentIndex(0)
    assert manager.status=='probe.available'
    assert window.probe_status.text()==window.i18n.tr('probe.available')
    manager.refresh(); assert manager.status=='probe.busy'
    wait_for(lambda:manager.worker is None)
    assert manager.status=='probe.available' and window.probe_combo.currentData()==''
    window.probe_combo.setCurrentIndex(1)
    current[0]=parsed([])
    manager.refresh(); wait_for(lambda:manager.worker is None)
    assert manager.status=='probe.empty' and window.probe_combo.currentData()==''
    assert window.probe_status.text()==window.i18n.tr('probe.empty')
    assert window.probe_status.text()!=window.i18n.tr('probe.available')
    assert not window.probe_combo.isEnabled()
    current[0]=parsed(nodes('A'))
    manager.refresh(); wait_for(lambda:manager.worker is None)
    assert manager.status=='probe.available'  # Reappearance is not a target reconnect.


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


def test_startup_once_page_changes_no_polling_and_manual_refresh(panel):
    window, create = panel
    calls = []
    manager = create(lambda _: calls.append(1) or parsed(nodes('A')+nodes('B')))
    wait_for(lambda: manager.worker is None and len(manager.selection.probes) == 2)
    chosen = manager.selection.probes[1].identity
    window.probe_combo.setCurrentIndex(window.probe_combo.findData(chosen))
    for width in (1024, 1280, 1600):
        window.resize(width, 800)
        for index in (3, 0, 1, 2, 3):
            window.pages.setCurrentIndex(index)
            window.retranslate_ui()
            QTest.qWait(10)
    # Cross the old 10-second periodic refresh boundary without mocking timers.
    QTest.qWait(10200)
    assert len(calls) == 1
    assert manager.selection.identity == chosen
    window.btn_probe_refresh.click()
    for _ in range(20):
        window.btn_probe_refresh.click()
    wait_for(lambda: manager.worker is None)
    assert len(calls) == 2 and manager.selection.identity == chosen
    manager._completed(manager._generation-1, parsed(nodes('OLD')))
    assert manager.selection.identity == chosen
    assert len(manager.selection.probes) == 2


def test_explicit_refresh_before_startup_does_not_schedule_a_second_scan(panel):
    _, create = panel
    calls = []
    manager = create(lambda _: calls.append(1) or parsed(nodes('A')))
    assert manager.refresh()
    wait_for(lambda: manager.worker is None and bool(manager.selection.identity))
    QTest.qWait(50)
    assert len(calls) == 1


def test_close_before_startup_never_enumerates(panel):
    _, create = panel
    calls = []
    manager = create(lambda _: calls.append(1) or parsed(nodes('A')))
    assert manager.request_close()
    QTest.qWait(50)
    assert calls == [] and manager.selection.identity == ''


@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('width',[1024,1280,1920])
def test_connection_groups_fit_their_own_pages(panel,language,width):
    window,create=panel
    manager=create(lambda _:parsed(nodes('A')))
    wait_for(lambda:manager.worker is None and bool(manager.selection.identity))
    window.i18n.set_language(language);window.retranslate_ui();window.resize(width,800)
    window.pages.setCurrentIndex(3)
    page=window.maintenance_page
    rect=lambda w:QRect(w.mapTo(window,QPoint()),w.size())
    for group,section,controls in (
            (window.probe_group,page.runtime_scroll,(window.probe_title,window.probe_combo,window.btn_probe_refresh,page.btn_swd_attach,page.btn_swd_detach,window.probe_status,window.header_swd_status)),
            (window.debug_connection_group,page.serial_section,(window.debug_port_combo,window.debug_baud_combo,window.btn_debug_connect,window.btn_debug_disconnect,window.debug_status))):
        page.sections.setCurrentWidget(section)
        # Long discovery text and the inactive connection action are now kept
        # in details/tooltips; geometry covers controls actually on the header.
        controls=tuple(control for control in controls if control.isVisible())
        assert controls
        wait_for(lambda:window.width()==width and all(rect(group).contains(rect(control)) for control in controls))
        assert window.header_bar.isAncestorOf(group)
        assert not page.isAncestorOf(group)
        for index,one in enumerate(controls):
            for two in controls[index+1:]:assert not rect(one).intersects(rect(two))
    assert rect(window.header_bar).contains(rect(window.header_connection_group))
    assert window.probe_status.isHidden() and window.probe_combo.toolTip()
    assert window.probe_combo.currentData().endswith('\\A')
    if language=='zh_CN':assert window.btn_probe_refresh.text()=='重新检测'
