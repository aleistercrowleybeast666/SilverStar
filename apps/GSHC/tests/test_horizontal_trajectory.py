from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from processing.flight_plotter import FlightPlotter, PlotterConfig
from services.i18n import I18n, Language
from services.state_model import FlightControllerState, EventHistory
from ui.main_window import MainWindow
from tests.test_time_exports import Data_Build


def test_gshc_export_keeps_east_limits_instead_of_time_range(tmp_path, monkeypatch):
    data = Data_Build(1)
    for sample in data.pos:
        sample.values = (100 + sample.time_s * 200, 50 + sample.time_s * 200, -20)
    plotter = FlightPlotter(PlotterConfig(language=Language.EN_US))
    plotter.page_range = (.2, .8)
    seen = []
    from processing import flight_plotter
    draw = flight_plotter.HorizontalTrajectory_Draw

    def capture(figure, trajectory, labels, **kwargs):
        axis = draw(figure, trajectory, labels, **kwargs)
        seen.append((axis.get_xlim(), trajectory))
        return axis

    monkeypatch.setattr(flight_plotter, "HorizontalTrajectory_Draw", capture)
    path = tmp_path / "horizontal_EN.png"
    plotter.plot_horizontal_trajectory(path, data)
    assert path.stat().st_size > 10000
    assert seen[0][0][0] > 100  # metre coordinates, not .2–.8 seconds
    assert seen[0][1].start_clipped and seen[0][1].end_clipped


def test_gshc_keeps_export_only_trajectory_and_six_live_plots(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(I18n(settings))
    try:
        window.render_timer.stop()
        window.bind_runtime_model(FlightControllerState(), EventHistory())
        assert [window.pages.widget(index) for index in range(window.pages.count())] == [
            window.preflight_page, window.flight_page, window.post_process_page,
            window.maintenance_scroll,
        ]
        assert window.maintenance_scroll.widget() is window.maintenance_page
        assert not hasattr(window, "horizontal_trajectory_widget")
        assert len(window.plot_widgets) == 6
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
