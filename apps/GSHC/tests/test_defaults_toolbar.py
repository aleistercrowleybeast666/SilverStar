"""Real Qt controls, private settings and offline fixtures; no device I/O."""
from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog

from services.i18n import I18n, Language
from services.preferences import (
    ALL_EXPORT_ITEMS, AppPreferences, ExportItem, ExportLanguage, ExportTheme, Theme,
)
from services.state_model import EventHistory, FlightControllerState
from ui.main_window import ExportOptionsDialog, MainWindow


@pytest.fixture
def settings(tmp_path):
    value = QSettings(str(tmp_path / "private.ini"), QSettings.IniFormat)
    value.setValue("connection/port", "COM_USER")
    value.setValue("data/root", "user-owned-data")
    return value


def Settings_Read(settings):
    return {key: settings.value(key) for key in settings.allKeys()}


def test_restore_export_draft_cancel_commit_reopen(qtbot, settings):
    prefs = AppPreferences(settings)
    prefs.set_theme(Theme.DARK)
    prefs.set_export_language(ExportLanguage.ZH_CN)
    prefs.set_export_theme(ExportTheme.LIGHT)
    prefs.set_export_items({ExportItem.CHARTS})
    dialog = ExportOptionsDialog(I18n(settings), prefs)
    qtbot.addWidget(dialog)
    dialog.range_combos["page"].setCurrentIndex(dialog.range_combos["page"].findData("custom"))
    dialog.range_custom["page"].setValue(18.75)
    dialog.resolved_options(Language.EN_US, Theme.DARK)
    saved = Settings_Read(settings)
    dialog.show()
    qtbot.mouseClick(dialog.btn_restore_defaults, Qt.LeftButton)
    assert Settings_Read(settings) == saved
    assert dialog.language_combo.currentData() == ExportLanguage.FOLLOW_UI.value
    assert dialog.export_theme_combo.currentData() == ExportTheme.FOLLOW_UI.value
    assert all(box.isChecked() for box in dialog.item_checkboxes.values())
    assert dialog._Range_Value("page") == 30.0
    assert dialog._Range_Value("gif") is None
    qtbot.mouseClick(dialog.btn_cancel, Qt.LeftButton)
    dialog.reload_preferences()
    assert dialog.language_combo.currentData() == ExportLanguage.ZH_CN.value
    assert dialog.export_theme_combo.currentData() == ExportTheme.LIGHT.value
    assert dialog._Range_Value("page") == 18.75
    assert Settings_Read(settings) == saved
    dialog.show()
    qtbot.mouseClick(dialog.btn_restore_defaults, Qt.LeftButton)
    qtbot.mouseClick(dialog.btn_accept, Qt.LeftButton)
    assert dialog.result() == QDialog.Accepted
    options = dialog.resolved_options(Language.EN_US, Theme.DARK)
    assert options.language is Language.EN_US and options.theme is Theme.DARK
    assert options.items == frozenset(ALL_EXPORT_ITEMS)
    assert options.page_duration_s == 30.0 and options.gif_source_duration_s is None
    dialog.reload_preferences()
    assert dialog._Range_Value("page") == 30.0
    assert prefs.export_language() is ExportLanguage.FOLLOW_UI
    assert prefs.export_theme() is ExportTheme.FOLLOW_UI
    assert prefs.theme() is Theme.DARK
    assert settings.value("connection/port") == "COM_USER"
    assert settings.value("data/root") == "user-owned-data"


@pytest.mark.parametrize("text,valid", [("19.875", True), ("", False), ("0", False)])
def test_export_direct_click_consumes_current_text_or_retains_invalid_draft(qtbot, settings, text, valid):
    dialog = ExportOptionsDialog(I18n(settings), AppPreferences(settings))
    qtbot.addWidget(dialog)
    dialog.range_combos["page"].setCurrentIndex(dialog.range_combos["page"].findData("custom"))
    dialog.range_custom["page"].setKeyboardTracking(False)
    dialog.show()
    editor = dialog.range_custom["page"].lineEdit()
    editor.setFocus()
    editor.setText(text)
    before = Settings_Read(settings)
    qtbot.mouseClick(dialog.btn_accept, Qt.LeftButton)
    assert Settings_Read(settings) == before
    if valid:
        assert dialog.result() == QDialog.Accepted
        assert dialog.resolved_options(Language.EN_US, Theme.LIGHT).page_duration_s == 19.875
    else:
        assert dialog.isVisible() and dialog.result() != QDialog.Accepted
        assert dialog.range_custom["page"].cleanText() == text
        assert dialog.lbl_range_error.isVisible()
        assert dialog.lbl_range_error.parentWidget() is dialog
        with pytest.raises(ValueError, match="export_range_invalid"):
            dialog.resolved_options(Language.EN_US, Theme.LIGHT)
        assert Settings_Read(settings) == before
        qtbot.mouseClick(dialog.btn_restore_defaults, Qt.LeftButton)
        assert not dialog.lbl_range_error.isVisible()
        assert dialog._Range_Value("page") == 30


@pytest.mark.parametrize("text,valid", [("19.875", True), ("", False), ("0", False)])
@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter])
def test_export_enter_uses_explicit_export_default_and_preserves_invalid_input(qtbot, settings, text, valid, key):
    dialog = ExportOptionsDialog(I18n(settings), AppPreferences(settings))
    qtbot.addWidget(dialog)
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData(ExportLanguage.ZH_CN.value))
    for item, checkbox in dialog.item_checkboxes.items():
        checkbox.setChecked(item is ExportItem.CHARTS)
    dialog.range_combos["page"].setCurrentIndex(dialog.range_combos["page"].findData("custom"))
    spin = dialog.range_custom["page"]
    spin.setKeyboardTracking(False)
    dialog.show()
    spin.lineEdit().setFocus()
    spin.lineEdit().setText(text)
    settings_before = Settings_Read(settings)
    qtbot.keyClick(spin.lineEdit(), key)
    print({"key": str(key), "input": text, "result": dialog.result(), "visible": dialog.isVisible(),
           "clean_text": spin.cleanText(), "export_default": dialog.btn_accept.isDefault(),
           "selected": [item.value for item, box in dialog.item_checkboxes.items() if box.isChecked()]})
    assert Settings_Read(settings) == settings_before
    assert dialog.language_combo.currentData() == ExportLanguage.ZH_CN.value
    assert [item for item, box in dialog.item_checkboxes.items() if box.isChecked()] == [ExportItem.CHARTS]
    assert dialog.btn_accept.isDefault()
    assert not any(button.autoDefault() for button in (
        dialog.btn_select_all, dialog.btn_select_none, dialog.btn_cancel, dialog.btn_restore_defaults))
    if valid:
        assert dialog.result() == QDialog.Accepted
        assert dialog.resolved_options(Language.EN_US, Theme.LIGHT).page_duration_s == 19.875
    else:
        assert dialog.isVisible() and dialog.result() != QDialog.Accepted
        assert spin.cleanText() == text
        assert dialog.lbl_range_error.isVisible()


@pytest.mark.parametrize("language", list(Language))
def test_header_snapshot_available_across_pages_without_changing_live_state(qtbot, settings, monkeypatch, language):
    def Hardware_Forbidden(*args, **kwargs):
        raise AssertionError("This UI workflow must not open a serial device")
    monkeypatch.setattr("transport.serial_backend.SerialLink.open", Hardware_Forbidden)
    i18n = I18n(settings)
    i18n.set_language(language)
    window = MainWindow(i18n)
    qtbot.addWidget(window)
    window.render_timer.stop()
    window.gl_view.hide()
    state = FlightControllerState()
    events = EventHistory()
    window.bind_runtime_model(state, events)
    authority = deepcopy(state)
    window.resize(960, 640)
    window.show()
    qtbot.waitUntil(lambda: window.header_mission_widget.isVisible())
    assert window.header_bar.isAncestorOf(window.btn_mission_profile)
    assert window.header_bar.isAncestorOf(window.lbl_mission_profile_summary)
    assert not window.post_process_page.isAncestorOf(window.btn_mission_profile)
    assert not window.btn_mission_trace.isEnabled()
    assert window.lbl_mission_profile_summary.text() == i18n.tr("mission_profile.none_short")
    path = Path(__file__).resolve().parents[3] / "contracts/mission_profile_v1.golden.json"
    monkeypatch.setattr("ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: (str(path), ""))
    qtbot.mouseClick(window.btn_mission_profile, Qt.LeftButton)
    profile = deepcopy(window._declared_mission_profile)
    assert profile and profile["project"]["name"] in window.lbl_mission_profile_summary.text()
    for index in range(window.pages.count()):
        window.pages.setCurrentIndex(index)
        window.set_data_tools_busy(True)
        window.render_state()
        assert window.btn_mission_profile.isVisible() and window.btn_mission_profile.isEnabled()
        assert window.btn_mission_profile_details.isVisible()
        assert not window.btn_process_data.isEnabled()
        assert window._state is state
        assert state.connected == authority.connected
        assert state.capability_acked == authority.capability_acked
        assert state.mission_started == authority.mission_started
        assert window.header_mission_widget.rect().contains(window.btn_mission_profile.geometry())
        assert window.header_mission_widget.rect().contains(window.btn_mission_profile_details.geometry())
    qtbot.mouseClick(window.btn_mission_profile_details, Qt.LeftButton)
    assert window.mission_profile_dialog.isVisible()
    assert profile["sha256"] in window.lbl_mission_profile.text()
    before = Settings_Read(settings)
    window.retranslate_ui()
    window.render_state()
    assert Settings_Read(settings) == before
    assert window.mission_profile_dialog.isVisible()
    assert window._declared_mission_profile == profile
    qtbot.keyClick(window.mission_profile_dialog, Qt.Key_Escape)
    assert not window.mission_profile_dialog.isVisible()
    monkeypatch.setattr("ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: ("", ""))
    qtbot.mouseClick(window.btn_mission_profile, Qt.LeftButton)
    assert window._declared_mission_profile == profile
    bad_path = Path(settings.fileName()).with_name("invalid.ssmission")
    bad_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("ui.main_window.QFileDialog.getOpenFileName", lambda *a, **k: (str(bad_path), ""))
    qtbot.mouseClick(window.btn_mission_profile, Qt.LeftButton)
    assert window._declared_mission_profile == profile
    assert i18n.tr("mission_profile.error_short") in window.lbl_mission_profile_summary.text()
    assert window._state is state and not state.connected and not state.mission_started


@pytest.mark.parametrize("language", list(Language))
def test_export_footer_reachable_in_small_dialog_after_language_change(qtbot, settings, language):
    i18n = I18n(settings)
    dialog = ExportOptionsDialog(i18n, AppPreferences(settings))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(560, 360)
    i18n.set_language(language)
    dialog.retranslate_ui()
    qtbot.waitUntil(lambda: dialog.btn_accept.isVisible())
    for button in (dialog.btn_restore_defaults, dialog.btn_accept, dialog.btn_cancel):
        assert button.parentWidget() is dialog
        assert dialog.rect().contains(button.geometry())
    assert dialog.btn_restore_defaults.text() == i18n.tr("button.restore_defaults")
    qtbot.mouseClick(dialog.btn_select_none, Qt.LeftButton)
    assert not dialog.btn_accept.isEnabled()
    qtbot.mouseClick(dialog.btn_restore_defaults, Qt.LeftButton)
    assert dialog.btn_accept.isEnabled()


@pytest.mark.parametrize("scale", ["1.25", "1.5"])
def test_snapshot_toolbar_and_export_footer_at_laptop_scale(tmp_path, scale):
    import os
    import subprocess
    import sys
    code = """
import sys
from pathlib import Path
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtWidgets import QApplication
from services.i18n import I18n, Language
from ui.main_window import MainWindow
application = QApplication([])
directory = Path(sys.argv[1])
scale = float(sys.argv[2])
window = MainWindow(I18n(QSettings(str(directory / 'private.ini'), QSettings.IniFormat)))
window.render_timer.stop()
window.gl_view.hide()
width, height = int(1366 / scale), int(768 / scale) - 40
window.resize(width, height)
window.show()
application.processEvents()
try:
    for language in Language:
        window.i18n.set_language(language)
        window.retranslate_ui()
        application.processEvents()
        assert window.width() <= width
        for button in (window.btn_mission_profile, window.btn_mission_profile_details):
            point = button.mapTo(window, QPoint(0, 0))
            assert point.x() >= 0 and point.x() + button.width() <= width
            assert point.y() >= 0 and point.y() + button.height() <= height
        dialog = window.export_options_dialog
        dialog.resize(560, min(360, height))
        dialog.show()
        application.processEvents()
        for button in (dialog.btn_restore_defaults, dialog.btn_cancel, dialog.btn_accept):
            assert dialog.rect().contains(button.geometry())
        assert dialog.height() <= height
        dialog.grab().save(str(directory / (language.value + '-export.png')))
        dialog.close()
        window.grab().save(str(directory / (language.value + '-toolbar.png')))
finally:
    window.close()
    window.deleteLater()
    application.processEvents()
"""
    environment = dict(os.environ, QT_SCALE_FACTOR=scale, QT_QPA_PLATFORM="offscreen",
                       QT_QPA_FONTDIR="C:/Windows/Fonts", PYTHONDONTWRITEBYTECODE="1",
                       TEMP=str(tmp_path), TMP=str(tmp_path))
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path), scale],
                            env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
