from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.core.i18n import Translator
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.export.service import ExportOptions, FlightExporter
from silverstar_flp.log_open import (
    LogOpenCoordinator,
    LogOpenRequest,
    LogOpenSourceMode,
)
from silverstar_flp.plugins.algorithms.pure_ins.plugin import (
    SOURCE_RECORDED_INCREMENT,
)
from silverstar_flp.plugins.api.algorithm import (
    ReplayFidelity,
    ReplayRequest,
)
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.data_explorer import DataExplorerPage
from silverstar_flp.ui.pages.overview import OverviewPage

_ROOT_ENVIRONMENT = "SILVERSTAR_SS0014_ROOT"
_LOG_SHA256 = "d41edfd449dd9507066bcd2bb9d04f20a28977b877294f7709727564e71e3225"
_PACKAGE_SHA256 = (
    "5335fb5ad1abaaab993c278f602c0704b883d7cc58632a5baf12f0c5655161f0"
)


def _Sha256_Get(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.mark.skipif(
    not os.environ.get(_ROOT_ENVIRONMENT),
    reason=f"set {_ROOT_ENVIRONMENT} to the matching SS0014 task root",
)
def test_ss0014_current_log_compatibility_gate(tmp_path: Path) -> None:
    root = Path(os.environ[_ROOT_ENVIRONMENT])
    log_path = root / "LOG" / "SS0014.BIN"
    package_path = root / "HARDWARE" / "SS_0_5_TEST_0.ssdecoder"
    assert log_path.is_file()
    assert package_path.is_file()
    source_hash_before = _Sha256_Get(log_path)
    package_hash_before = _Sha256_Get(package_path)
    assert source_hash_before == _LOG_SHA256
    assert package_hash_before == _PACKAGE_SHA256

    registry = builtin_registry()
    result = LogOpenCoordinator(
        registry,
        cache=DecoderProfileCache(tmp_path / "cache"),
    ).Open(
        LogOpenRequest(
            log_path=log_path,
            decoder_package_path=package_path,
            source_mode=LogOpenSourceMode.CLI,
        )
    )
    dataset = result.dataset
    diagnostics = result.parse_diagnostics
    summary = FlightSummary_Build(dataset)

    assert result.match_mode == "exact_generation_profile"
    assert result.package.package_sha256 == _PACKAGE_SHA256
    assert dataset.metadata["parse_status"] == "partial"
    assert diagnostics.header_valid
    assert diagnostics.header_crc_valid
    assert diagnostics.record_count == 87_980
    assert diagnostics.decoded_record_count == 87_980
    assert diagnostics.record_crc_failures == 1_152
    assert diagnostics.record_length_failures == 50
    assert diagnostics.resync_count == 1_252
    assert diagnostics.recovered_after_crc == 1_152
    assert diagnostics.recovered_after_sync_loss == 100
    assert diagnostics.sequence_gap_count == 1_222
    assert diagnostics.sequence_missing_count == 1_222
    assert diagnostics.decoder_failure_count == 0
    assert diagnostics.unknown_record_type_count == 0
    assert diagnostics.unknown_record_version_count == 0
    assert not diagnostics.truncated_tail
    assert len(diagnostics.damaged_spans) == 1_252
    assert all(span.raw_hex for span in diagnostics.damaged_spans)
    assert all(len(span.raw_hex) <= 96 * 2 for span in diagnostics.damaged_spans)
    assert result.data_quality.status.value == "warnings"

    calibration = dataset.semantic_context.calibration
    assert calibration.mode_name == "NONE"
    assert calibration.identity_model
    assert calibration.ready
    assert calibration.start_sequence == 1
    assert calibration.samples == 0
    assert calibration.accel_bias_mps2 == (0.0, 0.0, 0.0)
    assert calibration.accel_scale == (1.0, 1.0, 1.0)

    assert summary.gnss.native_configured
    assert summary.gnss.measurement_configured
    assert summary.gnss.native_sample_count == 2_666
    assert summary.gnss.measurement_sample_count == 0
    assert summary.gnss.latest_online
    assert summary.gnss.latest_fix_type == 0
    assert summary.gnss.position_usable_count == 0
    assert summary.gnss.velocity_usable_count == 0
    geodetic = tuple(
        series
        for series in dataset.series.values()
        if series.quantity == "geodetic_position"
    )
    assert geodetic
    assert all(not series.valid.any() for series in geodetic)

    assert summary.alignment.history_count == 3
    assert summary.alignment.ready_history_count == 2
    assert summary.alignment.result_timestamp_us == 87_918_336
    assert summary.alignment.initial_state_timestamp_us == 97_925_089
    assert summary.alignment.initial_state_authoritative
    assert summary.alignment.quaternion_record == "INITIAL_STATE"

    pure_ins = registry.Algorithm_Get("silverstar.algorithm.pure_ins")
    kf6 = registry.Algorithm_Get("silverstar.algorithm.kf6")
    pure_availability = pure_ins.availability(
        dataset,
        SOURCE_RECORDED_INCREMENT,
    )
    kf6_availability = kf6.availability(dataset)
    assert pure_availability.available
    assert kf6_availability.available
    assert pure_availability.fidelity == ReplayFidelity.APPROXIMATE
    assert kf6_availability.fidelity == ReplayFidelity.APPROXIMATE
    assert "GNSS_MEASUREMENT" not in kf6_availability.missing_inputs
    replay = pure_ins.run(
        dataset,
        ReplayRequest(input_source=SOURCE_RECORDED_INCREMENT),
    )
    assert replay.fidelity == ReplayFidelity.APPROXIMATE
    assert replay.channels["navigation.position_enu"].count > 0

    export_result = FlightExporter(registry).export(
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
            include_attitude_gif=False,
            selected_channels=("imu.corrected.accel_b",),
        ),
    )
    manifest_path = export_result.ManifestPath_Get()
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["data_quality"]["crc_failure_count"] == 1_152
    assert manifest["gnss_usability"]["measurement_sample_count"] == 0
    gnss_measurement = next(
        stream
        for stream in manifest["configured_streams"]
        if stream["record_name"] == "GNSS_MEASUREMENT"
    )
    assert gnss_measurement["enabled"]
    assert gnss_measurement["recorded_sample_count"] == 0
    assert "imu.corrected.accel_b" in manifest["exported_channel_provenance"]

    application = QApplication.instance() or QApplication([])
    overview_page = OverviewPage(Translator("zh_CN"))
    explorer_page = DataExplorerPage(Translator("zh_CN"))
    overview_page.Dataset_Set(dataset)
    explorer_page.Dataset_Set(dataset)
    application.processEvents()
    assert overview_page.gnss_card.value_label.text() == "在线 · 未定位"
    assert overview_page.quality_card.property("statusLevel") == "warning"
    assert explorer_page.tabs.count() == 3
    assert explorer_page.diagnostics_table.rowCount() == len(
        diagnostics.diagnostics
    )
    measurement_index = explorer_page.record_combo.findText(
        "GNSS_MEASUREMENT"
    )
    assert measurement_index >= 0
    explorer_page.record_combo.setCurrentIndex(measurement_index)
    application.processEvents()
    assert explorer_page.record_table.rowCount() == 0
    overview_page.close()
    explorer_page.close()

    assert _Sha256_Get(log_path) == source_hash_before
    assert _Sha256_Get(package_path) == package_hash_before
