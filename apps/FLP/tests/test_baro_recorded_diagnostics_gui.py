from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from silverstar_flp.analysis.measurement_diagnostics import RecordedMeasurementChannels_Build
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.dataset import TimeSeries
from silverstar_flp.core.i18n import Translator
from silverstar_flp.decoder_profiles.semantic_adapter import _StableSeries_Adapt
from silverstar_flp.export.service import ExportLanguage, ExportTheme, FlightExporter
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage

from tests.parameter_fixtures import SyntheticParameters_Attach
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_baro_recorded_diagnostics import _Record
from tests.test_project_export import _DisplayDataset_Parse

_APP = None


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_measurement_only_baro_gui_and_png_have_exact_valid_points(
    tmp_path,
    language,
    theme,
    monkeypatch,
):
    global _APP
    _APP = QApplication.instance() or QApplication(["baro-diagnostic-qa", "-platform", "offscreen"])
    app = _APP
    dataset = SyntheticParameters_Attach(
        _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "input.bin")),
        tmp_path / "params",
    )
    start = dataset.start_timestamp_us
    records = tuple(
        _Record(
            index + 1,
            estimator_present_timestamp_us=start + (index + 1) * 100_000,
            receive_timestamp_us=start + (index + 1) * 100_000 - 3_000,
            measurement_timestamp_us=start + (index + 1) * 100_000 - 10_000,
            innovation_m=value,
        )
        for index, value in enumerate((0.088341847, 0.25))
    )
    dataset = replace(
        dataset,
        records={
            **{key: value for key, value in dataset.records.items() if key != "KF6_DIAGNOSTIC"},
            "BARO_MEASUREMENT": records,
        },
        series={
            key: value
            for key, value in dataset.series.items()
            if ".innovation." not in key and ".nis." not in key and ".update_result" not in key
        },
    )
    dataset = replace(
        dataset,
        series={
            **dataset.series,
            "raw.baro.relative_altitude": TimeSeries(
                np.asarray([start + 90_000, start + 190_000], dtype=np.uint64),
                np.asarray([2.0, 2.0]),
                "m",
                "altitude",
                "BARO_MEASUREMENT",
                np.asarray([True, True]),
                metadata={"record_name": "BARO_MEASUREMENT", "field_name": "relative_altitude_m"},
            ),
        },
    )
    series, _ = _StableSeries_Adapt(
        dataset,
        SimpleNamespace(semantics=SimpleNamespace(canonical_channels=())),
    )
    parameters = dict(Kf6AlgorithmPlugin().OfflineParameters_Get())
    series.update(RecordedMeasurementChannels_Build(dataset.records, parameters))
    dataset = replace(dataset, series=series)
    resolver = ChannelResolver(dataset, ReplayResultStore())
    page = StateEstimationPage(Translator(language))
    page.Theme_Apply(theme)
    page.Dataset_Set(dataset, resolver)
    for combo in (
        page.innovation_measurement_combo,
        page.nis_measurement_combo,
        page.measurement_group_combo,
    ):
        combo.setCurrentIndex(combo.findData("barometric_altitude"))
    page.resize(1100, 900)
    page.show()
    page.tabs.setCurrentWidget(page.innovation_plot.parentWidget())
    app.processEvents()
    assert page.innovation_plot.isVisible()
    innovation_curves = page.innovation_plot.listDataItems()
    assert len(innovation_curves) == 1
    np.testing.assert_allclose(innovation_curves[0].getData()[1], [0.088341847, 0.25])
    np.testing.assert_allclose(innovation_curves[0].getData()[0], [0.1, 0.2])
    np.testing.assert_array_equal(page.nis_plot.listDataItems()[0].getData()[1], [1.0, 1.0])
    assert len(page.measurement_uncertainty_plot.listDataItems()) == 2
    for curve in page.measurement_uncertainty_plot.listDataItems():
        np.testing.assert_array_equal(curve.getData()[1], [5.0, 5.0])
    assert len(page.measurement_age_plot.listDataItems()) == 2
    assert page.innovation_plot.grab().save(str(tmp_path / "gui_innovation.png"))

    exporter = FlightExporter()
    group = next(
        group
        for group in Kf6AlgorithmPlugin.metadata.estimator_visualization.measurement_groups
        if group.measurement_group_id == "barometric_altitude"
    )
    source = resolver.Source_Get()
    assert exporter._MeasurementHasValidUpdates_Check(dataset, resolver, source, group)
    exporter._Matplotlib_Configure()
    from matplotlib.figure import Figure

    original_savefig = Figure.savefig
    captured = []

    def capture(figure, *args, **kwargs):
        captured.append([line.get_data() for axis in figure.axes for line in axis.lines])
        return original_savefig(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", capture)
    for label, channel, expected in (
        ("Innovation", group.innovation_channel, [0.088341847, 0.25]),
        ("NIS", group.nis_channel, [1.0, 1.0]),
        ("Effective_R", group.effective_r_channel, [25.0, 25.0]),
    ):
        selected = exporter._MeasurementSeries_Get(resolver, source, group, channel)
        assert selected.valid.tolist() == [True, True]
        path = tmp_path / f"{label}.png"
        exporter._StandardDiagnosticPlot_Write(
            dataset,
            selected,
            path,
            label,
            label,
            ExportLanguage(language),
            ExportTheme(theme),
            empty_message="No valid Barometric diagnostics",
        )
        assert path.stat().st_size > 1000
        assert len(captured[-1]) == 1
        np.testing.assert_allclose(captured[-1][0][0], [0.1, 0.2])
        np.testing.assert_allclose(captured[-1][0][1], expected)
    page.close()
