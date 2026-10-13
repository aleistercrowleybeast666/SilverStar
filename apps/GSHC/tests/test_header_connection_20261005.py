"""Connection row geometry across Windows display scales, without serial I/O."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox

from services.i18n import I18n
from ui.main_window import MainWindow


def _Rect(widget, window):
    return QRect(widget.mapTo(window, QPoint()), widget.size())


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
        assert 0 <= group.left() - bar.left() <= 16
        assert _Rect(window.lbl_port_name, window).right() < _Rect(window.port_combo, window).left()
        assert _Rect(window.lbl_baud_name, window).right() < _Rect(window.baud_combo, window).left()
        assert _Rect(window.port_combo, window).right() < _Rect(window.lbl_baud_name, window).left()
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
