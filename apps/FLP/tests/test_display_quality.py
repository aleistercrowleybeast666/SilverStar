from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
from silverstar_flp.core.diagnostics import DiagnosticSeverity, ParserDiagnostics
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.semantic_columns import SemanticColumns_Get
from silverstar_flp.core.trajectory import (
    TrajectoryGapThreshold_Get,
    TrajectoryPhaseSegments_Build,
    TrajectoryPhaseValues_Get,
    TrajectoryPosition_At,
    TrajectoryPosition_NearEvent,
)
from silverstar_flp.decoder_profiles import ProjectSemantics, RecordCatalog
from silverstar_flp.export.service import FlightExporter
from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
from silverstar_flp.ui.pages.overview import OverviewPage
from tests.test_decoder_profiles import _CatalogDocument_Build, _SemanticsDocument_Build


@pytest.mark.parametrize(
    "record,field,count,expected",
    [
        ("PURE_INS", "position_enu_m", 3, ("E", "N", "U")),
        ("ESTIMATOR", "velocity_enu_mps", 3, ("E", "N", "U")),
        ("PURE_INS", "accel_enu_mps2", 3, ("E", "N", "U")),
        ("IMU_NATIVE", "accel_b_mps2", 3, ("X", "Y", "Z")),
        ("IMU_NATIVE", "gyro_raw", 3, ("X", "Y", "Z")),
        ("MAG_NATIVE", "mag_raw", 3, ("X", "Y", "Z")),
        ("PURE_INS", "q_nb", 4, ("W", "X", "Y", "Z")),
        ("HW_QUAT_NATIVE", "quaternion_wxyz", 4, ("W", "X", "Y", "Z")),
        ("SAMPLE", "q_raw", 4, ("W", "X", "Y", "Z")),
        ("SAMPLE", "euler_deg", 3, ("Roll", "Pitch", "Yaw")),
        ("KF6_STATE", "state", 6, ("xE", "xN", "xU", "vE", "vN", "vU")),
        ("ESTIMATOR", "covariance_diagonal", 6, ("PxE", "PxN", "PxU", "PvE", "PvN", "PvU")),
        ("THIRD_PARTY", "array", 3, ("[0]", "[1]", "[2]")),
    ],
)
def test_semantic_columns(record, field, count, expected):
    assert SemanticColumns_Get(record, field, count) == expected


@pytest.mark.parametrize("explicit", [None, ["right", "forward", "up"], ["0", "1", "2"]])
def test_catalog_columns_take_priority(explicit):
    catalog = _CatalogDocument_Build()
    if explicit is not None:
        catalog["records"][0]["fields"][4]["columns"] = explicit
    semantics = ProjectSemantics.FromDocument(_SemanticsDocument_Build()).Catalog_Bind(
        RecordCatalog.FromDocument(catalog)
    )
    channel = semantics.records["IMU_NATIVE"].channels[0]
    assert channel.columns == tuple(explicit or ("X", "Y", "Z"))


def _Series_Build(times=(0, 10, 20, 30, 40), valid=None):
    return TimeSeries(
        np.asarray(times, dtype=np.uint64),
        np.column_stack((times, times, times)).astype(float),
        "m",
        "position",
        "SYNTHETIC",
        np.ones(len(times), dtype=bool) if valid is None else valid,
    )


@pytest.mark.parametrize("events", [(15,), (20,), (15, 25), (12, 15, 18)])
def test_phase_events_share_exact_display_points_without_changing_samples(events):
    series = _Series_Build()
    before = series.values.copy()
    segments = TrajectoryPhaseSegments_Build(series, events)
    assert len(segments) == len(events) + 1
    for index, event in enumerate(events):
        assert segments[index].timestamp_us[-1] == event
        assert segments[index + 1].timestamp_us[0] == event
        np.testing.assert_array_equal(segments[index].values[-1], segments[index + 1].values[0])
        np.testing.assert_allclose(segments[index].values[-1], [event] * 3)
    np.testing.assert_array_equal(series.values, before)
    assert series.count == 5 and not series.values.flags.writeable


@pytest.mark.parametrize("events", [(), (100,)])
def test_true_series_gap_is_never_bridged(events):
    series = _Series_Build((0, 10, 20, 200, 210, 220))
    assert TrajectoryGapThreshold_Get(series) == 25
    segments = TrajectoryPhaseSegments_Build(series, events)
    assert len(segments) == 2
    assert all(100 not in segment.timestamp_us for segment in segments)
    assert TrajectoryPosition_At(series, 100) is None
    assert TrajectoryPosition_NearEvent(series, 100) is None
    if not events:
        assert np.isnan(TrajectoryPhaseValues_Get(segments, 0)[3]).all()


def test_invalid_sample_and_duplicate_timestamp_keep_a_break():
    series = _Series_Build(valid=np.array([1, 1, 0, 1, 1], dtype=bool))
    assert len(TrajectoryPhaseSegments_Build(series)) == 2
    assert TrajectoryPosition_At(series, 25) is None
    assert len(TrajectoryPhaseSegments_Build(_Series_Build((0, 10, 10, 20)))) == 2


def test_explicit_tolerance_and_downsampling_preserve_phase_endpoints():
    series = replace(
        _Series_Build((0, 10, 20, 60, 70)), metadata={"trajectory_gap_tolerance_us": 50}
    )
    segments = TrajectoryPhaseSegments_Build(series, (40,))
    first = TrajectoryPhaseValues_Get(segments, 0, max_points_per_segment=2)
    second = TrajectoryPhaseValues_Get(segments, 1, max_points_per_segment=2)
    np.testing.assert_array_equal(first[-1], second[0])


def _Dataset_Build(tmp_path, gap_times=(100, 200, 300)):
    diagnostics = ParserDiagnostics(
        header_valid=True,
        header_crc_expected=1,
        header_crc_actual=1,
        record_count=100,
        sequence_gap_count=3,
        sequence_missing_count=12,
    )
    for index, (timestamp, missing) in enumerate(zip(gap_times, (3, 1, 8), strict=True)):
        diagnostics.Diagnostic_Add(
            "record_sequence_gap",
            DiagnosticSeverity.WARNING,
            offset=100 + index,
            record_sequence=70 + index,
            expected_sequence=67 + index,
            actual_sequence=70 + index,
            missing_count=missing,
            timestamp_us=timestamp,
            previous_timestamp_us=timestamp - 10,
        )
    records = {
        "EVENT": (
            DecodedRecord(
                2,
                "EVENT",
                0,
                12,
                90,
                1000,
                0,
                {"event_id": 3, "event_name": "MISSION_START", "arg0": 0, "arg1": 0},
                500,
            ),
        ),
        "STATS": tuple(
            DecodedRecord(
                1,
                "STATS",
                0,
                0,
                i,
                i * 100,
                0,
                {"logger_queue_overflow_count": count, "imu_queue_overflow_count": 0},
                i * 20,
            )
            for i, count in enumerate((0, 39, 39))
        ),
    }
    return FlightDataset(
        tmp_path / "SYNTHETIC.BIN", 1000, {}, diagnostics, records, {"position": _Series_Build()}
    )


def test_record_gaps_and_queue_counts_are_independent(tmp_path):
    dataset = _Dataset_Build(tmp_path)
    quality = dataset.data_quality
    assert quality.status.value == "startup_drops"
    assert quality.mission_record_continuity == "continuous"
    audit = quality.ToDict()
    assert (audit["gap_segments"], audit["missing_ids"]) == (3, 12)
    assert audit["queue_overflow"] == {"logger": 39, "imu": 0}
    assert audit["logger_overflow_event_count"] == 0
    assert len(TrajectoryPhaseSegments_Build(dataset.series["position"])) == 1
    with pytest.raises(TypeError):
        quality.sequence_gaps[0]["mission_phase"] = "mission"


@pytest.mark.parametrize(
    "gap_times,continuity", [((100, 200, 1100), "gaps"), ((100, 200, 1005), "gaps")]
)
def test_mission_or_boundary_gaps_are_not_classified_as_startup(tmp_path, gap_times, continuity):
    quality = _Dataset_Build(tmp_path, gap_times).data_quality
    assert quality.status.value == "warnings"
    assert quality.mission_record_continuity == continuity


def test_missing_phase_evidence_stays_unknown(tmp_path):
    dataset = _Dataset_Build(tmp_path)
    dataset.diagnostics.diagnostics[0].details.pop("previous_timestamp_us")
    quality = replace(dataset, data_quality=None).data_quality
    assert quality.status.value == "warnings"
    assert quality.mission_record_continuity == "unknown"


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_quality_gui_and_csv_inherit_shared_metadata(tmp_path, language):
    app = QApplication.instance() or QApplication([])
    dataset = _Dataset_Build(tmp_path)
    series = replace(dataset.series["position"], columns=("E", "N", "U"))
    dataset = replace(dataset, series={"position": series})
    overview = OverviewPage(Translator(language))
    explorer = DataExplorerPage(Translator(language))
    overview.Dataset_Set(dataset)
    explorer.Dataset_Set(dataset)
    app.processEvents()
    assert "3" in overview.quality_card.detail_label.text()
    assert "12 IDs" in overview.quality_card.detail_label.text()
    assert "39" in overview.quality_card.detail_label.text()
    assert explorer.sequence_gap_table.rowCount() == 3
    path = tmp_path / "channel.csv"
    FlightExporter._SeriesCsv_Write(dataset, "position", series, path)
    assert any(",E,N,U," in line for line in path.read_text(encoding="utf-8-sig").splitlines())
    overview.close()
    explorer.close()


def test_gif_samples_use_the_same_event_geometry():
    position = _Series_Build()
    attitude = TimeSeries(
        position.timestamp_us,
        np.tile([1.0, 0.0, 0.0, 0.0], (5, 1)),
        "1",
        "quaternion",
        "SYNTHETIC",
        np.ones(5, dtype=bool),
    )
    samples = FlightExporter()._ReplayFrameSamples_Precompute(
        attitude,
        position.timestamp_us,
        position.values,
        np.array([15, 40]),
        15,
        40,
        {"deploy": 0, "landing": 1},
    )
    for sample in samples:
        np.testing.assert_array_equal(sample.pre_deploy_values[-1], [15] * 3)
        np.testing.assert_array_equal(sample.post_deploy_values[0], [15] * 3)
    assert samples[-1].landing_visible


def test_local_document_links_resolve():
    import re

    root = Path(__file__).resolve().parents[1]
    documents = [root / name for name in ("README.md", "AGENTS.md", "TARGETS.md", "CHANGELOG.md")]
    documents.extend((root / "docs").glob("*.md"))
    for document in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf8")):
            if "://" in target or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            assert (document.parent / path).exists(), f"{document}: {target}"


def test_gif_event_marker_does_not_interpolate_through_an_invalid_sample(tmp_path, monkeypatch):
    from silverstar_flp.export.service import ExportOptions
    from tests.sslog_synthetic import AnalysisFlight_Build
    from tests.test_project_export import _DisplayDataset_Parse

    dataset = _DisplayDataset_Parse(AnalysisFlight_Build(tmp_path / "SYNTHETIC_gap.BIN"))
    channel_id = "kf6.recorded.navigation.position_enu"
    position = dataset.Series_Get(channel_id)
    deploy = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if record.payload["event_id"] == 0x29
    )
    valid = position.valid.copy()
    index = int(np.searchsorted(position.timestamp_us, deploy))
    valid[index] = False
    position = replace(position, valid=valid)
    dataset = replace(dataset, series={**dataset.series, channel_id: position})
    exporter = FlightExporter()
    original = exporter._ReplayTrajectoryArtists_Create
    meshes = []

    def capture(*args):
        meshes.append(args[5])  # deploy mesh passed to the real renderer
        return original(*args)

    monkeypatch.setattr(exporter, "_ReplayTrajectoryArtists_Create", capture)
    manifest = exporter.export(
        dataset,
        tmp_path / "export",
        options=ExportOptions(
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=False,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=False,
            include_attitude_gif=True,
        ),
    )
    assert meshes and meshes[0] is None
    assert manifest.ManifestPath_Get() is not None
