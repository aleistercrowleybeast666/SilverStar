from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.visual_semantics import (
    TRAJECTORY_DEPLOY_COLOR,
    TRAJECTORY_LANDING_COLOR,
    TRAJECTORY_POST_DEPLOY_COLOR,
    TRAJECTORY_PRE_DEPLOY_COLOR,
    RocketFaceColors_Get,
    TrajectoryEventMesh_Get,
    TrajectoryMarkerWorldSizes_Get,
    TrajectoryPhaseColor_Get,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.ui.pages.charts import (
    FlightPage,
    _RocketFaceColors_Get,
    _TrajectoryOrigin_Get,
)
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.sslog_synthetic import START_TIMESTAMP_US, AnalysisFlight_Build


def test_trajectory_marker_sizes_are_world_scaled_and_phase_color_changes() -> None:
    small = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.5, 0.25)))
    large = small * 500.0
    small_sizes = np.asarray(TrajectoryMarkerWorldSizes_Get(small))
    large_sizes = np.asarray(TrajectoryMarkerWorldSizes_Get(large))
    assert np.allclose(large_sizes, small_sizes * 500.0)
    assert np.isclose(small_sizes[0], 0.035)
    assert np.isclose(small_sizes[2], 0.030)
    assert np.isclose(small_sizes[1], 0.010)
    assert small_sizes[0] > small_sizes[1]
    vertices, faces = TrajectoryEventMesh_Get(np.asarray((4.0, 5.0, 6.0)), 0.14)
    assert vertices.shape == (6, 3)
    assert faces.shape == (8, 3)
    assert np.allclose(np.ptp(vertices, axis=0), 0.14)
    assert np.allclose(np.mean(vertices, axis=0), (4.0, 5.0, 6.0))
    assert TrajectoryPhaseColor_Get(99, 100) == TRAJECTORY_PRE_DEPLOY_COLOR
    assert TrajectoryPhaseColor_Get(100, 100) == TRAJECTORY_POST_DEPLOY_COLOR


def test_flight_tabs_start_crop_complete_vectors_and_active_source(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_flight_page.BIN")
    )
    result = PureInsAlgorithmPlugin().run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
    store = ReplayResultStore()
    entry = store.Result_Add(result, algorithm_name="Pure INS")
    assert store.ActiveSource_Set(entry.source_id)
    resolver = ChannelResolver(dataset, store)

    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    page.show()
    application.processEvents()

    assert page.tabs.count() == 6
    assert page._start_timestamp_us == START_TIMESTAMP_US
    assert page._position is result.channels["navigation.position_enu"]
    assert page._attitude is result.channels["attitude.q_nb"]
    assert not hasattr(page, "source_combo")
    assert "Pure INS" in page.source_value_label.text()
    assert len(page.velocity_plot.listDataItems()) == 6
    assert len(page.position_plot.listDataItems()) == 6
    assert len(page.acceleration_plot.listDataItems()) == 3
    assert len(page.angular_rate_plot.listDataItems()) == 3
    # This fixture has no recorded attitude channel to compare.
    assert len(page.quaternion_plot.listDataItems()) == 4
    assert len(page.euler_plot.listDataItems()) == 3
    assert page._deploy_timestamp_us == START_TIMESTAMP_US + 110_000
    assert page._end_timestamp_us == START_TIMESTAMP_US + 160_100
    assert page.playback_slider.parent() is not None
    assert page.reset_charts_button.text() == "Reset Charts"
    page.velocity_plot.setXRange(200.0, 201.0, padding=0)
    page.velocity_plot.setYRange(200.0, 201.0, padding=0)
    velocity_legend = page.velocity_plot.getPlotItem().legend
    velocity_legend.setPos(180.0, 140.0)
    assert not all(page.velocity_plot.getViewBox().state["autoRange"])
    page.reset_charts_button.click()
    assert all(page.velocity_plot.getViewBox().state["autoRange"])
    assert np.allclose(
        (velocity_legend.pos().x(), velocity_legend.pos().y()),
        (30.0, 30.0),
    )
    velocity_names = {item.name() for item in page.velocity_plot.listDataItems() if item.name()}
    assert sum("Recorded" in name for name in velocity_names) == 3
    assert sum("Pure INS" in name for name in velocity_names) >= 3
    styles = [item.opts["pen"].style() for item in page.velocity_plot.listDataItems()]
    assert styles[:3] == [Qt.PenStyle.DashLine] * 3
    assert styles[3:] == [Qt.PenStyle.SolidLine] * 3
    assert np.allclose(
        page._trajectory_origin,
        _TrajectoryOrigin_Get(page._position, START_TIMESTAMP_US),
    )

    if hasattr(page, "pre_deploy_line"):
        bounds_count = resolver.TrajectoryBoundsCalculationCount_Get(entry.source_id)
        fit_count = page._trajectory_camera_fit_count
        page.trajectory_view.opts["distance"] = 123.0
        page.playback_slider.setValue(2500)
        application.processEvents()
        assert np.allclose(
            page.current_marker.color,
            QColor(TRAJECTORY_PRE_DEPLOY_COLOR).getRgbF(),
        )
        assert page.current_marker.pxMode is False
        assert page.deploy_marker.__class__.__name__ == "GLMeshItem"
        assert page.landing_marker.__class__.__name__ == "GLMeshItem"
        assert not page.landing_marker.visible()
        assert page.current_marker.pos.shape[0] == 1
        assert not hasattr(page, "deploy_marker_outline")
    page.playback_slider.setValue(10000)
    application.processEvents()
    if hasattr(page, "pre_deploy_line"):
        assert page.trajectory_view.opts["distance"] == 123.0
        assert page._trajectory_camera_fit_count == fit_count
        assert resolver.TrajectoryBoundsCalculationCount_Get(entry.source_id) == bounds_count
        assert page.pre_deploy_line.pos.shape[0] > 0
        assert page.post_deploy_line.pos.shape[0] > 0
        assert np.allclose(page.pre_deploy_line.pos[0], np.zeros(3), atol=1.0e-5)
        assert page.landing_marker.visible()
        assert page.current_marker.pos.shape[0] == 0
        assert page.rocket_mesh is not None
        assert not hasattr(page, "start_marker")
        assert len(page._trajectory_text_items) == 3
        expected_light_faces = np.asarray(
            [QColor(color).getRgbF() for color in RocketFaceColors_Get("light")],
            dtype=np.float32,
        )
        assert np.allclose(_RocketFaceColors_Get("light"), expected_light_faces)
        assert page._deploy_marker_vertices.shape == (6, 3)
        assert page._landing_marker_vertices.shape == (6, 3)
        assert page._trajectory_bounds is not None
        expected_sizes = TrajectoryMarkerWorldSizes_Get(
            np.asarray(
                (
                    page._trajectory_bounds.min_enu,
                    page._trajectory_bounds.max_enu,
                )
            )
        )
        assert np.allclose(page._trajectory_marker_sizes, expected_sizes)
        assert np.allclose(
            np.ptp(page._deploy_marker_vertices, axis=0),
            expected_sizes[0],
        )
        assert np.isclose(page.current_marker.size, expected_sizes[1])
        deploy_face_colors = page.deploy_marker.opts["meshdata"].faceColors()
        assert np.allclose(
            deploy_face_colors,
            np.tile(
                QColor(TRAJECTORY_DEPLOY_COLOR).getRgbF(),
                (deploy_face_colors.shape[0], 1),
            ),
        )
        assert np.allclose(deploy_face_colors[:, 3], 1.0)
        landing_face_colors = page.landing_marker.opts["meshdata"].faceColors()
        assert np.allclose(
            landing_face_colors,
            np.tile(
                QColor(TRAJECTORY_LANDING_COLOR).getRgbF(),
                (landing_face_colors.shape[0], 1),
            ),
        )
        assert np.allclose(landing_face_colors[:, 3], 1.0)
        assert page.deploy_marker.depthValue() > page.current_marker.depthValue()
        assert page.landing_marker.depthValue() > page.current_marker.depthValue()
        page.Theme_Apply("dark")
        expected_background = (17 / 255, 24 / 255, 39 / 255)
        assert np.allclose(
            page.attitude_view.opts["bgcolor"][:3],
            expected_background,
        )
        assert np.allclose(
            page.trajectory_view.opts["bgcolor"][:3],
            expected_background,
        )
        assert np.allclose(
            page.deploy_marker.opts["meshdata"].faceColors()[:, 3],
            1.0,
        )
        assert np.allclose(
            page.landing_marker.opts["meshdata"].faceColors()[:, 3],
            1.0,
        )
    page.close()


def test_recorded_recomputed_and_what_if_share_landing_marker_lifecycle(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_marker_sources.BIN")
    )
    plugin = PureInsAlgorithmPlugin()
    recomputed = plugin.run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.OFFLINE,
        ),
    )
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
            continue
        page.playback_slider.setValue(8000)
        application.processEvents()
        assert page.current_marker.pos.shape[0] == 1
        assert not page.landing_marker.visible()
        page.playback_slider.setValue(10000)
        application.processEvents()
        assert page.current_marker.pos.shape[0] == 0
        assert page.landing_marker.visible()
        assert page._landing_marker_vertices.shape == (6, 3)
    page.close()


def test_no_landing_trajectory_uses_source_end_and_keeps_current_visible(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_no_landing_3d.BIN",
            include_landing_event=False,
            update_count=10,
        )
    )
    resolver = ChannelResolver(dataset, ReplayResultStore())
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    page.show()
    application.processEvents()

    assert page._end_timestamp_us == START_TIMESTAMP_US + 200_000
    assert page._trajectory_bounds is not None
    assert page._trajectory_bounds.sample_count == 10
    if hasattr(page, "landing_marker"):
        page.playback_slider.setValue(10000)
        application.processEvents()
        assert page.current_marker.pos.shape[0] == 1
        assert not page.landing_marker.visible()
        assert page.pre_deploy_line.pos.shape[0] > 0
        assert page.post_deploy_line.pos.shape[0] > 0
    page.close()


def test_flight_plots_stop_at_landing_while_raw_series_remains_complete(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_plot_mission_end.BIN",
            update_count=10,
            landing_after_update_count=6,
        )
    )
    raw = dataset.Series_Get("imu.corrected.accel_b")
    assert raw is not None
    raw_end = int(raw.timestamp_us[-1])
    landing = START_TIMESTAMP_US + 120_100
    assert raw_end > landing
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, ChannelResolver(dataset, ReplayResultStore()))
    application.processEvents()

    for plot in (
        page.velocity_plot,
        page.position_plot,
        page.acceleration_plot,
        page.angular_rate_plot,
        page.quaternion_plot,
        page.euler_plot,
    ):
        for item in plot.listDataItems():
            assert item.xData is not None
            assert float(np.nanmax(item.xData)) <= (landing - START_TIMESTAMP_US) * 1.0e-6
    assert int(raw.timestamp_us[-1]) == raw_end
    page.close()


def test_state_estimation_shows_recorded_kf6_diagnostics_and_i18n(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_state_page.BIN")
    )
    from tests.parameter_fixtures import SyntheticParameters_Attach
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "parameters")
    resolver = ChannelResolver(dataset, ReplayResultStore())
    page = StateEstimationPage(Translator("en_US"))
    page.Dataset_Set(dataset, resolver)
    page.show()
    application.processEvents()

    assert page.tabs.count() == 6
    assert not hasattr(page, "source_combo")
    assert "Recorded" in page.source_value_label.text()
    assert page.state_group_combo.count() == 2
    assert page.innovation_measurement_combo.count() == 5
    assert page.nis_measurement_combo.count() == 5
    assert page.measurement_group_combo.count() == 5
    assert len(page.covariance_plot.listDataItems()) == 3
    assert len(page.innovation_plot.listDataItems()) == 0
    assert len(page.nis_plot.listDataItems()) == 0
    assert len(page.measurement_uncertainty_plot.listDataItems()) == 0
    assert len(page.measurement_age_plot.listDataItems()) == 0
    assert "Unavailable" in page.measurement_unavailable_label.text()
    assert page.nis_summary.rowCount() == 4
    assert page.gnss_integrity.display_combo.count() == 3
    assert page.reset_charts_button.text() == "Reset Charts"
    page.nis_plot.setXRange(200.0, 201.0, padding=0)
    page.nis_plot.setYRange(200.0, 201.0, padding=0)
    page.reset_charts_button.click()
    assert all(page.nis_plot.getViewBox().state["autoRange"])

    page.Language_Apply(Translator("zh_CN"))
    application.processEvents()
    assert page.reset_charts_button.text() == "复位图表"
    assert page.tabs.tabText(3) == "量测"
    assert page.tabs.tabText(2) == "归一化新息平方（NIS）"
    assert page.nis_summary.horizontalHeaderItem(0).text() == "量测"
    page.close()


def test_trajectory_hides_deploy_point_when_no_deploy_event(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = Sslog0ParserPlugin().parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_no_deploy_marker.BIN",
            include_deploy_detail=False,
            include_deploy_event=False,
        )
    )
    page = FlightPage(Translator("en_US"))
    page.Dataset_Set(dataset, ChannelResolver(dataset, ReplayResultStore()))
    page.playback_slider.setValue(10000)
    application.processEvents()
    assert page._deploy_timestamp_us is None
    if hasattr(page, "deploy_marker"):
        assert page._deploy_marker_vertices.shape[0] == 0
    page.close()
