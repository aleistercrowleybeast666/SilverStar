"""Acceptance regressions for visible reasons and display-only maintenance controls."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.i18n import I18n
from services.magnetometer_workflow import MagDevices_Parse
from ui.maintenance_console import MaintenanceConsole
from ui.maintenance_page import MaintenancePage
from ui.swd_watch import SwdWatchPanel


@pytest.fixture
def ui_context(tmp_path):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / "acceptance.ini"), QSettings.IniFormat))
    i18n.set_language("zh_CN")
    return app, i18n


def test_mag_list_accepts_the_linked_jy901b_adapter_name():
    response = ("OK MAG LIST count=1 DATA instance=0 descriptor_id=5 "
                "physical_device_id=5 shared=1 device=JY901B Magnetometer Adapter model=JY901B")
    devices = MagDevices_Parse(response)
    assert len(devices) == 1
    assert devices[0].instance == 0 and devices[0].physical_device_id == 5
    assert devices[0].name == "JY901B Magnetometer Adapter / JY901B"


@pytest.mark.parametrize("body", (
    "instance=0 instance=1 physical_device_id=5 device=JY901B model=JY901B",
    "instance=0 physical_device_id=5 device=JY901B physical_device_id=6 model=JY901B",
    "instance=0 physical_device_id=5 device=JY901B\nAdapter model=JY901B",
))
def test_mag_list_keeps_identity_and_control_character_rejection(body):
    with pytest.raises(ValueError):
        MagDevices_Parse("OK MAG LIST count=1 DATA " + body)


def test_clear_response_display_preserves_command_and_protocol_state(ui_context):
    app, i18n = ui_context
    panel = MaintenanceConsole(i18n)
    try:
        panel.set_connection(True)
        panel.set_runtime_capabilities({"supported": "1", "file_service_version": "1", "maintenance": "0.1"})
        panel.raw.setText("SYSTEM INFO")
        panel.show_response("SYSTEM INFO", "OK SYSTEM INFO firmware=0.1.3")
        caps, command = dict(panel._runtime_caps), panel.raw.text()
        sent = []
        panel.send_requested.connect(sent.append)
        panel.clear_display.click()
        assert panel.output.toPlainText() == ""
        assert panel._runtime_caps == caps and panel.raw.text() == command
        assert panel.connected and not panel.busy and sent == []
        panel.show_response("SYSTEM STATUS", "OK SYSTEM STATUS ready=0")
        assert "ready=0" in panel.output.toPlainText()
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()


def test_unsupported_candidate_explains_empty_watch_table_and_offers_real_scalar(ui_context):
    app, i18n = ui_context
    unsupported = SimpleNamespace(id="APP/Src/app_tasks.c::s_device_stack", unavailable="Missing/invalid DWARF size", type_name="", address=0)
    scalar = SimpleNamespace(id="APP/Src/estimator_bus.c::s_head", unavailable="", type_name="uint16_t", address=0x20000000)
    panel = SwdWatchPanel(i18n)
    try:
        panel.set_firmware(SimpleNamespace(watches=(unsupported, scalar), dwarf=True))
        panel.search.setText("s_device_stack")
        assert not panel.add.isEnabled() and not panel.remove.isEnabled()
        assert "DWARF" in panel.candidate_help.text()
        assert scalar.id in panel.candidate_help.text()
        assert panel.table.topLevelItemCount() == 0 and not panel.empty_hint.isHidden()
        panel.search.setText("s_head")
        assert panel.add.isEnabled()
        panel.add.click()
        assert panel.selected == [scalar.id]
        assert panel.table.topLevelItemCount() == 1
        assert panel.empty_hint.isHidden()
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()


def test_unknown_diagnostic_is_readable_when_matched_but_mismatch_stays_protected(ui_context):
    app, i18n = ui_context
    page = MaintenancePage(i18n)
    row = {"id": "thread.estimator", "state": "UNKNOWN", "reason": "sequence_changed_or_writer_active", "values": {}, "host_age_ms": 0}
    try:
        page.set_swd_summary([row], matched=True)
        box, value, age = page.summary_cards["thread.estimator"]
        assert box.isEnabled()
        assert "序列" in age.text()
        assert age.toolTip() == "sequence_changed_or_writer_active"
        page.set_swd_summary([{**row, "state": "OBSERVED", "values": {"last_duration_us": 123}}], matched=False)
        assert not box.isEnabled()
        assert "123" not in value.text()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_details_copy_preserves_complete_reason_and_table_can_expand(ui_context):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem
    app,i18n=ui_context;page=MaintenancePage(i18n)
    reason='sequence_changed_or_writer_active'
    item=QTreeWidgetItem(['Estimator','UNKNOWN: '+reason,'','RX; sequence unconfirmed'])
    item.setData(0,Qt.UserRole,'reason='+reason)
    page.swd_diagnostics.addTopLevelItem(item)
    try:
        page.swd_details.show();app.processEvents()
        page.swd_copy.click()
        assert reason in QApplication.clipboard().text()
        page.swd_diagnostics.setCurrentItem(item)
        assert reason in page.swd_reason_text.toPlainText()
        assert page.swd_diagnostics.height()>200
        assert page.swd_diagnostics.textElideMode()==Qt.ElideNone
        assert page.swd_diagnostics.wordWrap()
    finally:
        page.close();page.deleteLater();app.processEvents()


def test_byte_progress_unknown_and_verification_are_explicit(ui_context):
    from services.transfer_progress import TransferProgress
    from ui.log_export_dialog import LogExportDialog
    app,i18n=ui_context;dialog=LogExportDialog(i18n)
    try:
        dialog.show_byte_progress(TransferProgress(64,None,'receiving'))
        assert dialog.progress.maximum()==0
        assert '64 B' in dialog.status.text() and '总量未知' in dialog.status.text()
        dialog.show_byte_progress(TransferProgress(100,100,'verifying'))
        assert dialog.progress.value()==1000 and '校验' in dialog.status.text()
        assert '完成' not in dialog.status.text()
        dialog.show_byte_progress(TransferProgress(64,None,'failed'))
        assert dialog.progress.maximum()==1000 and '失败' in dialog.status.text()
    finally:
        dialog.close();dialog.deleteLater();app.processEvents()
