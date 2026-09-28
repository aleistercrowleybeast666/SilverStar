from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.mission import MissionReplayBounds_Get, MissionReplayEndReason
from silverstar_flp.core.trajectory import (
    TrajectoryCameraDistance_Get,
    TrajectoryPosition_NearEvent,
)
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import (
    InertialIncrement_BuildFromCorrectedImu,
    Mechanization_ConfigurationGet,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.charts import FlightPage


def test_ss0007_real_log_landing_horizon_and_bounds() -> None:
    path_text = os.environ.get("SILVERSTAR_SS0007_PATH")
    if not path_text:
        pytest.skip("set SILVERSTAR_SS0007_PATH for the real-log validation gate")
    path = Path(path_text)
    if not path.is_file():
        pytest.skip(f"real-log validation file is unavailable: {path}")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    dataset = Sslog0ParserPlugin().parse(path)
    start = dataset.start_timestamp_us
    assert start is not None
    landing = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if int(record.payload.get("event_id", -1)) == 0x2A
    )
    assert landing == pytest.approx(156_965_000, abs=1_000)

    pure_recorded = dataset.Series_Get("pure_ins.recorded.navigation.position_enu")
    kf6_recorded = dataset.Series_Get("kf6.recorded.navigation.position_enu")
    raw_imu = dataset.Series_Get("imu.corrected.accel_b")
    assert pure_recorded is not None
    assert kf6_recorded is not None
    assert raw_imu is not None
    assert 0 < landing - int(pure_recorded.timestamp_us[-1]) <= 100_000
    assert 0 < landing - int(kf6_recorded.timestamp_us[-1]) <= 100_000
    assert TrajectoryPosition_NearEvent(pure_recorded, landing) is not None
    assert TrajectoryPosition_NearEvent(kf6_recorded, landing) is not None
    assert int(raw_imu.timestamp_us[-1]) > landing

    mission = MissionReplayBounds_Get(dataset)
    assert mission.end_reason == MissionReplayEndReason.LANDING
    assert mission.end_timestamp_us == landing
    config = Mechanization_ConfigurationGet(dataset)
    unbounded_increments, _ = InertialIncrement_BuildFromCorrectedImu(
        dataset.Records_Get("IMU_CORRECTED"),
        start_timestamp_us=start,
        minimum_sample_rate_hz=config["minimum_sample_rate_hz"],
        maximum_sample_rate_hz=config["maximum_sample_rate_hz"],
    )
    assert unbounded_increments[-1].interval_end_timestamp_us > landing

    for plugin in (PureInsAlgorithmPlugin(), Kf6AlgorithmPlugin()):
        result = plugin.run(dataset, ReplayRequest())
        position = result.channels["navigation.position_enu"]
        assert int(position.timestamp_us[-1]) <= landing
        assert landing - int(position.timestamp_us[-1]) <= 100_000
        assert result.diagnostics["mission_end_timestamp_us"] == landing
        assert result.diagnostics["mission_end_reason"] == "landing"

    resolver = ChannelResolver(dataset, ReplayResultStore())
    bounds = resolver.TrajectoryBounds_Get()
    assert bounds is not None
    assert bounds.sample_count == kf6_recorded.count
    assert resolver.TrajectoryBoundsCalculationCount_Get() == 1
    distance = TrajectoryCameraDistance_Get(
        bounds,
        horizontal_fov_deg=60.0,
        aspect_ratio=16.0 / 9.0,
    )
    assert distance > bounds.bounding_radius
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_ss0007_real_log_recorded_recomputed_and_what_if_marker_lifecycle() -> None:
    path_text = os.environ.get("SILVERSTAR_SS0007_PATH")
    if not path_text:
        pytest.skip("set SILVERSTAR_SS0007_PATH for the real-log validation gate")
    path = Path(path_text)
    if not path.is_file():
        pytest.skip(f"real-log validation file is unavailable: {path}")
    dataset = Sslog0ParserPlugin().parse(path)
    plugin = PureInsAlgorithmPlugin()
    recomputed = plugin.run(dataset, ReplayRequest())
    what_if = plugin.run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF,
            parameters={"gravity_mps2": 9.7},
        ),
    )
    store = ReplayResultStore()
    recomputed_entry = store.Result_Add(recomputed, algorithm_name="Pure INS")
    what_if_entry = store.Result_Add(what_if, algorithm_name="Pure INS")
    resolver = ChannelResolver(dataset, store)
    application = QApplication.instance() or QApplication([])
    page = FlightPage(Translator("en_US"))

    for source_id in (
        ReplayResultStore.RECORDED_SOURCE_ID,
        recomputed_entry.source_id,
        what_if_entry.source_id,
    ):
        assert store.ActiveSource_Set(source_id)
        page.Dataset_Set(dataset, resolver)
        page.show()
        application.processEvents()
        if not hasattr(page, "landing_marker"):
            pytest.skip("OpenGL trajectory widgets are unavailable")
        calculation_count = resolver.TrajectoryBoundsCalculationCount_Get(source_id)
        fit_count = page._trajectory_camera_fit_count
        assert page._end_timestamp_us == 156_965_267
        page.playback_slider.setValue(9900)
        application.processEvents()
        assert page.current_marker.pos.shape[0] == 1
        assert not page.landing_marker.visible()
        page.playback_slider.setValue(10000)
        application.processEvents()
        assert page.current_marker.pos.shape[0] == 0
        assert page.landing_marker.visible()
        assert page._landing_marker_vertices.shape == (6, 3)
        assert resolver.TrajectoryBoundsCalculationCount_Get(source_id) == calculation_count
        assert page._trajectory_camera_fit_count == fit_count
    page.close()


def test_ss0007_real_log_gui_worker_exports_gif_manifest_and_metadata_plots(
    tmp_path: Path,
) -> None:
    path_text = os.environ.get("SILVERSTAR_SS0007_PATH")
    if not path_text:
        pytest.skip("set SILVERSTAR_SS0007_PATH for the real-log validation gate")
    path = Path(path_text)
    if not path.is_file():
        pytest.skip(f"real-log validation file is unavailable: {path}")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    dataset = Sslog0ParserPlugin().parse(path)
    application = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    window._Dataset_Set(dataset)
    dialog = window.export_dialog
    output = tmp_path / "SS0007_GUI_Worker_Export"
    dialog.folder_edit.setText(str(output))
    for checkbox in dialog._checks:
        checkbox.setChecked(False)
    dialog.full_p_check.setChecked(True)
    dialog.plots_check.setChecked(True)
    dialog.trajectory_check.setChecked(True)
    dialog.gif_check.setChecked(True)

    dialog._Export_Request()
    worker = window._active_worker
    assert worker is not None
    errors: list[tuple[str, str]] = []
    worker.signals.error.connect(
        lambda message, traceback_text: errors.append(
            (message, traceback_text)
        )
    )
    loop = QEventLoop()
    worker.signals.finished.connect(loop.quit)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(180_000)
    loop.exec()
    timed_out = not timeout.isActive()
    timeout.stop()
    application.processEvents()

    fallback = output / "Export_Failures_ZH.txt"
    fallback_text = (
        fallback.read_text(encoding="utf-8")
        if fallback.is_file()
        else ""
    )
    assert not timed_out
    assert not errors
    assert window._active_worker is None
    assert (output / "Flight_Replay_ZH.gif").is_file(), fallback_text
    assert (output / "Export_Manifest_ZH.json").is_file(), fallback_text
    assert not fallback.exists(), fallback_text
    expected_plots = (
        "KF6_Recorded_Position_Std_1Sigma_ZH.png",
        "KF6_Recorded_Velocity_Std_1Sigma_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Position_ZH.png",
        "KF6_Recorded_Innovation_GNSS_Velocity_ZH.png",
        "KF6_Recorded_NIS_GNSS_Position_ZH.png",
        "KF6_Recorded_NIS_GNSS_Velocity_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Position_ZH.png",
        "KF6_Recorded_Measurement_Std_GNSS_Velocity_ZH.png",
    )
    for name in expected_plots:
        assert (output / "Plots_ZH" / name).is_file()
    full_p = output / "KF6_Full_P_Keyframes_ZH.txt"
    assert full_p.is_file()
    assert "INITIAL_STATE.p0_diagonal" in full_p.read_text(encoding="utf-8")
    manifest = dialog._result_manifest
    assert manifest is not None
    assert not manifest.failures
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    window.close()
