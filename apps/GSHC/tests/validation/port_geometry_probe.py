"""Isolated Qt process: style edit rect, popup, connected status and screenshots."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PySide6.QtCore import QSettings, Qt, QRect, QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox
from services.i18n import I18n
from ui.main_window import MainWindow

def Probe_Run(output: Path, width: int, height: int, baseline: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    for filename in ("segoeui.ttf", "msyh.ttc"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Microsoft YaHei", 16))
    window_type = MainWindow
    if baseline:
        import subprocess
        import types
        legacy_port = types.ModuleType("legacy_port")
        exec(subprocess.check_output(["git", "show", "HEAD:ui/port_combo.py"], text=True), legacy_port.__dict__)
        legacy_window = types.ModuleType("legacy_window")
        sys.modules[legacy_window.__name__] = legacy_window
        exec(subprocess.check_output(["git", "show", "HEAD:ui/main_window.py"], text=True, encoding="utf-8"), legacy_window.__dict__)
        legacy_window.PortComboBox = legacy_port.PortComboBox
        window_type = legacy_window.MainWindow
    window = window_type(I18n(QSettings(str(output / "ui.ini"), QSettings.Format.IniFormat)))
    window.resize(width, height)
    window.show()
    window.port_combo.setFont(QFont("Segoe UI", 16))
    if not baseline:
        window.debug_port_combo.setFont(QFont("Segoe UI", 16))
    window.conn_label.setFont(QFont("Segoe UI", 16))
    rows = []
    for port in ("COM1", "COM9", "COM10", "COM99", "COM100"):
        window.set_ports([port])
        if not baseline:
            window.debug_port_combo.setCurrentText(port)
        status = port + "@230400"
        window.set_connection_status(status)
        app.processEvents()
        if not baseline:
            baud = window.baud_combo
            baud_option = QStyleOptionComboBox()
            baud.initStyleOption(baud_option)
            baud_field = baud.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,
                baud_option, QStyle.SubControl.SC_ComboBoxEditField, baud)
            assert baud_field.width() >= baud.fontMetrics().horizontalAdvance(baud.currentText())
        combo = window.port_combo
        option = QStyleOptionComboBox()
        combo.initStyleOption(option)
        field = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,
                    option, QStyle.SubControl.SC_ComboBoxEditField, combo)
        metrics = combo.fontMetrics()
        required = max(metrics.horizontalAdvance(port), metrics.boundingRect(port).width())
        if not baseline:
            assert field.width() >= required, (port, field.width(), required)
        if not baseline:
            assert combo.minimumWidth() > 0
            window.pages.setCurrentWidget(window.maintenance_scroll)
            window.maintenance_page.sections.setCurrentWidget(window.maintenance_page.serial_section)
            app.processEvents()
            for debug_combo in (window.debug_port_combo, window.debug_baud_combo):
                debug_option = QStyleOptionComboBox()
                debug_combo.initStyleOption(debug_option)
                debug_field = debug_combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,
                    debug_option, QStyle.SubControl.SC_ComboBoxEditField, debug_combo)
                assert debug_field.width() >= debug_combo.fontMetrics().horizontalAdvance(debug_combo.currentText())
            assert window.debug_port_combo.toolTip() == port
            rect = lambda widget: QRect(widget.mapTo(window,QPoint()),widget.size())
            assert window.header_bar.isAncestorOf(window.header_connection_group)
            assert window.header_bar.isAncestorOf(window.debug_connection_group)
            assert window.header_bar.isAncestorOf(window.probe_group)
            assert window.probe_group.isAncestorOf(window.maintenance_page.btn_swd_attach)
            assert window.probe_group.isAncestorOf(window.maintenance_page.btn_swd_detach)
            assert not rect(window.header_connection_group).intersects(rect(window.debug_connection_group))
        combo.showPopup()
        app.processEvents()
        popup = combo.view().viewport().width()
        if not baseline:
            assert popup >= required
        if port == "COM100":
            combo.view().window().grab().save(str(output / "popup.png"))
        combo.hidePopup()
        label = window.conn_label
        # QLabel contents minus its documented margin/indent, including word wrap.
        available = label.contentsRect().adjusted(label.margin(), label.margin(),
                                                   -label.margin(), -label.margin())
        indent = label.indent()
        if indent < 0:
            indent = label.fontMetrics().horizontalAdvance("x") // 2 if label.frameWidth() else 0
        available.adjust(indent, 0, 0, 0)
        displayed = status if baseline else label.text()
        bounds = label.fontMetrics().boundingRect(QRect(0, 0, available.width(), 10000),
                    int(label.alignment()) | (int(Qt.TextFlag.TextWordWrap) if label.wordWrap() else 0), displayed)
        if not baseline:
            assert bounds.width() <= available.width(), (status, bounds, available)
            assert bounds.height() <= available.height(), (status, bounds, available)
        if baseline:assert label.text() == status
        else:
            assert status in label.toolTip()
            assert not label.wordWrap() and label.maximumWidth()<=88
        rows.append(dict(port=port, required=required, edit=field.width(), popup=popup,
                         status_width=available.width(), status_height=available.height(),
                         displayed=displayed,full_status_tooltip=label.toolTip(),text_width=bounds.width(), text_height=bounds.height()))
    window.grab().save(str(output / "window.png"))
    (output / "geometry.json").write_text(json.dumps(dict(scale=window.devicePixelRatioF(),
        requested=[width,height], actual=[window.width(),window.height()], rows=rows), indent=2))
    window.render_timer.stop()
    window.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("output", type=Path)
    parser.add_argument("width", type=int)
    parser.add_argument("height", type=int)
    args = parser.parse_args()
    Probe_Run(args.output, args.width, args.height, args.baseline)
