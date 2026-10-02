"""Synthetic actual-C producer → exact generated decoder → ESKF product replay."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.algorithms.eskf15.verification import RecordedParity_Verify
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.fccg_source_fixture import FccgCommon_RootGet


@pytest.mark.parametrize("interleaved", [False, True])
def test_actual_c_producer_exact_decoder_and_15_state_replay(tmp_path, interleaved):
    root_value = os.environ.get("SILVERSTAR_FCCG_ROOT")
    project_value = os.environ.get("SILVERSTAR_ESKF_GENERATED")
    if not root_value or not project_value:
        pytest.skip("explicit actual FCCG source and generated ESKF project required")
    root, project = Path(root_value), Path(project_value)
    builtin = root / "plugins/builtin"
    core = builtin / "silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
    protocol = builtin / "silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG"
    common = FccgCommon_RootGet(root)
    decoder = next(project.glob("*.ssdecoder"))
    captured = tmp_path / decoder.name
    shutil.copy2(decoder, captured)
    for relative in (
        "Generated/Src/project_log_decoder_profile.c",
        "Generated/Inc/project_log_decoder_profile.h",
        "Generated/Inc/project_algorithm_parameters.h",
    ):
        shutil.copy2(project / relative, tmp_path / Path(relative).name)
    executable = tmp_path / "producer.exe"
    command = [
        shutil.which("gcc"),
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(tmp_path),
        "-I",
        str(core / "Inc"),
        "-I",
        str(protocol / "Inc"),
        "-I",
        str(common / "Inc"),
        "-include",
        str(tmp_path / "project_algorithm_parameters.h"),
        str(Path(__file__).parent / "fixtures/eskf15_producer.c"),
        str(core / "Src/navigation_eskf.c"),
        str(protocol / "Src/sslog_records.c"),
        str(protocol / "Src/sslog_protocol.c"),
        str(common / "Src/silverstar_assert.c"),
        str(tmp_path / "project_log_decoder_profile.c"),
        "-o",
        str(executable),
        "-lm",
    ]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    built = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert built.returncode == 0, built.stderr
    log = tmp_path / "SYNTHETIC_C_ESKF15.BIN"
    made = subprocess.run(
        [str(executable), str(log)] + (["interleaved"] if interleaved else []),
        capture_output=True,
        text=True,
    )
    assert made.returncode == 0, made.stdout + made.stderr
    before = hashlib.sha256(log.read_bytes()).hexdigest()
    registry = builtin_registry()
    opened = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / "cache")).Open(
        LogOpenRequest(log_path=log, decoder_package_path=captured)
    )
    dataset = opened.dataset
    assert dataset.diagnostics.record_crc_failures == 0
    assert dataset.diagnostics.sequence_gap_count == 0
    assert not dataset.diagnostics.truncated_tail
    assert len(dataset.Records_Get("ESKF15_BODY_INPUT")) == 100
    assert len(dataset.Records_Get("ESKF15_MEASUREMENT")) == 50
    if interleaved:
        parts = dataset.Records_Get("ESKF15_FULL_P_PART")
        next_body = dataset.Records_Get("ESKF15_BODY_INPUT")[1]
        assert parts[3].record_sequence > next_body.record_sequence
        assert parts[3].timestamp_us < dataset.Records_Get("ESKF15_BODY_INPUT")[1].timestamp_us
    plugin = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15")
    assert plugin.FirmwareMember_Is(dataset)
    result = plugin.run(dataset, ReplayRequest())
    assert not result.missing_inputs
    assert result.fidelity == ReplayFidelity.EXACT, result.diagnostics.get("recorded_parity")
    assert result.diagnostics["replay_claim"] == "FAITHFUL"
    # An unattempted operation has no numeric innovation/NIS/effective R. Match
    # its explicit admission/result first; never hide attempted differences.
    unavailable_series, unavailable_channels = dict(dataset.series), dict(result.channels)
    for quantity, expected, actual in (
        ("admitted", 0, 0),
        ("update_result", 3, 3),
        ("innovation", 0, np.nan),
        ("nis", 0, np.nan),
        ("effective_variance", 0, 2.25),
    ):
        channel_id = f"eskf15.{quantity}.position_en"
        recorded_id = f"eskf15.recorded.{quantity}.position_en"
        for collection, key, value in (
            (unavailable_series, recorded_id, expected),
            (unavailable_channels, channel_id, actual),
        ):
            channel = collection[key]
            values = channel.values.copy()
            values[0] = value
            collection[key] = replace(channel, values=values)
    unattempted = replace(dataset, series=unavailable_series)
    checked = RecordedParity_Verify(unattempted, unavailable_channels)
    assert checked["passed"]
    assert checked["unattempted_diagnostic_rows_unavailable"]["eskf15.nis.position_en"] == 1
    key = "eskf15.admitted.position_en"
    channel = unavailable_channels[key]
    values = channel.values.copy()
    values[0] = 1
    assert not RecordedParity_Verify(
        unattempted, {**unavailable_channels, key: replace(channel, values=values)}
    )["passed"]
    without_legacy = replace(
        dataset,
        records={
            name: rows
            for name, rows in dataset.records.items()
            if name not in ("INITIAL_STATE", "ALIGNMENT_RESULT")
        },
    )
    assert plugin.run(without_legacy, ReplayRequest()).diagnostics["replay_claim"] == "FAITHFUL"
    records = dataset.Records_Get("ESKF15_MEASUREMENT")
    bad_record = replace(
        records[0],
        payload={
            **records[0].payload,
            "calibration_generation": records[0].payload["calibration_generation"] + 1,
        },
    )
    mismatched = replace(
        dataset, records={**dataset.records, "ESKF15_MEASUREMENT": (bad_record, *records[1:])}
    )
    with pytest.raises(ValueError, match="epoch_or_calibration_identity_mismatch"):
        plugin.run(mismatched, ReplayRequest())
    altered = dict(result.channels)
    channel = altered["eskf15.gyro_bias"]
    values = channel.values.copy()
    values[9, 1] += 0.1
    altered["eskf15.gyro_bias"] = replace(channel, values=values)
    rejected = RecordedParity_Verify(dataset, altered)
    assert not rejected["passed"]
    assert rejected["first_difference"]["channel"] == "eskf15.gyro_bias"
    assert rejected["first_difference"]["timestamp_us"] == int(channel.timestamp_us[9])
    incomplete = replace(
        dataset,
        series={
            k: v
            for k, v in dataset.series.items()
            if k != "eskf15.recorded.covariance.upper_triangle"
        },
    )
    assert not RecordedParity_Verify(incomplete, result.channels)["passed"]
    without_periodic = replace(
        incomplete,
        records={
            name: records
            for name, records in dataset.records.items()
            if name != "ESKF15_FULL_P_PART"
        },
    )

    def PeriodicPolicy(enabled):
        context = replace(
            dataset.semantic_context,
            logging_streams=tuple(
                {**row, "enabled": enabled}
                if str(row.get("record", "")).removeprefix("FLIGHT_LOG_RECORD_")
                == "ESKF15_FULL_P_PART"
                else row
                for row in dataset.semantic_context.logging_streams
            ),
        )
        return replace(without_periodic, semantic_context=context)

    flight_parity = RecordedParity_Verify(PeriodicPolicy(False), result.channels)
    assert flight_parity["passed"]
    assert flight_parity["cross_covariance_comparison"].startswith("unavailable")
    assert not RecordedParity_Verify(PeriodicPolicy(True), result.channels)["passed"]
    unknown = replace(
        without_periodic,
        semantic_context=replace(
            dataset.semantic_context,
            logging_streams=tuple(
                row
                for row in dataset.semantic_context.logging_streams
                if str(row.get("record", "")).removeprefix("FLIGHT_LOG_RECORD_")
                != "ESKF15_FULL_P_PART"
            ),
        ),
    )
    assert not RecordedParity_Verify(unknown, result.channels)["passed"]
    broken = replace(
        PeriodicPolicy(False),
        metadata={
            **dataset.metadata,
            "eskf15_covariance_diagnostics": [{"reason": "missing_or_duplicate_part"}],
        },
    )
    assert not RecordedParity_Verify(broken, result.channels)["passed"]
    maximum = {}
    for channel in (
        "navigation.position_enu",
        "navigation.velocity_enu",
        "attitude.q_nb",
        "eskf15.gyro_bias",
        "eskf15.accel_bias",
        "eskf15.covariance.diagonal",
        "eskf15.covariance.upper_triangle",
    ):
        prefix = channel.removeprefix("eskf15.")
        recorded = dataset.Series_Get("eskf15.recorded." + prefix)
        assert recorded is not None, channel
        reference = result.channels[channel]
        np.testing.assert_array_equal(reference.timestamp_us, recorded.timestamp_us)
        maximum[channel] = float(np.max(np.abs(reference.values - recorded.values)))
        np.testing.assert_allclose(reference.values, recorded.values, atol=2e-4, rtol=3e-4)
    assert hashlib.sha256(log.read_bytes()).hexdigest() == before
    (tmp_path / "golden_result.json").write_text(
        json.dumps(
            {
                "origin": "synthetic Host actual C producer; never flight data",
                "input_sha256": before,
                "decoder_sha256": hashlib.sha256(captured.read_bytes()).hexdigest(),
                "maximum_absolute_error": maximum,
                "records": sum(len(records) for records in dataset.records.values()),
            },
            indent=2,
        ),
        encoding="utf8",
    )
