"""Geometry checks for the three-page GSHC layout; no serial connection."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from ui.main_window import MainWindow


def rect(widget, window):
    return QRect(widget.mapTo(window, QPoint()), widget.size())


@pytest.mark.parametrize("size", [(1280, 720), (1536, 816)])
@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_three_pages_serial_row_and_flight_grid(tmp_path, size, language):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.set_ports(["COM100"])
        window.resize(*size)
        window.show()
        app.processEvents()
        assert window.width() == size[0]
        assert window.height() == size[1]
        assert [window.pages.widget(index) for index in range(window.pages.count())] == [
            window.preflight_page, window.flight_page, window.post_process_page
        ]
        assert window.header_title.width() > 0
        assert window.header_title.toolTip() == i18n.tr("app.brand")
        assert window.header_version.text() == "SilverStar GSHC v0.1.1"
        assert rect(window.header_title, window).bottom() < rect(window.port_combo, window).top()
        assert rect(window.header_title, window).right() < rect(window.header_version, window).left()
        assert rect(window.header_version, window).right() < rect(window.header_credit, window).left()
        assert rect(window.lbl_theme, window).right() < rect(window.theme_combo, window).left()
        assert rect(window.theme_combo, window).right() < rect(window.lbl_language, window).left()
        assert rect(window.lbl_language, window).right() < rect(window.language_combo, window).left()
        assert rect(window.lbl_port_name, window).right() < rect(window.port_combo, window).left()
        assert rect(window.port_combo, window).right() < rect(window.btn_refresh, window).left()
        assert rect(window.btn_refresh, window).right() < rect(window.lbl_baud_name, window).left()
        assert rect(window.lbl_baud_name, window).right() < rect(window.baud_combo, window).left()
        assert rect(window.baud_combo, window).right() < rect(window.btn_connect, window).left()
        assert rect(window.btn_connect, window).right() < rect(window.btn_disconnect, window).left()
        assert rect(window.btn_disconnect, window).right() < rect(window.conn_label, window).left()
        assert window.current_port() == "COM100"
        assert window.baud_combo.isEditable()
        assert window.current_baudrate() == 230400
        window.baud_combo.setCurrentText("250000")
        assert window.current_baudrate() == 250000

        window.pages.setCurrentWidget(window.preflight_page)
        app.processEvents()
        summary = [rect(widget.parentWidget(), window) for widget in (
            window.lbl_pf_system_ready, window.lbl_cal_ready, window.lbl_align_ready
        )]
        assert summary[0].top() == summary[1].top() == summary[2].top()
        assert summary[0].right() < summary[1].left() < summary[2].left()
        viewport = rect(window.preflight_page.viewport(), window)
        for widget in (window.lbl_pf_system_ready, window.lbl_pf_accel,
                       window.btn_start):
            window.preflight_page.ensureWidgetVisible(widget, 0, 0)
            app.processEvents()
            assert viewport.contains(rect(widget, window))

        window.pages.setCurrentWidget(window.post_process_page)
        app.processEvents()
        assert window.post_process_page.isAncestorOf(window.btn_process_data)
        assert window.post_process_page.isAncestorOf(window.btn_select_data_root)

        window.pages.setCurrentWidget(window.flight_page)
        app.processEvents()
        cards = [rect(widget.parentWidget(), window) for widget in (
            window.lbl_flight_lifecycle, window.lbl_flight_accel, window.lbl_mission_state
        )]
        assert cards[0].top() == cards[1].top() == cards[2].top()
        assert cards[0].right() < cards[1].left() < cards[2].left()
        assert abs(cards[1].width() - 2 * cards[0].width()) <= 10
        assert abs(cards[2].width() - 2 * cards[0].width()) <= 10
        plots = [rect(window.plot_widgets[(key, axis)], window)
                 for key in ("vel", "pos") for axis in range(3)]
        assert len({plot.top() for plot in plots[:3]}) == 1
        assert len({plot.top() for plot in plots[3:]}) == 1
        assert plots[0].bottom() < plots[3].top()
        assert all(window.rect().contains(plot) for plot in plots)
        expected_height = 160 if size[1] <= 720 else 190
        assert all(plot.width() >= 240 and plot.height() >= expected_height for plot in plots)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_small_window_scrolls_to_flight_plots_and_post_process_actions(tmp_path, language):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / "small.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.resize(1024, 600)
        window.show()
        app.processEvents()
        assert window.size().width() == 1024
        assert window.size().height() == 600
        for widget in (window.header_title, window.header_version, window.header_credit,
                       window.theme_combo, window.language_combo, window.lbl_port_name,
                       window.port_combo, window.btn_refresh, window.lbl_baud_name,
                       window.baud_combo, window.btn_connect, window.btn_disconnect,
                       window.conn_label):
            assert window.rect().contains(rect(widget, window))
        assert rect(window.lbl_port_name, window).right() < rect(window.port_combo, window).left()
        assert rect(window.lbl_baud_name, window).right() < rect(window.baud_combo, window).left()
        window.pages.setCurrentWidget(window.flight_page)
        app.processEvents()
        assert window.flight_page.verticalScrollBar().maximum() > 0
        last_plot = window.plot_widgets[("pos", 2)]
        window.flight_page.verticalScrollBar().setValue(
            window.flight_page.verticalScrollBar().maximum()
        )
        app.processEvents()
        assert rect(window.flight_page.viewport(), window).contains(rect(last_plot, window))
        window.pages.setCurrentWidget(window.post_process_page)
        window.post_process_page.ensureWidgetVisible(window.btn_select_data_root, 0, 0)
        app.processEvents()
        assert rect(window.post_process_page.viewport(), window).contains(
            rect(window.btn_select_data_root, window)
        )
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
