from dataclasses import replace

import numpy as np
import pytest
from config import HORIZONTAL_TRAJECTORY_MAX_POINTS, UI_EVENT_HISTORY_LIMIT
from processing.horizontal_trajectory import HorizontalTrajectory_Build
from protocol.air import AirStatusMessage
from protocol.common import AirStatusId
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from services.mission_trajectory import (
    MissionTrajectoryAppendResult as Result,
)
from services.mission_trajectory import (
    MissionTrajectoryHistory,
)
from services.state_model import MissionPhase
from test_start_ack_state import flight_state, make_controller
from ui.main_window import MainWindow


def _Window_Create(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        I18n(QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    )
    window.render_timer.stop()
    return app, window


def _Frame_Get(index):
    t = index / 5
    return replace(
        flight_state(index * 200),
        pos_m=(100 * np.sin(t / 30), 100 * np.cos(t / 30), t / 2),
    )


def test_controller_350s_5hz_keeps_start_and_early_deploy_after_event_eviction(
    tmp_path,
):
    _app, window = _Window_Create(tmp_path)
    controller = make_controller()
    controller._handle_status_message(
        AirStatusMessage(1, int(AirStatusId.MISSION_START), 0, 0, 0), None
    )
    for index in range(1751):
        controller._handle_flight_state(_Frame_Get(index), None)
        if index == 50:
            controller._handle_status_message(
                AirStatusMessage(2, int(AirStatusId.PARACHUTE_DEPLOY), 10000, 0, 0),
                None,
            )
        elif index > 50:
            controller._handle_status_message(
                AirStatusMessage(
                    index % 256, int(AirStatusId.GNSS_POSITION), index * 200, 1, 0
                ),
                None,
            )
    assert len(controller.events.snapshot()) == UI_EVENT_HISTORY_LIMIT
    assert not any(
        event.status_id == int(AirStatusId.PARACHUTE_DEPLOY)
        for event in controller.events.snapshot()
    )
    times, _positions, _breaks = controller.state.horizontal_trajectory.Snapshot_Get()
    assert len(times) == 1751 and times[0] == 0 and times[-1] == 350
    assert len(controller.state.live_plot.snapshot()[0]) == 51
    assert controller.state.live_plot.snapshot()[0][0] == 340
    window.bind_runtime_model(controller.state, controller.events)
    window._render_plots(controller.state)
    trajectory = window.horizontal_trajectory_widget.trajectory
    np.testing.assert_allclose(trajectory.points_enu[0], _Frame_Get(0).pos_m)
    np.testing.assert_allclose(trajectory.deploy_enu, _Frame_Get(50).pos_m)
    assert not trajectory.start_clipped and trajectory.end_clipped
    assert window.horizontal_trajectory_widget.omitted_samples == 0
    controller._handle_status_message(
        AirStatusMessage(3, int(AirStatusId.LANDING), 350000, 0, 0), None
    )
    controller._handle_flight_state(_Frame_Get(1752), None)
    window._render_plots(controller.state)
    assert not window.horizontal_trajectory_widget.trajectory.end_clipped
    assert window.horizontal_trajectory_widget.trajectory.times_s[-1] == 350
    window.close()


def test_capacity_clips_oldest_without_sampling_and_labels_range(tmp_path):
    _app, window = _Window_Create(tmp_path)
    controller = make_controller()
    history = controller.state.horizontal_trajectory
    for index in range(HORIZONTAL_TRAJECTORY_MAX_POINTS + 7):
        history.Sample_Append(index / 5, (index, index / 2, -index))
    history.Deploy_Observe(0.2)  # No extrapolation back into the clipped-away data.
    window.bind_runtime_model(controller.state, controller.events)
    window._render_plots(controller.state)
    trajectory = window.horizontal_trajectory_widget.trajectory
    assert len(trajectory.times_s) == HORIZONTAL_TRAJECTORY_MAX_POINTS
    assert trajectory.times_s[0] == 7 / 5
    assert (
        history.dropped_sample_count
        == window.horizontal_trajectory_widget.omitted_samples
        == 7
    )
    assert trajectory.start_clipped and trajectory.deploy_enu is None
    assert len(trajectory.edges_enu) == HORIZONTAL_TRAJECTORY_MAX_POINTS - 1
    for language in ("en_US", "zh_CN"):
        window.i18n.set_language(language)
        window.retranslate_ui()
        window.horizontal_trajectory_widget._Draw()
        axis = window.horizontal_trajectory_widget.figure.axes[0]
        assert "7" in axis.get_title()
        assert axis.get_legend().get_texts()[0].get_text() == window.i18n.tr(
            "horizontal.view_start"
        )
    window.close()


def test_invalid_duplicates_and_rejected_old_time_do_not_bridge():
    history = MissionTrajectoryHistory(20)
    assert history.Sample_Append(0, (0, 0, 0)) is Result.ADDED
    assert history.Sample_Append(0.2, (1, 1, 1)) is Result.ADDED
    assert history.Sample_Append(0.1, (99, 99, 99)) is Result.OUT_OF_ORDER
    assert history.Sample_Append(0.4, (2, 2, 2)) is Result.ADDED
    assert history.Sample_Append(0.4, (3, 3, 3)) is Result.ADDED
    assert history.Sample_Append(0.6, (np.nan, 4, 4)) is Result.ADDED
    assert history.Sample_Append(float("nan"), (5, 5, 5)) is Result.INVALID_INPUT
    assert history.Sample_Append(0.8, (5, 5, 5)) is Result.ADDED
    assert history.Sample_Append(10, (6, 6, 6)) is Result.ADDED
    times, positions, breaks = history.Snapshot_Get()
    trajectory = HorizontalTrajectory_Build(
        times, positions, breaks_s=breaks, deploy_time_s=0.3
    )
    assert len(trajectory.edges_enu) == 1
    assert trajectory.deploy_enu is None
    assert history.invalid_sample_count == history.ignored_non_monotonic_samples == 1


@pytest.mark.parametrize("restart", ["reconnect", "controller_restart"])
def test_reconnect_or_session_replacement_has_no_old_positions_or_deploy(
    tmp_path, restart
):
    _app, window = _Window_Create(tmp_path)
    controller = make_controller()
    controller._handle_flight_state(_Frame_Get(0), None)
    controller.state.horizontal_trajectory.Deploy_Observe(0)
    window.bind_runtime_model(controller.state, controller.events)
    window._render_plots(controller.state)
    previous = controller.state.horizontal_trajectory
    controller.window = window
    controller._state_generation = controller.state.session_generation
    if restart == "reconnect":
        controller._replace_state(connected=True, connection_text="reconnected")
    else:
        controller.FlightSession_Restart("TEST_NEW_CONTROLLER_SESSION")
    window.bind_runtime_model(controller.state, controller.events)
    window._render_plots(controller.state)
    assert controller.state.horizontal_trajectory is not previous
    assert controller.state.horizontal_trajectory.Snapshot_Get()[0] == []
    assert controller.state.horizontal_trajectory.deploy_time_s is None
    assert len(window.horizontal_trajectory_widget.trajectory.points_enu) == 0
    controller._handle_flight_state(_Frame_Get(1), None)
    window._render_plots(controller.state)
    assert len(window.horizontal_trajectory_widget.trajectory.points_enu) == 1
    assert window.horizontal_trajectory_widget.trajectory.deploy_enu is None
    window.close()


def test_new_mission_after_landing_clears_history_but_late_or_duplicate_start_does_not():
    controller = make_controller()
    controller._handle_flight_state(_Frame_Get(5), None)
    history = controller.state.horizontal_trajectory
    for _ in range(2):
        controller._handle_status_message(
            AirStatusMessage(1, int(AirStatusId.MISSION_START), 0, 0, 0), None
        )
    assert history.Snapshot_Get()[0] == [1]
    history.Deploy_Observe(1)
    controller._handle_status_message(
        AirStatusMessage(2, int(AirStatusId.LANDING), 2000, 0, 0), None
    )
    controller._handle_status_message(
        AirStatusMessage(3, int(AirStatusId.MISSION_START), 0, 0, 0), None
    )
    assert history.Snapshot_Get()[0] == [] and history.deploy_time_s is None
    assert controller.state.mission_presentation.phase is MissionPhase.MISSION_ACTIVE
    controller._handle_flight_state(_Frame_Get(0), None)
    assert history.Snapshot_Get()[0] == [0]


def test_hidden_stream_is_not_painted_and_visible_updates_are_coalesced(tmp_path):
    app, window = _Window_Create(tmp_path)
    widget = window.horizontal_trajectory_widget
    trajectory = HorizontalTrajectory_Build([0, 0.2], [(0, 0, 0), (1, 1, 1)])
    for _ in range(10):
        widget.Trajectory_Set(trajectory)
    assert not widget.redraw_timer.isActive()
    window.show()
    window.pages.setCurrentWidget(widget)
    app.processEvents()
    for _ in range(20):
        widget.Trajectory_Set(trajectory)
    assert widget.redraw_timer.isActive() and widget.redraw_timer.interval() == 500
    assert widget.redraw_timer.isSingleShot()
    window.close()
