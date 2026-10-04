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
    trajectory = _Trajectory_FromState(controller.state)
    np.testing.assert_allclose(trajectory.points_enu[0], _Frame_Get(0).pos_m)
    np.testing.assert_allclose(trajectory.deploy_enu, _Frame_Get(50).pos_m)
    assert not trajectory.start_clipped and trajectory.end_clipped
    assert controller.state.horizontal_trajectory.dropped_sample_count == 0
    controller._handle_status_message(
        AirStatusMessage(3, int(AirStatusId.LANDING), 350000, 0, 0), None
    )
    controller._handle_flight_state(_Frame_Get(1752), None)
    window._render_plots(controller.state)
    assert controller.state.mission_presentation.phase is MissionPhase.LANDED
    assert not _Trajectory_FromState(controller.state).end_clipped
    assert _Trajectory_FromState(controller.state).times_s[-1] == 350
    window.close()


def test_capacity_clips_oldest_without_sampling(tmp_path):
    _app, window = _Window_Create(tmp_path)
    controller = make_controller()
    history = controller.state.horizontal_trajectory
    for index in range(HORIZONTAL_TRAJECTORY_MAX_POINTS + 7):
        history.Sample_Append(index / 5, (index, index / 2, -index))
    history.Deploy_Observe(0.2)  # No extrapolation back into the clipped-away data.
    window.bind_runtime_model(controller.state, controller.events)
    window._render_plots(controller.state)
    trajectory = _Trajectory_FromState(controller.state)
    assert len(trajectory.times_s) == HORIZONTAL_TRAJECTORY_MAX_POINTS
    assert trajectory.times_s[0] == 7 / 5
    assert history.dropped_sample_count == 7
    assert trajectory.start_clipped and trajectory.deploy_enu is None
    assert len(trajectory.edges_enu) == HORIZONTAL_TRAJECTORY_MAX_POINTS - 1
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
    assert len(_Trajectory_FromState(controller.state).points_enu) == 0
    assert controller.state.horizontal_trajectory.deploy_time_s is None
    assert controller.state.horizontal_trajectory.Snapshot_Get()[0] == []
    controller._handle_flight_state(_Frame_Get(1), None)
    window._render_plots(controller.state)
    assert len(_Trajectory_FromState(controller.state).points_enu) == 1
    assert controller.state.horizontal_trajectory.deploy_time_s is None
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


def _Trajectory_FromState(state):
    history = state.horizontal_trajectory
    times, positions, breaks = history.Snapshot_Get()
    landing_time = state.mission_presentation.last_critical_event_time_ms
    view_range = (
        (0, landing_time / 1000.0)
        if state.mission_presentation.phase is MissionPhase.LANDED
        and landing_time is not None
        else None
    )
    trajectory = HorizontalTrajectory_Build(
        times, positions, breaks_s=breaks, time_range=view_range,
        deploy_time_s=history.deploy_time_s,
    )
    return replace(
        trajectory,
        start_clipped=history.dropped_sample_count > 0,
        end_clipped=state.mission_presentation.phase is not MissionPhase.LANDED,
    )
