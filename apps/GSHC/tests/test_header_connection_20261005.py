"""Connection row geometry across Windows display scales, without serial I/O."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox

from services.i18n import I18n
from ui.main_window import MainWindow


def _Rect(widget, window):
    return QRect(widget.mapTo(window, QPoint()), widget.size())


@pytest.mark.parametrize("language", ("zh_CN", "en_US"))
@pytest.mark.parametrize("width", (1024, 1280, 1536, 1760))
def test_header_keeps_full_identity_above_device_controls(tmp_path, language, width):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / "two-rows.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.set_ports(["COM100"])
        window.resize(width, 800)
        window.show()
        QTest.qWait(80)
        identity = _Rect(window.header_identity_widget, window)
        preferences = _Rect(window.header_preferences_widget, window)
        devices = _Rect(window.header_connection_widget, window)
        assert identity.bottom() < devices.top()
        assert preferences.bottom() < devices.top()
        assert not identity.intersects(preferences)
        for label, key in ((window.header_title, "app.brand"),
                           (window.header_version, "app.product_version"),
                           (window.header_credit, "app.credit")):
            assert label.isVisible()
            assert label.text() == i18n.tr(key)
            assert label.contentsRect().width() >= label.fontMetrics().horizontalAdvance(label.text())
            assert identity.contains(_Rect(label, window))
        groups = (window.btn_refresh, window.header_connection_group,
                  window.debug_connection_group, window.probe_group)
        bounds = [_Rect(group, window) for group in groups]
        assert all(devices.contains(bound) for bound in bounds)
        # Normal desktop widths use exactly two header rows. At narrow widths
        # the device groups may wrap, retaining every control without overlap.
        if width >= 1536:
            assert max(bound.top() for bound in bounds) < min(bound.bottom() for bound in bounds)
        assert all(not bounds[i].intersects(bounds[j]) for i in range(len(bounds)) for j in range(i))
        for widget in (window.port_combo, window.baud_combo, window.debug_port_combo,
                       window.debug_baud_combo, window.probe_combo, window.btn_probe_refresh,
                       window.theme_combo, window.language_combo):
            assert widget.isVisible()
            assert _Rect(window.header_bar, window).contains(_Rect(widget, window))
        assert window.current_port() == "COM100"
        assert window.current_baudrate() == 230400
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("language", ("zh_CN", "en_US"))
def test_connection_controls_left_aligned_and_baud_edit_field_fits(tmp_path, language):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        long_port = "COM_" + "LONG_DEVICE_" * 5
        window.set_ports([long_port])
        window.set_connection_status("Disconnected")
        window.resize(1024, 600)
        window.show()
        app.processEvents()
        assert window.current_port() == long_port
        assert window.port_combo.toolTip() == long_port
        assert window.port_combo.width() <= 180
        group = _Rect(window.header_connection_group, window)
        bar = _Rect(window.header_bar, window)
        refresh = _Rect(window.btn_refresh,window)
        # The unified refresh control now precedes both serial-role groups.
        assert 0 <= refresh.left() - bar.left() <= 16
        assert 0 < group.left() - refresh.right() <= 16
        assert _Rect(window.lbl_port_name, window).right() < _Rect(window.port_combo, window).left()
        assert window.lbl_baud_name.isHidden()
        assert window.baud_combo.toolTip()==i18n.tr('field.baudrate')
        assert _Rect(window.port_combo, window).right() < _Rect(window.baud_combo, window).left()
        assert window.baud_combo.isEditable() and not window.baud_combo.lineEdit().isReadOnly()
        for baud in ("230400", "921600", "2000000"):
            window.baud_combo.setCurrentText(baud)
            app.processEvents()
            assert window.current_baudrate() == int(baud)
            option = QStyleOptionComboBox()
            window.baud_combo.initStyleOption(option)
            option.rect = window.baud_combo.rect()
            field = window.baud_combo.style().subControlRect(
                QStyle.ComplexControl.CC_ComboBox, option,
                QStyle.SubControl.SC_ComboBoxEditField, window.baud_combo)
            metrics = window.baud_combo.lineEdit().fontMetrics()
            assert field.width() >= metrics.horizontalAdvance(baud) + 12
            assert window.baud_combo.lineEdit().width() >= metrics.horizontalAdvance(baud) + 12
    finally:
        window.close()
