"""Actual offscreen Qt geometry; no serial/controller policy changes."""
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from services.preferences import Theme
from services.state_model import EventHistory
from test_ui_workflow import ready_state
from ui.main_window import MainWindow


@pytest.mark.parametrize('language', ['zh_CN', 'en_US'])
@pytest.mark.parametrize('theme', [Theme.LIGHT, Theme.DARK])
@pytest.mark.parametrize('size,font_pt', [((1920, 1020), 9), ((1280, 720), 9), ((1024, 600), 13)])
def test_status_cards_use_content_height_and_six_plots_keep_remainder(tmp_path, language, theme, size, font_pt):
    app = QApplication.instance() or QApplication([])
    original_font = app.font()
    for name in ('msyh.ttc', 'segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name))
    app.setFont(QFont('Microsoft YaHei', font_pt))
    settings = QSettings(str(tmp_path / 'isolated.ini'), QSettings.Format.IniFormat)
    i18n = I18n(settings)
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()  # OpenGL is unavailable offscreen.
        window._apply_theme(theme, persist=False)
        state = ready_state()
        state.sensor.accel_mps2 = (0.125, -0.375, 9.807)
        state.sensor.gyro_radps = (0.012, -0.025, 0.001)
        state.sensor.quat = (1.0, 0.0, 0.0, 0.0)
        state.sensor.quat_valid = True
        state.sensor.velocity_mps = (12.345, -6.789, 20.012)
        state.sensor.position_m = (123.456, -234.567, 1200.012)
        state.sensor.revision = 1
        window.bind_runtime_model(state, EventHistory())
        window.render_state()
        window.pages.setCurrentWidget(window.flight_page)
        window.resize(*size)
        window.show()
        if os.environ.get('QT_SCALE_FACTOR'):
            assert abs(window.devicePixelRatioF() - float(os.environ['QT_SCALE_FACTOR'])) < 0.01
        for _ in range(4):
            app.processEvents()
        scroll = window.flight_status_scroll
        chart_top = window.plot_layout.parentWidget().mapTo(window, QPoint()).y()
        viewport_bottom = scroll.viewport().mapTo(window, QPoint()).y() + scroll.viewport().height()
        assert 0 <= chart_top - viewport_bottom <= 12
        cards = [window.lbl_flight_lifecycle.parentWidget(), window.lbl_flight_accel.parentWidget(), window.lbl_mission_state.parentWidget()]
        if scroll.verticalScrollBar().maximum() == 0:
            card_bottom = max(card.mapTo(window, QPoint()).y() + card.height() for card in cards)
            assert 0 <= chart_top - card_bottom <= 12
            assert scroll.height() <= scroll.sizeHint().height() + 2
        else:
            # Content keeps its required wrapped-text height; the viewport scrolls.
            assert scroll.widget().height() >= scroll.widget().heightForWidth(scroll.viewport().width())
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            app.processEvents()
        assert len(window.plot_widgets) == 6
        assert all(plot.width() >= 200 and plot.height() >= 100 for plot in window.plot_widgets.values())
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
        app.setFont(original_font)
