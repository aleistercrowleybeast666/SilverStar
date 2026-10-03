import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from processing.flight_plotter import FlightPlotter, PlotterConfig
from processing.horizontal_trajectory import HorizontalTrajectory_Build
from services.i18n import I18n, Language
from services.state_model import FlightControllerState, EventHistory, FlightEvent
from protocol.common import AirStatusId
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


def test_gshc_live_tab_does_not_replace_six_plots_and_event_only_refresh(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(I18n(settings))
    state, events = FlightControllerState(), EventHistory()
    state.mission_first_time_ms = 1000
    window.bind_runtime_model(state, events)
    for t in np.arange(0, 1.01, .2):
        state.live_plot.append(t, (0, 0, 0), (t*10, t*20, t*30))
        state.horizontal_trajectory.Sample_Append(1 + t, (t*10, t*20, t*30))
    window._render_plots(state)
    assert len(window.plot_widgets) == 6
    assert window.horizontal_trajectory_widget.trajectory.deploy_enu is None
    events.append(FlightEvent(1, int(AirStatusId.PARACHUTE_DEPLOY), "PARACHUTE_DEPLOY", 1500, 0, 0, 0))
    state.horizontal_trajectory.Deploy_Observe(1.5)
    window._render_plots(state)
    np.testing.assert_allclose(window.horizontal_trajectory_widget.trajectory.deploy_enu, [5, 10, 15])
    assert window.horizontal_trajectory_widget.trajectory.end_clipped
    # Rebinding a new mission with equal revision counters must replace old
    # geometry and markers, even when the old widget is currently hidden.
    replacement, replacement_events = FlightControllerState(), EventHistory()
    for t in np.arange(0, 1.01, .2):
        replacement.live_plot.append(t, (0, 0, 0), (-t*10, -t*20, -t*30))
        replacement.horizontal_trajectory.Sample_Append(t, (-t*10, -t*20, -t*30))
    replacement_events.append(FlightEvent(1, 0, "OTHER", 1500, 0, 0, 0))
    window.bind_runtime_model(replacement, replacement_events)
    window._render_plots(replacement)
    np.testing.assert_allclose(window.horizontal_trajectory_widget.trajectory.points_enu[-1],
                               [-10, -20, -30])
    assert window.horizontal_trajectory_widget.trajectory.deploy_enu is None
    window.close()
