"""Read-only, opt-in current SS0000 compatibility gate; never a host-C Golden."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.trajectory import (
    TimeSeriesGapSummary_Get,
    TrajectoryPhaseSegments_Build,
    TrajectoryPhaseValues_Get,
)
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.charts import FlightPage
from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
from silverstar_flp.ui.pages.overview import OverviewPage

_LOG_HASH = "00a77559dbd44eff8dad0a1523c7e7c9fc1ac0533d4b7687d27884038e6023dd"
_PACKAGE_HASH = "d5d208c77215369e613c2df79177c09a46db1d6cff97be96fd1f91d0627f773f"


@pytest.mark.skipif(
    not os.environ.get("SILVERSTAR_CURRENT_LOG_ROOT"),
    reason="set SILVERSTAR_CURRENT_LOG_ROOT for the hash-locked SS0000 log",
)
def test_current_log_display_and_quality_acceptance(tmp_path):
    root = Path(os.environ["SILVERSTAR_CURRENT_LOG_ROOT"])
    log = root / "LOG/SS0000.BIN"
    package = root / "HARDWARE/SS_0_5_TEST_0.ssdecoder"
    assert hashlib.sha256(log.read_bytes()).hexdigest() == _LOG_HASH
    assert hashlib.sha256(package.read_bytes()).hexdigest() == _PACKAGE_HASH
    registry = builtin_registry()
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(log_path=log, decoder_package_path=package)
    )
    dataset = opened.dataset
    quality = dataset.data_quality
    assert quality.status.value == "startup_drops"
    assert quality.structural_integrity == "normal"
    assert quality.mission_record_continuity == "continuous"
    assert (quality.sequence_gap_count, quality.sequence_missing_count) == (3, 12)
    assert quality.logger_overflow_count == 39 and quality.imu_queue_overflow_count == 0
    assert all(gap["mission_phase"] == "before_start" for gap in quality.sequence_gaps)
    summary = FlightSummary_Build(dataset)
    assert summary.gnss.latest_online and summary.gnss.latest_fix_type == 0
    assert dataset.semantic_context.calibration.identity_model
    resolver = ChannelResolver(dataset, ReplayResultStore())
    positions = {}
    for name, rate in (("pure_ins", 100), ("kf6", 25)):
        channel = f"{name}.recorded.navigation.position_enu"
        series = dataset.Series_Get(channel)
        assert series is not None and series.columns == ("E", "N", "U")
        assert np.isfinite(series.values).all()
        measured_rate = 1e6 / np.median(np.diff(series.timestamp_us))
        assert abs(measured_rate - rate) < 1
        positions[name] = series
        assert (
            TimeSeriesGapSummary_Get(series, dataset.start_timestamp_us)["timestamp_gap_segments"]
            == 0
        )
        algorithm = registry.Algorithm_Get(f"silverstar.algorithm.{name}")
        assert algorithm.availability(dataset).available
    deploy = next(
        record.timestamp_us
        for record in dataset.Records_Get("EVENT")
        if record.payload["event_id"] == 0x29
    )
    segments = TrajectoryPhaseSegments_Build(positions["kf6"], (deploy,))
    pre, post = (TrajectoryPhaseValues_Get(segments, phase) for phase in (0, 1))
    np.testing.assert_array_equal(pre[-1], post[0])
    assert deploy not in positions["kf6"].timestamp_us
    app = QApplication.instance() or QApplication([])
    for language in ("zh_CN", "en_US"):
        translator = Translator(language)
        overview, flight, explorer = (
            OverviewPage(translator),
            FlightPage(translator),
            DataExplorerPage(translator),
        )
        overview.Dataset_Set(dataset)
        flight.Dataset_Set(dataset, resolver)
        explorer.Dataset_Set(dataset)
        app.processEvents()
        assert "12 IDs" in overview.quality_card.detail_label.text()
        assert "39" in overview.quality_card.detail_label.text()
        assert explorer.sequence_gap_table.rowCount() == 3
        for theme in ("light", "dark"):
            flight.Theme_Apply(theme)
            flight._Trajectory3d_Refresh(flight._end_timestamp_us)
            np.testing.assert_allclose(
                flight.pre_deploy_line.pos[-1], flight.post_deploy_line.pos[0]
            )
        overview.close()
        flight.close()
        explorer.close()
    manifest = FlightExporter(registry).export(
        dataset,
        tmp_path / "export",
        options=ExportOptions(
            include_overview=False,
            include_diagnostics=True,
            include_events=True,
            include_csv=True,
            include_full_covariance_keyframes=False,
            include_plots=False,
            include_trajectory_3d=True,
            include_attitude_gif=True,
            selected_channels=("kf6.recorded.navigation.position_enu",),
        ),
    )
    audit = json.loads(manifest.ManifestPath_Get().read_text(encoding="utf8"))
    assert not audit["failed"]
    assert audit["data_quality"]["gap_segments"] == 3
    assert audit["data_quality"]["missing_ids"] == 12
    assert audit["data_quality"]["queue_overflow"]["logger"] == 39
    assert list((tmp_path / "export").glob("*.png"))
    gifs = list((tmp_path / "export").glob("*.gif"))
    assert gifs
    with Image.open(gifs[0]) as image:
        assert image.n_frames >= 2
    assert hashlib.sha256(log.read_bytes()).hexdigest() == _LOG_HASH
    assert hashlib.sha256(package.read_bytes()).hexdigest() == _PACKAGE_HASH
