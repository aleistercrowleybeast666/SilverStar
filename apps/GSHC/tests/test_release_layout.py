"""Geometry checks for the four-page GSHC layout; no serial connection."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
from pathlib import Path

import pytest
from config import APP_VERSION
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionButton
from services.i18n import I18n
from services.preferences import Theme
from services.state_model import EventHistory, FlightControllerState
from ui.main_window import MainWindow


def rect(widget, window):
    return QRect(widget.mapTo(window, QPoint()), widget.size())


@pytest.fixture
def application():
    app = QApplication.instance() or QApplication([])
    original_font = app.font()
    # Windows offscreen Qt does not discover the installed font database.
    # Match the explicit font used by the compact flight-summary regression.
    for name in ("msyh.ttc", "consola.ttf", "segoeui.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Microsoft YaHei", 9))
    yield app
    app.setFont(original_font)


@pytest.mark.parametrize("size", [(1280, 720), (1536, 816)])
@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_four_pages_serial_row_and_flight_grid(application, tmp_path, size, language):
    app = application
    i18n = I18n(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.set_ports(["COM100"])
        window.resize(*size)
        window.show()
        QTest.qWait(50)
        assert window.width() == size[0]
        assert window.height() == size[1]
        assert [window.pages.widget(index) for index in range(window.pages.count())] == [
            window.preflight_page, window.flight_page, window.post_process_page,
            window.maintenance_scroll,
        ]
        assert [window.pages.tabText(index) for index in range(window.pages.count())] == [
            i18n.tr("page." + page) for page in
            ("preflight", "flight", "post_process", "maintenance")
        ]
        assert window.maintenance_scroll.widget() is window.maintenance_page
        assert window.header_title.width() > 0
        assert window.header_title.toolTip() == i18n.tr("app.brand")
        assert window.header_version.text() == f"SilverStar GSHC v{APP_VERSION}"
        assert rect(window.header_title, window).bottom() < rect(window.port_combo, window).top()
        assert rect(window.header_title, window).right() < rect(window.header_version, window).left()
        assert rect(window.header_version, window).right() < rect(window.header_credit, window).left()
        assert rect(window.lbl_theme, window).right() < rect(window.theme_combo, window).left()
        assert rect(window.theme_combo, window).right() < rect(window.lbl_language, window).left()
        assert rect(window.lbl_language, window).right() < rect(window.language_combo, window).left()
        assert rect(window.btn_refresh, window).right() < rect(window.lbl_port_name, window).left()
        assert rect(window.lbl_port_name, window).right() < rect(window.port_combo, window).left()
        assert rect(window.port_combo, window).right() < rect(window.lbl_baud_name, window).left()
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

        window.pages.setCurrentWidget(window.maintenance_scroll)
        app.processEvents()
        for widget in (window.btn_export_device, window.btn_download_device,
                       window.btn_refresh_device_logs, window.maintenance_page.catalog):
            assert window.maintenance_page.isAncestorOf(widget)
            window.maintenance_scroll.ensureWidgetVisible(widget, 0, 0)
            app.processEvents()
            assert rect(window.maintenance_scroll.viewport(), window).contains(rect(widget, window))

        window.pages.setCurrentWidget(window.flight_page)
        QTest.qWait(50)  # FlightPageScroll defers content sizing to the Qt event loop.
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
        expected_height = 160 if size[1] <= 720 else 190
        assert all(plot.width() >= 240 and plot.height() >= expected_height for plot in plots)
        # Ground, maintenance and probe controls can wrap the header to three
        # rows. The flight page deliberately scrolls; every complete plot must
        # remain reachable without shrinking or overlapping either plot row.
        for row in range(2):
            scrollbar = window.flight_page.verticalScrollBar()
            scrollbar.setValue(0 if row == 0 else scrollbar.maximum())
            QTest.qWait(20)
            for key in list(window.plot_widgets)[row * 3:(row + 1) * 3]:
                assert rect(window.flight_page.viewport(), window).contains(
                    rect(window.plot_widgets[key], window)
                )
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_small_window_scrolls_to_flight_plots_and_post_process_actions(application, tmp_path, language):
    app = application
    i18n = I18n(QSettings(str(tmp_path / "small.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.resize(1024, 600)
        window.show()
        QTest.qWait(50)
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
        QTest.qWait(50)
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


def test_header_language_theme_cycle_keeps_button_text_visible(application, tmp_path):
    window = MainWindow(I18n(QSettings(str(tmp_path / "cycle.ini"), QSettings.IniFormat)))
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.bind_runtime_model(FlightControllerState(), EventHistory())
        window.resize(1280, 720)
        window.show()
        QTest.qWait(150)
        for language in ("zh_CN", "en_US", "zh_CN", "en_US"):
            window.language_combo.setCurrentIndex(window.language_combo.findData(language))
            for theme in (Theme.LIGHT, Theme.DARK):
                window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme.value))
                QTest.qWait(150)
                for button in (window.btn_refresh, window.btn_connect, window.btn_disconnect,
                               window.btn_debug_connect, window.btn_debug_disconnect, window.btn_probe_refresh):
                    option = QStyleOptionButton()
                    option.initFrom(button)
                    option.text = button.text()
                    contents = button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, button)
                    assert contents.width() >= button.fontMetrics().horizontalAdvance(button.text()), button.text()
                for label in (window.lbl_port_name, window.lbl_baud_name,
                              window.lbl_debug_baud_name, window.probe_title):
                    assert label.width() >= label.fontMetrics().horizontalAdvance(label.text()), label.text()
    finally:
        window.close()
        window.deleteLater()
        application.processEvents()
