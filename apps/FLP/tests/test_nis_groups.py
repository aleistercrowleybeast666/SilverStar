from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.core.i18n import Translator
from silverstar_flp.decoder_profiles.semantic_adapter import _StableSeries_Adapt
from silverstar_flp.export.service import ExportLanguage, FlightExporter
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.parameter_fixtures import SyntheticParameters_Attach
from tests.sslog_synthetic import AnalysisFlight_Build
from tests.test_project_export import _DisplayDataset_Parse


def test_recorded_group_nis_and_results_are_distinct_in_state_view(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset = SyntheticParameters_Attach(
        _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "nis.bin")),
        tmp_path / "parameters",
    )
    start = dataset.start_timestamp_us
    measurements = []
    for index in range(2):
        timestamp = start + (index + 1) * 100_000
        measurements.append(DecodedRecord(
            0x20, "GNSS_MEASUREMENT", 1, 0, index + 1, timestamp, 3,
            dict(estimator_present_timestamp_us=timestamp, valid_group_mask=15,
                 replay_epoch=0, sequence=index + 1,
                 group_nis=(2.0 + index, 7.0 + index, 3.0 + index, 11.0 + index),
                 group_update_result=(2, 0, 1, 0),
                 position_innovation_m=(1., 2., 3.),
                 velocity_innovation_mps=(4., 5., 6.),
                 position_variance_m2=(1., 1., 1.),
                 velocity_variance_m2ps2=(1., 1., 1.)),
            0,
        ))
    dataset = replace(dataset, records={
        **dataset.records, "GNSS_MEASUREMENT": tuple(measurements),
    })
    package = SimpleNamespace(semantics=SimpleNamespace(canonical_channels=()))
    series, _aliases = _StableSeries_Adapt(dataset, package)
    dataset = replace(dataset, series=series)
    assert dataset.Series_Get("kf6.recorded.nis.position_en").values.tolist() == [2., 3.]
    assert dataset.Series_Get("kf6.recorded.nis.position_u").values.tolist() == [7., 8.]
    assert dataset.Series_Get("kf6.recorded.nis.velocity_en").values.tolist() == [3., 4.]
    assert dataset.Series_Get("kf6.recorded.nis.velocity_u").values.tolist() == [11., 12.]
    page = StateEstimationPage(Translator("en_US"))
    page.Dataset_Set(dataset)
    assert page.nis_display_combo.count() == 2
    assert [page.nis_display_combo.itemText(index) for index in range(2)] == [
        "NIS Curve", "Four-group Statistics",
    ]
    assert page.nis_pages.count() == 2
    page.resize(1000, 700)
    page.tabs.setCurrentWidget(page.nis_pages.parentWidget())
    page.show()
    app.processEvents()
    assert page.nis_plot.height() > 300
    page.nis_display_combo.setCurrentIndex(1)
    app.processEvents()
    assert page.nis_summary.height() > 300
    assert "current time window" in page.nis_scope_label.text().lower()
    page.setStyleSheet("font-size: 24px;")  # Approximate 200% text scale at 1000×700.
    app.processEvents()
    assert page.nis_summary.viewport().height() > sum(
        page.nis_summary.rowHeight(row) for row in range(4)
    )
    for group_id, expected in (
        ("gnss_position_en", [2., 3.]), ("gnss_position_u", [7., 8.]),
        ("gnss_velocity_en", [3., 4.]), ("gnss_velocity_u", [11., 12.]),
    ):
        page.nis_measurement_combo.setCurrentIndex(
            page.nis_measurement_combo.findData(group_id)
        )
        app.processEvents()
        curves = page.nis_plot.listDataItems()
        assert curves
        np.testing.assert_array_equal(curves[0].getData()[1], expected)
        groups = Kf6AlgorithmPlugin.metadata.estimator_visualization.measurement_groups
        group = next(group for group in groups
                     if group.measurement_group_id == group_id)
        lines = FlightExporter._NisThresholds_Get(
            group, {spec.parameter_id: spec.default
                    for spec in Kf6AlgorithmPlugin.metadata.parameter_schema},
            ExportLanguage.EN,
        )
        assert len(lines) == 2
        assert all(line.parameter_id.startswith("nis_2d")
                   for line in group.NisThresholds_Get()) if group_id.endswith("_en") else all(
                       line.parameter_id.startswith("nis_1d")
                       for line in group.NisThresholds_Get())
    assert page.nis_summary.rowCount() == 4
    labels = [page.nis_summary.item(row, 0).text() for row in range(4)]
    assert labels == ["GNSS Position EN", "GNSS Position U",
                      "GNSS Velocity EN", "GNSS Velocity U"]
    assert page.nis_summary.item(0, 3).text() == "2"
    assert page.nis_summary.item(1, 1).text() == "2"
    assert page.nis_summary.item(2, 2).text() == "2"
    page.TimeRange_Set(0.0, 0.15)
    assert page.nis_summary.item(0, 3).text() == "1"
    assert page.nis_summary.item(1, 1).text() == "1"
    page.close()
