from __future__ import annotations

import inspect
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import (
    AlgorithmAvailability,
    AlgorithmMetadata,
    AlgorithmPlugin,
    AlgorithmResult,
    EstimatorVisualizationSpec,
    FullCovarianceSpec,
    MeasurementGroupSpec,
    ReplayFidelity,
    ReplayRequest,
    StateGroupSpec,
)
from silverstar_flp.plugins.registry import PluginRegistry
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.sslog_synthetic import START_TIMESTAMP_US, AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse, _PlotBaseName_Get


def _Series(
    timestamps: np.ndarray,
    values: np.ndarray,
    *,
    columns: tuple[str, ...] = (),
    unit: str = "1",
    quantity: str = "diagnostic",
) -> TimeSeries:
    return TimeSeries(
        timestamp_us=timestamps,
        values=np.asarray(values, dtype=np.float64),
        unit=unit,
        quantity=quantity,
        source="test.algorithm.fake_eskf",
        valid=np.ones(timestamps.size, dtype=np.bool_),
        columns=columns,
        metadata={"provenance": "Recomputed"},
    )


_FAKE_STATE_GROUPS = (
    StateGroupSpec(
        "position_error",
        "state.position_error",
        ("E", "N", "U"),
        "m",
        "fake.covariance.diagonal",
        (0, 1, 2),
    ),
    StateGroupSpec(
        "velocity_error",
        "state.velocity_error",
        ("E", "N", "U"),
        "m/s",
        "fake.covariance.diagonal",
        (3, 4, 5),
    ),
    StateGroupSpec(
        "attitude_error",
        "state.attitude_error",
        ("X", "Y", "Z"),
        "rad",
        "fake.covariance.diagonal",
        (6, 7, 8),
    ),
    StateGroupSpec(
        "gyro_bias",
        "state.gyro_bias",
        ("X", "Y", "Z"),
        "rad/s",
        "fake.covariance.diagonal",
        (9, 10, 11),
    ),
    StateGroupSpec(
        "accel_bias",
        "state.accel_bias",
        ("X", "Y", "Z"),
        "m/s²",
        "fake.covariance.diagonal",
        (12, 13, 14),
    ),
)

_FAKE_STATE_SYMBOLS = (
    "δpE",
    "δpN",
    "δpU",
    "δvE",
    "δvN",
    "δvU",
    "δθX",
    "δθY",
    "δθZ",
    "δbgX",
    "δbgY",
    "δbgZ",
    "δbaX",
    "δbaY",
    "δbaZ",
)
_FAKE_STATE_UNITS = (
    "m",
    "m",
    "m",
    "m/s",
    "m/s",
    "m/s",
    "rad",
    "rad",
    "rad",
    "rad/s",
    "rad/s",
    "rad/s",
    "m/s²",
    "m/s²",
    "m/s²",
)


def _Measurement(
    group_id: str,
    label_key: str,
    index: int,
    dimension: int,
    unit: str,
    file_stem: str,
    *,
    configuration_fields: tuple[str, ...] = (),
) -> MeasurementGroupSpec:
    components = (
        ("X", "Y", "Z")
        if group_id == "star_tracker_attitude"
        else ("E", "N", "U")
        if dimension == 3
        else ("U",)
    )
    return MeasurementGroupSpec(
        group_id,
        label_key,
        dimension,
        components,
        f"fake.innovation.{group_id}",
        f"fake.nis.{group_id}",
        "fake.update_result",
        "fake.r_scale",
        measurement_age_channel=f"fake.age.{group_id}",
        effective_r_channel=f"fake.measurement_r.{group_id}",
        update_result_index=index,
        r_scale_index=index,
        attempt_mask_channel="fake.measurement_attempt_mask",
        attempt_mask_bit=1 << index,
        unit=unit,
        file_stem=file_stem,
        configuration_fields=configuration_fields,
    )


class _FakeEskfPlugin(AlgorithmPlugin):
    metadata = AlgorithmMetadata(
        plugin_id="test.algorithm.fake_eskf",
        version="test",
        display_name="Fake ESKF",
        description="test-only metadata compatibility estimator",
        required_records=(),
        optional_records=(),
        required_channels=(),
        optional_channels=(),
        parameter_schema=(),
        standard_outputs=(
            "attitude.q_nb",
            "navigation.velocity_enu",
            "navigation.position_enu",
        ),
        diagnostic_outputs=(
            "fake.covariance.diagonal",
            "fake.covariance.upper_triangle",
        ),
        estimator_visualization=EstimatorVisualizationSpec(
            state_groups=_FAKE_STATE_GROUPS,
            measurement_groups=(
                _Measurement(
                    "gnss_position",
                    "measurement.gnss_position",
                    0,
                    3,
                    "m",
                    "GNSS_Position",
                    configuration_fields=("configured_gnss_rate_hz",),
                ),
                _Measurement(
                    "barometric_altitude",
                    "measurement.barometric_altitude",
                    1,
                    1,
                    "m",
                    "Barometer",
                    configuration_fields=("configured_barometer_rate_hz",),
                ),
                _Measurement(
                    "magnetometer",
                    "measurement.magnetometer",
                    2,
                    3,
                    "uT",
                    "Magnetometer",
                    configuration_fields=(
                        "configured_magnetometer_rate_hz",
                    ),
                ),
                _Measurement(
                    "star_tracker_attitude",
                    "measurement.star_tracker_attitude",
                    3,
                    3,
                    "rad",
                    "Star_Tracker_Attitude",
                ),
            ),
            full_covariance=FullCovarianceSpec(
                channel_id="fake.covariance.upper_triangle",
                file_stem="Fake_ESKF_Full_P_Keyframes",
                state_symbols=_FAKE_STATE_SYMBOLS,
                state_units=_FAKE_STATE_UNITS,
            ),
        ),
    )

    def availability(
        self,
        dataset: FlightDataset,
        input_source: str | None = None,
    ) -> AlgorithmAvailability:
        del dataset, input_source
        return AlgorithmAvailability(True, ReplayFidelity.EXACT)

    def run(
        self,
        dataset: FlightDataset,
        request: ReplayRequest,
        context: TaskContext | None = None,
    ) -> AlgorithmResult:
        del dataset, request, context
        raise NotImplementedError


def _FakeResult_Create() -> AlgorithmResult:
    timestamps = np.asarray(
        [START_TIMESTAMP_US + index * 20_000 for index in range(4)],
        dtype=np.uint64,
    )
    channels = {
        "attitude.q_nb": _Series(
            timestamps,
            np.tile((1.0, 0.0, 0.0, 0.0), (4, 1)),
            columns=("W", "X", "Y", "Z"),
        ),
        "navigation.velocity_enu": _Series(
            timestamps,
            np.zeros((4, 3)),
            columns=("E", "N", "U"),
            unit="m/s",
        ),
        "navigation.position_enu": _Series(
            timestamps,
            np.zeros((4, 3)),
            columns=("E", "N", "U"),
            unit="m",
        ),
        "fake.covariance.diagonal": _Series(
            timestamps,
            np.tile(np.linspace(0.01, 0.15, 15), (4, 1)),
            columns=tuple(f"P{index}" for index in range(15)),
        ),
        "fake.covariance.upper_triangle": _Series(
            timestamps,
            np.vstack(
                [
                    np.arange(1.0, 121.0) + sample_index * 1000.0
                    for sample_index in range(4)
                ]
            ),
            columns=tuple(f"P{index}" for index in range(120)),
        ),
        "fake.update_result": _Series(
            timestamps,
            np.tile((0.0, 1.0, 2.0, 0.0), (4, 1)),
            columns=("GNSS", "Baro", "Mag", "Star Tracker"),
        ),
        "fake.r_scale": _Series(
            timestamps,
            np.tile((1.0, 1.5, 2.0, 1.0), (4, 1)),
            columns=("GNSS", "Baro", "Mag", "Star Tracker"),
        ),
        "fake.measurement_attempt_mask": _Series(
            timestamps,
            np.full(4, 0x0F),
            quantity="status",
        ),
    }
    for group in _FakeEskfPlugin.metadata.estimator_visualization.measurement_groups:
        channels[group.innovation_channel] = _Series(
            timestamps,
            np.ones((4, group.dimension)),
            columns=group.component_names,
        )
        channels[group.nis_channel] = _Series(
            timestamps,
            np.linspace(1.0, 2.0, 4),
            quantity="nis",
        )
        channels[group.effective_r_channel] = _Series(
            timestamps,
            np.full((4, group.dimension), 4.0),
            columns=group.component_names,
            unit=f"({group.unit})^2",
            quantity="variance",
        )
        channels[group.measurement_age_channel] = _Series(
            timestamps,
            np.full(4, 10_000.0),
            unit="us",
            quantity="time",
        )
    return AlgorithmResult(
        algorithm_id=_FakeEskfPlugin.metadata.plugin_id,
        algorithm_version="test",
        input_source="corrected_imu",
        parameters={},
        fidelity=ReplayFidelity.EXACT,
        missing_inputs=(),
        warnings=(),
        channels=channels,
        provenance="Recomputed",
    )


def test_kf6_declares_estimator_visualization_and_parameter_groups() -> None:
    visualization = Kf6AlgorithmPlugin.metadata.estimator_visualization
    assert visualization is not None
    assert {group.group_id for group in visualization.state_groups} == {
        "position",
        "velocity",
    }
    assert {
        group.measurement_group_id for group in visualization.measurement_groups
    } == {
        "gnss_position_en", "gnss_position_u",
        "gnss_velocity_en", "gnss_velocity_u",
        "barometric_altitude",
    }
    assert {group.dimension for group in visualization.measurement_groups} == {1, 2}
    assert PureInsAlgorithmPlugin.metadata.estimator_visualization is None
    assert {
        parameter.group_key for parameter in Kf6AlgorithmPlugin.metadata.parameter_schema
    } == {
        "parameter_group.process_model",
        "parameter_group.initial_covariance",
        "parameter_group.measurement_noise",
        "parameter_group.consistency_gating",
        "parameter_group.gnss_integrity",
    }


def test_fake_eskf_and_magnetometer_need_no_state_page_code_change(
    tmp_path: Path,
) -> None:
    application = QApplication.instance() or QApplication([])
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_fake_eskf.BIN")
    )
    registry = PluginRegistry()
    registry.Algorithm_Register(_FakeEskfPlugin())
    store = ReplayResultStore()
    entry = store.Result_Add(_FakeResult_Create(), algorithm_name="Fake ESKF")
    assert store.ActiveSource_Set(entry.source_id)
    page = StateEstimationPage(Translator("en_US"), registry)
    page.Dataset_Set(dataset, ChannelResolver(dataset, store))
    page.show()
    application.processEvents()

    assert "kf6." not in inspect.getsource(StateEstimationPage)
    assert page.state_group_combo.count() == 5
    assert page.innovation_measurement_combo.count() == 4
    assert page.nis_measurement_combo.count() == 4
    assert page.measurement_group_combo.count() == 4
    assert len(page.covariance_plot.listDataItems()) == 3

    magnetometer = page.innovation_measurement_combo.findData("magnetometer")
    page.innovation_measurement_combo.setCurrentIndex(magnetometer)
    page.nis_measurement_combo.setCurrentIndex(
        page.nis_measurement_combo.findData("magnetometer")
    )
    page.measurement_group_combo.setCurrentIndex(
        page.measurement_group_combo.findData("magnetometer")
    )
    application.processEvents()
    assert len(page.innovation_plot.listDataItems()) == 3
    assert len(page.nis_plot.listDataItems()) == 1
    assert len(page.measurement_uncertainty_plot.listDataItems()) > 0
    assert page.nis_summary.rowCount() == 4
    assert page.tabs.count() == 6

    page.Language_Apply(Translator("zh_CN"))
    assert page.tabs.tabText(2) == "归一化新息平方（NIS）"
    assert page.innovation_measurement_combo.currentText() == "磁力计"
    page.close()


def test_standard_export_uses_fake_state_and_future_sensor_metadata(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_fake_export.BIN")
    )
    registry = PluginRegistry()
    registry.Algorithm_Register(_FakeEskfPlugin())
    store = ReplayResultStore()
    entry = store.Result_Add(_FakeResult_Create(), algorithm_name="Fake ESKF")
    assert store.ActiveSource_Set(entry.source_id)

    manifest = FlightExporter(registry).export(
        dataset,
        tmp_path / "fake_metadata_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=True,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )

    assert not manifest.failures
    names = {_PlotBaseName_Get(path) for path in manifest.files}
    assert {
        "Fake_ESKF_Recomputed_Attitude_Error_Std_1Sigma_EN.png",
        "Fake_ESKF_Recomputed_Gyro_Bias_Std_1Sigma_EN.png",
        "Fake_ESKF_Recomputed_Accel_Bias_Std_1Sigma_EN.png",
        "Fake_ESKF_Recomputed_Innovation_Star_Tracker_Attitude_EN.png",
        "Fake_ESKF_Recomputed_NIS_Star_Tracker_Attitude_EN.png",
        "Fake_ESKF_Recomputed_Measurement_Std_Star_Tracker_Attitude_EN.png",
    } <= names
    standard_source = inspect.getsource(FlightExporter._StandardPlots_Write)
    assert "kf6." not in standard_source.lower()
    assert "gnss_position" not in standard_source
    assert "barometric_altitude" not in standard_source


def test_unconfigured_measurement_group_is_skipped_despite_nonzero_diagnostics(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(
            tmp_path / "SYNTHETIC_fake_unconfigured_mag.BIN",
            configured_magnetometer_rate_hz=0,
        )
    )
    registry = PluginRegistry()
    registry.Algorithm_Register(_FakeEskfPlugin())
    store = ReplayResultStore()
    entry = store.Result_Add(_FakeResult_Create(), algorithm_name="Fake ESKF")
    assert store.ActiveSource_Set(entry.source_id)

    manifest = FlightExporter(registry).export(
        dataset,
        tmp_path / "fake_unconfigured_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=True,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )

    assert not manifest.failures
    names = {_PlotBaseName_Get(path) for path in manifest.files}
    assert not any("Magnetometer" in name for name in names)
    skipped = [
        item
        for item in manifest.skipped
        if item.item_id.endswith(":magnetometer")
    ]
    assert len(skipped) == 3
    assert {
        item.skipped_reason for item in skipped
    } == {"measurement_not_configured"}
    assert (
        "Fake_ESKF_Recomputed_Innovation_Star_Tracker_Attitude_EN.png"
        in names
    )


def test_configured_without_valid_updates_keeps_blank_plots_and_nis_thresholds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_no_gnss_updates.BIN")
    )
    from tests.parameter_fixtures import SyntheticParameters_Attach
    dataset = SyntheticParameters_Attach(dataset, tmp_path / "parameters")
    exporter = FlightExporter()
    calls: dict[str, tuple[TimeSeries | None, str, tuple[tuple[float, str, str], ...]]] = {}
    original = exporter._StandardDiagnosticPlot_Write

    def capture(
        dataset_arg,
        series,
        path,
        title,
        ylabel,
        language,
        theme,
        *,
        empty_message,
        thresholds=(),
        end_timestamp_us=None,
    ) -> None:
        calls[_PlotBaseName_Get(path)] = (series, empty_message, thresholds)
        original(
            dataset_arg,
            series,
            path,
            title,
            ylabel,
            language,
            theme,
            empty_message=empty_message,
            thresholds=thresholds,
            end_timestamp_us=end_timestamp_us,
        )

    monkeypatch.setattr(exporter, "_StandardDiagnosticPlot_Write", capture)
    manifest = exporter.export(
        dataset,
        tmp_path / "configured_no_updates_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=True,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )

    assert not manifest.failures
    for group in ("Position_EN", "Position_U", "Velocity_EN", "Velocity_U"):
        for kind in ("Innovation", "NIS", "Measurement_Std"):
            name = f"KF6_Recorded_{kind}_GNSS_{group}_EN.png"
            assert name in calls
            series, message, thresholds = calls[name]
            assert series is None
            assert message.startswith("No valid GNSS")
            if kind == "NIS":
                assert len(thresholds) == 2


def test_full_p_keyframes_use_plugin_metadata_for_15_state_estimator(
    tmp_path: Path,
) -> None:
    dataset = _DisplayDataset_Parse(
        AnalysisFlight_Build(tmp_path / "SYNTHETIC_fake_eskf_full_p.BIN")
    )
    registry = PluginRegistry()
    registry.Algorithm_Register(_FakeEskfPlugin())
    store = ReplayResultStore()
    entry = store.Result_Add(_FakeResult_Create(), algorithm_name="Fake ESKF")
    assert store.ActiveSource_Set(entry.source_id)

    manifest = FlightExporter(registry).export(
        dataset,
        tmp_path / "fake_eskf_full_p_export",
        options=ExportOptions(
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
        replay_store=store,
    )

    assert not manifest.failures
    full_p_path = (
        tmp_path
        / "fake_eskf_full_p_export"
        / "Fake_ESKF_Full_P_Keyframes_EN.txt"
    )
    assert full_p_path in manifest.files
    text = full_p_path.read_text(encoding="utf-8")
    assert "Algorithm: Fake ESKF (test.algorithm.fake_eskf)" in text
    assert "Source: Recomputed" in text
    assert "14: δbaZ [m/s²]" in text
    assert text.count("Full P matrix (15 x 15):") == 3
    assert "1.00000000000000000e+00" in text
    assert "3.12000000000000000e+03" in text


def test_gnss_nis_group_references_are_shared_by_gui_and_export(tmp_path):
    from tests.parameter_fixtures import SyntheticParameters_Attach
    app = QApplication.instance() or QApplication([])
    dataset = SyntheticParameters_Attach(
        _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "nis.BIN")),
        tmp_path / "parameters",
    )
    groups = Kf6AlgorithmPlugin.metadata.estimator_visualization.measurement_groups
    expected_1d = (6.635, 10.828)
    expected_2d = (9.210, 13.816)
    for language in ("en_US", "zh_CN"):
        page = StateEstimationPage(Translator(language))
        page.Dataset_Set(dataset)
        page.resize(1280, 800)
        page.show()
        for group in groups:
            page.nis_measurement_combo.setCurrentIndex(
                page.nis_measurement_combo.findData(group.measurement_group_id))
            app.processEvents()
            thresholds = FlightExporter._NisThresholds_Get(
                group, {spec.parameter_id: spec.default
                        for spec in Kf6AlgorithmPlugin.metadata.parameter_schema},
                ExportLanguage.EN if language == "en_US" else ExportLanguage.ZH,
            )
            expected = (expected_2d if group.measurement_group_id.endswith("_en")
                        else expected_1d)
            np.testing.assert_allclose([line[0] for line in thresholds], expected, rtol=1e-6)
            assert len(group.NisThresholds_Get()) == 2
            assert "max(" not in page.nis_plot.getPlotItem().titleLabel.text
        page.close()
