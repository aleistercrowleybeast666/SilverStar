"""Optional sibling integration gate: real generated C codec and numerical outputs.

Set SILVERSTAR_FCCG_GENERATED and SILVERSTAR_C_GOLDEN to explicit test artifacts.
The caller generates these with FCCG tests/joint_navigation_support.py; this test
never writes to that repository or claims validation of an actual flight log.
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


def test_generated_c_log_exact_decoder_replay_and_mechanization(tmp_path):
    project = os.environ.get('SILVERSTAR_FCCG_GENERATED')
    log = os.environ.get('SILVERSTAR_C_GOLDEN')
    if not project or not log:
        pytest.skip('explicit FCCG generated project and C golden required')
    registry = builtin_registry()
    packages = tuple(Path(project).glob("*.ssdecoder"))
    assert len(packages) == 1
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(log_path=Path(log), decoder_package_path=packages[0])
    )
    dataset = opened.dataset
    assert dataset.diagnostics.header_crc_valid
    assert dataset.diagnostics.record_crc_failures == 0
    assert dataset.diagnostics.sequence_gap_count == 0
    assert dataset.diagnostics.unknown_record_type_count == 0
    assert not dataset.diagnostics.truncated_tail
    assert (
        not {"SAMPLE", "RAW_SENSOR", "IMU_NATIVE", "HW_QUAT_NATIVE", "PURE_INS"}
        & dataset.records.keys()
    )
    plugin = registry.Algorithm_Get('silverstar.algorithm.kf6')
    assert plugin.availability(dataset).available
    result = plugin.run(dataset, ReplayRequest())
    integrity = result.diagnostics.get("gnss_integrity")
    assert integrity and integrity["revision"] == 2
    assert integrity["recorded_mask_mismatches"] == 0
    assert integrity["recorded_r_mismatches"] == 0
    what_if = plugin.run(dataset, ReplayRequest(
        mode=ReplayMode.WHAT_IF,
        parameters={"gnss_integrity_error_threshold_m": 20.0},
    ))
    assert what_if.diagnostics["gnss_integrity"]["position_disabled_count"] < (
        integrity["position_disabled_count"]
    )
    from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build
    decisions = GnssIntegrityStream_Build(dataset, result.parameters, consumed_only=True)
    for record in dataset.Records_Get("GNSS_MEASUREMENT"):
        key = (int(record.payload["sequence"]), int(record.payload["receive_timestamp_us"]))
        decision = decisions.by_measurement[key]
        assert record.payload["valid_group_mask"] == decision.admitted_mask
        if record.payload["valid_group_mask"] & 1:
            np.testing.assert_allclose(
                record.payload["position_variance_m2"][:2],
                np.full(2, 6.25 * decision.position_r_scale), rtol=1e-6,
            )
    measurements = dataset.Records_Get("GNSS_MEASUREMENT")
    pos_en_updates = [
        row for row in result.diagnostics["gnss_group_updates"]
        if row["group"] == "Pos EN"
    ]
    assert len(pos_en_updates) == len(measurements)
    for record, update in zip(measurements, pos_en_updates, strict=True):
        assert record.timestamp_us == update["timestamp_us"]
        assert int(record.payload["group_update_result"][0]) == int(update["result"])
        np.testing.assert_allclose(
            record.payload["group_nis"][0], update["nis"],
            rtol=1e-6, atol=1e-6, equal_nan=True,
        )
    events = [row for row in dataset.Records_Get("EVENT")
              if int(row.payload["event_id"]) == 0x2E]
    assert len(events) == len(integrity["transitions"])
    for event, (timestamp, before, after, reason, sequence) in zip(
        events, integrity["transitions"], strict=True
    ):
        arg0 = int(event.payload["arg0"])
        assert event.timestamp_us == timestamp
        assert event.payload["arg1"] == sequence
        assert (arg0 & 0xFF, (arg0 >> 8) & 0xFF,
                (arg0 >> 16) & 0xFF) == (before, after, reason)
    assert (
        result.fidelity == ReplayFidelity.APPROXIMATE
    )  # Bounded tested scope, no universal EXACT.
    assert not result.diagnostics['measurement_timing_inferred']
    assert not result.diagnostics['execution_mismatches']
    verification = result.diagnostics['mechanization_verification']
    assert verification['passed'] and verification['first_divergence'] is None
    assert verification['calibration_applied'] is False
    for role, name, field in [
        ('navigation.position_enu','ESTIMATOR','position_enu_m'),
        ('navigation.velocity_enu','ESTIMATOR','velocity_enu_mps'),
        ('attitude.q_nb','ESTIMATOR','q_nb'),
        ('kf6.covariance.upper_triangle','KF6_FULL_P','covariance_upper_triangle')]:
        actual = result.channels[role]
        expected = {r.timestamp_us:r.payload[field] for r in dataset.Records_Get(name)}
        np.testing.assert_allclose(actual.values, [expected[int(t)] for t in actual.timestamp_us],
                                   rtol=1e-6, atol=5e-7)

    exported = FlightExporter().export(
        dataset, tmp_path / "export",
        options=ExportOptions(
            language=ExportLanguage.EN, include_overview=False,
            include_diagnostics=False, include_events=False, include_csv=False,
            include_full_covariance_keyframes=False, include_plots=True,
            include_trajectory_3d=False, include_attitude_gif=False,
            page_mode="Full",
        ),
    )
    names = {path.name for path in exported.files}
    for kind in (
        "GNSS_Horizontal_Consistency_Error",
        "GNSS_Vertical_Consistency_Error",
        "GNSS_Receiver_Information",
    ):
        assert any(kind in name for name in names)
    assert not any("GNSS_Position_Vs_Integrated_Velocity" in name for name in names)
    labels = {item.localized_name for item in exported.generated
              if item.item_id.startswith("gnss_integrity:")}
    assert labels == {
        "GNSS Horizontal Consistency Error",
        "GNSS Vertical Consistency Error",
        "GNSS Receiver Information",
    }

    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.navigation_diagnostics import NavigationDiagnostics

    application = QApplication.instance() or QApplication([])
    landing = NavigationDiagnostics("landing", Translator("en_US"))
    landing.Dataset_Set(dataset, ChannelResolver(dataset, ReplayResultStore()))
    landing.TimeRange_Set(0.0, 30.0)
    assert landing.model.rowCount() == len(dataset.Records_Get("LANDING_DIAGNOSTIC")) == 0
    assert landing.table.isHidden()
    assert "no recorded landing diagnostics" in landing.note.text().lower()
    landing.close()
    application.processEvents()
