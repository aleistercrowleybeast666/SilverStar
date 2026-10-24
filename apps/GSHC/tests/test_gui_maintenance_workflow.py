import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json,time
from pathlib import Path
from threading import Event
from unittest.mock import patch
import pytest
from PySide6.QtCore import QSettings,QThread,Qt
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from app import Controller
from services.device_export import ExportCancelled
from services.i18n import I18n
from services.swd_summary import Summary_Build
from test_file_service_client import MockTransport
from transport.probe_inventory import ProbeInventory,ProbeInventoryResult
from ui.main_window import MainWindow


def wait_for(predicate):
    end=time.monotonic()+5
    while not predicate() and time.monotonic()<end:QTest.qWait(10)
    assert predicate()


@pytest.fixture
def gui(tmp_path):
    application=QApplication.instance() or QApplication([])
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():QFontDatabase.addApplicationFont(str(font));application.setFont(QFont('Microsoft YaHei',10))
    window=MainWindow(I18n(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)))
    window.render_timer.stop();window.gl_view.hide()
    with patch('app.USER_DATA_ROOT',tmp_path),patch('app.list_serial_port_names',return_value=[]):
        controller=Controller(window,probe_enumerator=lambda _:ProbeInventory(ProbeInventoryResult.Empty))
    window.resize(1280,800);window.pages.setCurrentIndex(3);window.show();QTest.qWait(30)
    yield window,controller,tmp_path
    controller.shutdown();QTest.qWait(30);window.close();window.deleteLater();application.processEvents()


def connect(window,controller,wire):
    controller.file_transfer.transport_factory=lambda *_:wire
    window.debug_port_combo.setCurrentText('COM-MOCK');window.btn_debug_connect.click()
    wait_for(lambda:window._debug_service_supported)


def test_groups_are_on_correct_pages_and_splitter_does_not_move(gui):
    window,controller,_=gui;page=window.maintenance_page
    assert page.sections.count()==2
    assert [page.sections.tabText(i) for i in range(2)]==['SWD 调试','串口']
    assert window.header_bar.isAncestorOf(window.probe_group)
    assert window.header_bar.isAncestorOf(window.debug_connection_group)
    assert window.probe_group.isAncestorOf(page.btn_swd_attach)
    assert window.probe_group.isAncestorOf(page.btn_swd_detach)
    assert not page.isAncestorOf(window.probe_group)
    assert not page.isAncestorOf(window.debug_connection_group)
    assert page.runtime_section.isAncestorOf(page.btn_swd_import)
    assert page.runtime_section.isAncestorOf(page.btn_swd_relocate)
    assert page.serial_group.isAncestorOf(page.console)
    assert page.serial_group.isAncestorOf(window.btn_download_device)
    assert window.btn_download_device.menu() is None and window.btn_export_device.menu() is None
    assert not hasattr(window,'action_download_delete')
    assert not window.action_export_cut.isEnabled() and not window.btn_cut_device.isEnabled()
    assert window.btn_cut_device.isHidden()
    assert page.serial_group.isAncestorOf(window.btn_cut_device)
    for width in (1024,1280,1600):
        window.resize(width,800);QTest.qWait(30);sizes=window.content_splitter.sizes()
        for subpage in (0,1,0):
            page.sections.setCurrentIndex(subpage)
            assert window.probe_group.isVisible() and window.debug_connection_group.isVisible()
        for index in (3,0,1,2,3)*2:
            window.pages.setCurrentIndex(index);QTest.qWait(10)
            assert window.attitude_panel.isVisible() and window.content_splitter.sizes()==sizes


def test_export_confirmation_selection_sizes_verified_results_and_reopen(gui):
    window,c,root=gui;wire=MockTransport();connect(window,c,wire);manager=c.file_transfer
    manager.choose_download();dialog=manager.export_dialog
    assert dialog.isVisible() and not any('ENTER' in cmd for cmd in wire.commands)
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.No):dialog.refresh.click()
    assert not manager.busy and not any('ENTER' in cmd for cmd in wire.commands)
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.Yes):dialog.refresh.click()
    wait_for(lambda:not manager.busy and dialog.files.topLevelItemCount()==1)
    assert dialog.files.topLevelItem(0).text(1)=='9 B'
    assert window.i18n.settings.value(window.maintenance_page.TF_DIRECTORY_KEY) is None
    assert not any(' READ ' in cmd for cmd in wire.commands)
    dialog.all.setChecked(True);dialog.path.setText(str(root))
    assert '1 / 1' in dialog.count.text() and '9 B' in dialog.count.text()
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.Yes):dialog.start.click()
    wait_for(lambda:not manager.busy)
    assert '已下载并校验' in dialog.files.topLevelItem(0).text(2)
    assert window.i18n.settings.value(window.maintenance_page.TF_DIRECTORY_KEY)==str(root)
    manifest=json.loads(next(root.glob('SilverStar_download_*/manifest.json')).read_text())
    assert [item['file_id'] for item in manifest['files']]==[1]
    assert wire.data==b'123456789' and not any('DELETE' in cmd for cmd in wire.commands)
    before=list(wire.commands);dialog.close();manager.choose_download();QTest.qWait(30)
    assert dialog.isVisible() and '已下载并校验' in dialog.files.topLevelItem(0).text(2)
    assert not any(cmd.startswith(('LOGFILE ENTER','LOGFILE READ')) for cmd in wire.commands[len(before):])
    window.btn_debug_disconnect.click();wait_for(lambda:manager.owner is None)
    assert dialog.files.topLevelItemCount()==0 and not dialog.start.isEnabled()


def test_close_cancels_download_and_reopening_does_not_restart_job(gui):
    window,c,root=gui;entered=Event()
    class SlowWire(MockTransport):
        def exchange(self,command,timeout,cancel):
            if command.startswith('LOGFILE READ '):
                entered.set();cancel.wait(3)
                if cancel.is_set():raise ExportCancelled('Cancelled by dialog')
            return super().exchange(command,timeout,cancel)
    wire=SlowWire();connect(window,c,wire);manager=c.file_transfer;manager.choose_download();dialog=manager.export_dialog
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.Yes):dialog.refresh.click()
    wait_for(lambda:not manager.busy and dialog.files.topLevelItemCount()==1)
    dialog.all.setChecked(True);dialog.path.setText(str(root))
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.Yes):dialog.start.click()
    wait_for(entered.is_set);dialog.close();wait_for(lambda:not manager.busy)
    assert window.i18n.settings.value(window.maintenance_page.TF_DIRECTORY_KEY) is None
    assert not list(root.glob('SilverStar_download_*/*.sslog')) and wire.data==b'123456789'
    before=sum(cmd.startswith('LOGFILE ENTER') for cmd in wire.commands);manager.choose_download();QTest.qWait(30)
    assert sum(cmd.startswith('LOGFILE ENTER') for cmd in wire.commands)==before


def test_explicit_default_directory_setting_and_same_owner_manual_read(gui):
    window,c,root=gui;page=window.maintenance_page;destination=root/'exports';destination.mkdir()
    with patch('ui.file_transfer.QFileDialog.getExistingDirectory',return_value=str(destination)):
        page.btn_destination.click()
    assert page.destination_path.text()==str(destination)
    assert window.i18n.settings.value(page.TF_DIRECTORY_KEY)==str(destination)
    wire=MockTransport();connect(window,c,wire);manager=c.file_transfer
    assert manager.send_command(f'LOGFILE READ 1 {wire.token} 0')
    assert not manager.send_command('SYSTEM STATUS')
    wait_for(lambda:not manager.busy)
    assert 'data=313233343536373839' in page.console.output.toPlainText()
    assert not any(command=='LOGFILE ENTER' for command in wire.commands)
    assert list(destination.iterdir())==[]
    manager.choose_download();manager.export_dialog.set_catalog([{'id':1,'size':9}]);manager.export_dialog.all.setChecked(True)
    with patch('ui.log_export_dialog.QMessageBox.question',return_value=QMessageBox.Yes):manager.export_dialog.start.click()
    wait_for(lambda:not manager.busy)
    assert len(list(destination.glob('SilverStar_download_*/*.sslog')))==1
    assert any(command=='LOGFILE ENTER' for command in wire.commands)


def test_telemetry_session_replacement_and_swd_do_not_revalidate_old_ready(gui):
    window,c,_=gui;page=window.maintenance_page;state=c.state
    state.connected=True;state.system_ready=True;state.selftest_passed=True
    stamp=time.monotonic_ns();state.handshake.last_preflight_status_rx_monotonic_ns=stamp
    page._telemetry_render_ns=0;page.render(state)
    assert page.labels['system'][1].isEnabled() and 'True' in page.labels['system'][1].text()
    state.session_generation+=1;page.render(state)
    assert not page.labels['system'][1].isEnabled()
    rows=[dict(id='task.preparation',state='OBSERVED',fields={'ready':1},received_ns=time.monotonic_ns(),reason='ram_observation')]
    page.set_swd_summary(Summary_Build(rows,True),matched=True);page._telemetry_render_ns=0;page.render(state)
    assert not page.labels['system'][1].isEnabled()
    state.handshake.last_preflight_status_rx_monotonic_ns=time.monotonic_ns();page._telemetry_render_ns=0;page.render(state)
    assert page.labels['system'][1].isEnabled()
    state.connected=False;page.render(state)
    assert not page.labels['system'][1].isEnabled() and page.tree.isEnabled()


def test_console_uses_owner_thread_and_blocks_control_and_invalidates_disconnect(gui):
    window,c,_=gui;threads=[]
    assert not c.file_transfer.send_command('SYSTEM STATUS')
    assert '未发送' in window.maintenance_page.console.output.toPlainText()
    class ConsoleWire(MockTransport):
        def exchange(self,command,timeout,cancel):
            if command=='CAL STATUS':
                threads.append(QThread.currentThread());self.commands.append(command)
                return 'OK CAL STATUS state=WAIT_FACE ready=0'
            return super().exchange(command,timeout,cancel)
    wire=ConsoleWire();connect(window,c,wire);panel=window.maintenance_page.console
    panel.raw_mode.setChecked(True);panel.raw.setText('CAL RESET');assert not panel.send.isEnabled()
    assert not c.file_transfer.send_command('CAL RESET') and 'CAL RESET' not in wire.commands
    panel.raw.setText('CAL STATUS');assert panel.send.isEnabled();panel.send.click()
    wait_for(lambda:'WAIT_FACE' in panel.output.toPlainText() and not c.file_transfer.busy)
    assert threads and all(thread!=QApplication.instance().thread() for thread in threads)
    assert not c.swd.snapshot
    window.btn_debug_disconnect.click();wait_for(lambda:c.file_transfer.owner is None)
    assert not panel.send.isEnabled() and '历史响应' in panel.output.toPlainText()


def test_stale_unknown_and_disconnected_values_cannot_look_current(gui):
    window,c,_=gui;page=window.maintenance_page
    rows=[dict(id='task.preparation',state='OBSERVED',fields={'start_blocking_mask':0x80000080,'ready':0},received_ns=time.monotonic_ns()-7_000_000_000,reason='ram_observation')]
    page.set_swd_summary(Summary_Build(rows,True),matched=True);box,label,age=page.summary_cards['task.preparation']
    assert box.isEnabled() and '历史观测' in label.text() and '校准尚未就绪' in label.text() and '未知位' in label.text()
    page.set_swd_summary(Summary_Build(rows,False),matched=False)
    assert 'UNKNOWN' in label.text() and '校准尚未就绪' not in label.text()


def test_failed_serial_close_retains_owner_and_retries_only_release(gui):
    window,c,_=gui;created=[]
    class CloseWire(MockTransport):
        closes=0
        def close(self):
            self.closes+=1
            if self.closes==1:raise OSError('mock close uncertain')
            super().close()
    wire=CloseWire()
    def factory(*_):created.append(True);return wire
    c.file_transfer.transport_factory=factory
    window.debug_port_combo.setCurrentText('MOCK')
    with patch('ui.file_transfer.QMessageBox.warning'):
        window.btn_debug_connect.click();wait_for(lambda:window._debug_service_supported)
        owner=c.file_transfer.owner;window.btn_debug_disconnect.click()
        wait_for(lambda:not owner.isRunning())
        QTest.qWait(30)
        assert c.file_transfer.owner is owner and owner.unreleased_transport is wire
        assert not window.btn_debug_connect.isVisible() and window.btn_debug_disconnect.isEnabled()
        assert '重试' in window.btn_debug_disconnect.text()
        assert not c.file_transfer.send_command('SYSTEM STATUS')
        window.btn_debug_disconnect.click();wait_for(lambda:c.file_transfer.owner is None)
    assert wire.closed and wire.closes==2 and created==[True]


def test_inactive_palette_remains_readable_and_export_retranslates(gui):
    from PySide6.QtGui import QPalette
    from ui.theme import Theme,apply_application_theme
    window,c,_=gui;app=QApplication.instance();palette=app.palette();sheet=app.styleSheet()
    try:
        apply_application_theme(app,Theme.DARK)
        colors=app.palette()
        assert colors.color(QPalette.Inactive,QPalette.Text)==colors.color(QPalette.Active,QPalette.Text)
        assert colors.color(QPalette.Disabled,QPalette.Text)!=colors.color(QPalette.Active,QPalette.Text)
        def luminance(color):
            values=[component/12.92 if component<=.04045 else ((component+.055)/1.055)**2.4 for component in (color.redF(),color.greenF(),color.blueF())]
            return .2126*values[0]+.7152*values[1]+.0722*values[2]
        for group in (QPalette.Active,QPalette.Inactive,QPalette.Disabled):
            foreground=luminance(colors.color(group,QPalette.PlaceholderText));background=luminance(colors.color(group,QPalette.Base))
            assert (max(foreground,background)+.05)/(min(foreground,background)+.05)>=4.5
        console=window.maintenance_page.console
        assert console.parameters.isHidden()
        console.choice.setCurrentIndex(console.choice.findData('SYSTEM DIAG'))
        assert not console.parameters.isHidden()
        console.category.setCurrentIndex(console.category.findData('CAL'))
        console.choice.setCurrentIndex(console.choice.findData('CAL STATUS'))
        assert console.parameters.isHidden()
        dialog=c.file_transfer.export_dialog;dialog.set_catalog([{'id':1,'size':9}]);dialog.all.setChecked(True)
        dialog.show_results([{'file_id':1,'sha256':'test'}]);window.i18n.set_language('en_US');window.retranslate_ui()
        assert dialog.files.topLevelItem(0).text(2)=='Downloaded and verified'
    finally:
        app.setPalette(palette);app.setStyleSheet(sheet)
