"""The unscrolled flight summary leaves the rest of the page for six plots."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from services.preferences import Theme
from ui.main_window import MainWindow


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
@pytest.mark.parametrize("theme", [Theme.LIGHT, Theme.DARK])
@pytest.mark.parametrize("size,font_pt", [((1536, 816), 9), ((1280, 720), 9)])
def test_original_flight_summary_and_six_plots(tmp_path, language, theme, size, font_pt):
    app = QApplication.instance() or QApplication([])
    original_font = app.font()
    app.setFont(QFont("Microsoft YaHei", font_pt))
    i18n = I18n(QSettings(str(tmp_path / "isolated.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window._apply_theme(theme, persist=False)
        window.resize(*size)
        window.show()
        window.pages.setCurrentWidget(window.flight_page)
        app.processEvents()
        assert not hasattr(window, "flight_status_scroll")
        card_bottom = max(card.mapTo(window, QPoint()).y() + card.height() for card in (
            window.lbl_flight_lifecycle.parentWidget(), window.lbl_flight_accel.parentWidget(),
            window.lbl_mission_state.parentWidget()
        ))
        chart_top = window.plot_layout.parentWidget().mapTo(window, QPoint()).y()
        assert 0 <= chart_top - card_bottom <= 36
        assert len(window.plot_widgets) == 6
        expected_height = 160 if size[1] == 720 else 190
        assert all(plot.width() >= 240 and plot.height() >= expected_height
                   for plot in window.plot_widgets.values())
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
        app.setFont(original_font)
