import gzip
import json
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.gnss_integrity_display import (
    HorizontalQuality_Build,
    HorizontalQualitySummary_Get,
)
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportLanguage, ExportTheme, FlightExporter


@pytest.fixture
def mission62():
    path = Path(__file__).parent / "fixtures/gnss_quality_mission000062.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as source:
        fixture = json.load(source)
    quality = tuple(DecodedRecord(39, "NAV_QUALITY", 1, 100, index, row[0], 0, {
        "quality_revision": 3, "evaluation_us": row[0], "closure_norm_m": row[1],
        "variance_scale": row[2], "evidence_valid": row[3], "closure_en_m": row[4:6],
    }, 0) for index, row in enumerate(fixture["rows"]))
    initial = DecodedRecord(0, "INITIAL_STATE", 1, 0, 0, fixture["origin_us"], 0, {}, 0)
    return FlightDataset(Path("mission000062-display-projection.sslog"), 0, {},
                         ParserDiagnostics(), {"NAV_QUALITY": quality,
                         "INITIAL_STATE": (initial,)}, {})


def test_mission62_recorded_window_values_and_interval_vs_endpoint(mission62):
    trace = HorizontalQuality_Build(mission62)
    summary = HorizontalQualitySummary_Get(trace, mission62.start_timestamp_us)
    assert summary["samples"] == 3390 and summary["valid_samples"] == 3140
    assert summary["maximum_closure_m"] == pytest.approx(15.71895980834961)
    assert summary["maximum_scale"] == pytest.approx(2.4708569049835205)
    assert summary["end_scale"] == 1 and summary["weighted_samples"] > 0
    assert np.isnan(trace.closure_norm_m[~trace.evidence_valid]).all()


def test_nonfinite_coordinates_are_omitted_without_fabricating_validity(mission62):
    first = mission62.Records_Get("NAV_QUALITY")[300]
    bad = replace(first, payload={**first.payload, "closure_en_m": (np.nan, 0.0)})
    dataset = replace(mission62, records={"NAV_QUALITY": (bad,)})
    trace = HorizontalQuality_Build(dataset)
    assert not trace.evidence_valid[0] and np.isnan(trace.closure_norm_m[0])
    assert trace.variance_scale[0] == first.payload["variance_scale"]


def test_recomputed_evidence_never_uses_recorded_rows_or_native_epoch_as_plot_time(mission62):
    evidence = [dict(evaluation_us=60_000_000, end_us=486_109_000_000,
                     valid=True, closure_en=(6., 8.), variance_scale=1.5),
                dict(evaluation_us=None, end_us=486_114_000_000,
                     valid=True, closure_en=(30., 40.), variance_scale=4.)]
    trace = HorizontalQuality_Build(mission62, source_kind="recomputed",
                                    window_evidence=evidence, integrity_enabled=True)
    assert trace.source_kind == "recomputed"
    np.testing.assert_array_equal(trace.timestamp_us, [60_000_000])
    np.testing.assert_array_equal(trace.closure_norm_m, [10.])
    assert HorizontalQuality_Build(mission62, source_kind="recomputed").timestamp_us.size == 0


def test_recomputed_disabled_or_unknown_policy_does_not_fabricate_weighting(mission62):
    evidence = [dict(evaluation_us=60_000_000, valid=True,
                     closure_en=(6., 8.), variance_scale=1.5)]
    disabled = HorizontalQuality_Build(mission62, source_kind="recomputed",
                                      window_evidence=evidence, integrity_enabled=False)
    unknown = HorizontalQuality_Build(mission62, source_kind="recomputed",
                                     window_evidence=evidence)
    np.testing.assert_array_equal(disabled.closure_norm_m, [10.])
    np.testing.assert_array_equal(disabled.variance_scale, [1.])
    assert np.isnan(unknown.variance_scale).all()


def test_current_display_has_no_revision2_fallback(mission62):
    rows = tuple(replace(r, payload={**r.payload, "quality_revision": 2})
                 for r in mission62.Records_Get("NAV_QUALITY"))
    trace = HorizontalQuality_Build(replace(mission62, records={"NAV_QUALITY": rows}))
    assert trace.timestamp_us.size == 0


def test_mission62_gui_and_export_use_identical_current_trace(mission62, tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from matplotlib.axes import Axes
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.ui.gnss_integrity import GnssIntegrityPage
    app = QApplication.instance() or QApplication([])
    page = GnssIntegrityPage(Translator("en_US"))
    page.Dataset_Set(mission62)
    page.Source_Set({"gnss_integrity_error_threshold_m": 10,
                     "gnss_integrity_recovery_threshold_m": 4}, source_kind="recorded")
    page.TimeRange_Set(0, 135.672253)
    gui = page.closure_plot.listDataItems()[0].getData()
    weight = page.weight_plot.listDataItems()[0].getData()
    assert np.nanmax(gui[1]) == pytest.approx(15.71895980834961)
    assert "15.7" in page.status_label.text() and "2.47" in page.status_label.text()
    assert "multiplier 1" in page.status_label.text()
    lines = [x for x in page.closure_plot.items() if type(x).__name__ == "InfiniteLine"]
    assert len(lines) == 1 and lines[0].angle == 0  # Scale only; no reset/recovery lines.
    plotted = []
    original = Axes.plot
    def capture(axis, *args, **kwargs):
        plotted.append((np.asarray(args[0]), np.asarray(args[1])))
        return original(axis, *args, **kwargs)
    monkeypatch.setattr(Axes, "plot", capture)
    path = tmp_path / "mission000062.png"
    FlightExporter()._GnssIntegrityPlot_Write(
        mission62, page._horizontal, "GNSS_Horizontal_Consistency_Error", path,
        ExportLanguage.EN, ExportTheme.LIGHT, 0, 135.672253,
        {"gnss_integrity_error_threshold_m": 10})
    np.testing.assert_allclose(plotted[0][0], gui[0])
    np.testing.assert_allclose(plotted[0][1], gui[1], equal_nan=True)
    np.testing.assert_allclose(plotted[1][1], weight[1], equal_nan=True)
    assert path.stat().st_size > 1000
    page.Source_Set({}, source_kind="recomputed", window_evidence=[])
    assert page._horizontal.timestamp_us.size == 0
    assert "Offline recomputation" in page.status_label.text()
    assert "unavailable" in page.status_label.text()
    page.close()
    app.processEvents()
