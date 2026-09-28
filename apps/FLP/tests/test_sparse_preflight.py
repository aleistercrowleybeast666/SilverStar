from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.diagnostics import DataQualityStatus
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
from silverstar_flp.ui.pages.overview import OverviewPage
from silverstar_flp.ui.pages.replay import ReplayPage
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from tests.synthetic_parameter_navigation import NavigationPair_Open


def test_sparse_120_seconds_import_replay_pages_and_export(tmp_path):
    dataset = NavigationPair_Open(
        tmp_path / "sparse", preflight_us=120_000_000, flight_samples=2001
    ).dataset
    assert dataset.diagnostics.header_valid
    assert dataset.diagnostics.record_crc_failures == 0
    assert dataset.diagnostics.sequence_gap_count == 0
    assert not dataset.diagnostics.truncated_tail
    assert dataset.data_quality.status == DataQualityStatus.CLEAN
    start = next(r.timestamp_us for r in dataset.Records_Get("EVENT") if r.payload["event_id"] == 3)
    assert start - dataset.Records_Get("EVENT")[0].timestamp_us >= 120_000_000
    for name in ("IMU_CORRECTED", "BARO_NATIVE", "BARO_MEASUREMENT"):
        assert min(r.timestamp_us for r in dataset.Records_Get(name)) >= start
    results = {}
    store = ReplayResultStore()
    registry = builtin_registry()
    for plugin in registry.algorithms:
        mode = (
            ReplayMode.RECORDED_CONFIGURATION
            if plugin.FirmwareMember_Is(dataset)
            else ReplayMode.WHAT_IF
        )
        result = plugin.run(dataset, ReplayRequest(mode=mode))
        assert result.fidelity != ReplayFidelity.UNAVAILABLE
        assert not result.missing_inputs
        assert result.channels
        results[plugin.metadata.plugin_id] = result
        entry = store.Result_Add(result, algorithm_name=plugin.metadata.display_name)
        if plugin.metadata.plugin_id.endswith("kf6"):
            store.ActiveSource_Set(entry.source_id)
    app = QApplication.instance() or QApplication([])
    translator = Translator("en_US")
    resolver = ChannelResolver(dataset, store)
    pages = [
        OverviewPage(translator),
        DataExplorerPage(translator),
        StateEstimationPage(translator, registry),
        ReplayPage(translator, registry),
    ]
    for page in pages:
        if isinstance(page, StateEstimationPage):
            page.Dataset_Set(dataset, resolver)
        elif isinstance(page, DataExplorerPage):
            page.Dataset_Set(dataset, store)
        else:
            page.Dataset_Set(dataset)
        page.resize(1280, 800)
        page.show()
        app.processEvents()
        assert page.grab().save(str(tmp_path / (type(page).__name__ + ".png")))
        page.close()
    manifest = FlightExporter().export(
        dataset,
        tmp_path / "export",
        algorithm_results=results,
        options=ExportOptions(
            include_overview=True,
            include_diagnostics=True,
            include_events=True,
            include_csv=True,
            include_plots=True,
            include_full_covariance_keyframes=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert not manifest.failures
    assert list((tmp_path / "export").rglob("*.png"))


def test_sparse_preflight_does_not_hide_missing_mission_imu(tmp_path):
    dataset = NavigationPair_Open(
        tmp_path / "missing", preflight_us=120_000_000, flight_samples=2001, omit_imu=True
    ).dataset
    assert dataset.diagnostics.sequence_gap_count == 0
    for plugin in builtin_registry().algorithms:
        try:
            result = plugin.run(dataset, ReplayRequest())
        except ValueError:
            continue
        assert result.fidelity == ReplayFidelity.UNAVAILABLE
        assert result.missing_inputs
