from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from silverstar_flp.analysis.measurement_diagnostics import RecordedMeasurementChannels_Build
from silverstar_flp.core.dataset import DecodedRecord, TimeSeries
from silverstar_flp.decoder_profiles.semantic_adapter import _StableSeries_Adapt


def _Record(index=1, **overrides):
    payload = dict(
        estimator_present_timestamp_us=1_000_000 + index * 100_000,
        receive_timestamp_us=1_000_000 + index * 100_000 - 3_000,
        measurement_timestamp_us=1_000_000 + index * 100_000 - 10_000,
        valid_mask=1,
        update_result=0,
        innovation_m=0.088341847 + index,
        nis=1.0,
        variance_m2=25.0,
        relative_altitude_m=2.0,
    )
    payload.update(overrides)
    return DecodedRecord(
        0x15, "BARO_MEASUREMENT", 1, 72, index, 900_000 + index * 100_000, 1, payload, 0
    )


def _LegacySeries(field, values):
    return TimeSeries(
        np.asarray([1_050_000], dtype=np.uint64),
        np.asarray(values),
        "1",
        "diagnostic",
        "KF6_DIAGNOSTIC",
        np.asarray([True]),
        metadata={"record_name": "KF6_DIAGNOSTIC", "field_name": field},
    )


def _Adapt(records, *, legacy=False):
    diagnostic = replace(
        _Record(),
        record_name="KF6_DIAGNOSTIC",
        payload={
            "position_update_result": 0,
            "velocity_update_result": 1,
            "baro_update_result": 2,
        },
    )
    raw = {"raw.baro": _LegacySeries("baro_innovation", [99.0])} if legacy else {}
    dataset = SimpleNamespace(
        series=raw,
        Records_Get=lambda name: (
            tuple(records)
            if name == "BARO_MEASUREMENT"
            else (diagnostic,)
            if legacy and name == "KF6_DIAGNOSTIC"
            else ()
        ),
    )
    package = SimpleNamespace(semantics=SimpleNamespace(canonical_channels=()))
    return _StableSeries_Adapt(dataset, package)


def test_measurement_only_baro_diagnostics_use_actual_application_time_and_sorted_values():
    records = (_Record(2), _Record(1))
    channels, aliases = _Adapt(records)
    for suffix, values in (
        ("innovation", [1.088341847, 2.088341847]),
        ("nis", [1.0, 1.0]),
        ("update_result", [0.0, 0.0]),
    ):
        channel = "kf6.recorded." + suffix + ".baro"
        series = channels[channel]
        np.testing.assert_array_equal(series.timestamp_us, [1_100_000, 1_200_000])
        np.testing.assert_allclose(series.values, values)
        assert series.valid.tolist() == [True, True]
        assert series.source == "BARO_MEASUREMENT"
        assert series.metadata["timestamp_field"] == "estimator_present_timestamp_us"
        assert aliases[channel] == channel
    assert records[0].timestamp_us == 1_100_000
    assert "kf6.recorded.update_result" not in channels


def test_legacy_diagnostic_only_and_old_measurement_layout_keep_legacy_roles():
    old = replace(_Record(), record_version=0, payload={"relative_altitude_m": 2.0})
    for records in ((), (old,)):
        channels, aliases = _Adapt(records, legacy=True)
        assert channels["kf6.recorded.innovation.baro"].values.tolist() == [99.0]
        assert aliases["kf6.recorded.innovation.baro"] == "raw.baro"
        assert channels["kf6.recorded.update_result.baro"].values.tolist() == [2.0]


def test_measurement_stream_wins_over_diagnostic_snapshot_without_filling_holes():
    channels, _ = _Adapt((_Record(innovation_m=float("nan")),), legacy=True)
    assert channels["raw.baro"].values.tolist() == [99.0]
    assert not channels["kf6.recorded.innovation.baro"].valid.any()
    record = replace(
        _Record(),
        payload={
            key: value
            for key, value in _Record().payload.items()
            if key not in ("innovation_m", "nis")
        },
    )
    channels, _ = _Adapt((record,), legacy=True)
    assert "kf6.recorded.innovation.baro" not in channels
    assert "kf6.recorded.nis.baro" not in channels
    assert channels["kf6.recorded.update_result.baro"].values.tolist() == [0.0]


@pytest.mark.parametrize(
    "result,diagnostic_valid,result_valid",
    [
        (0, True, True),
        (1, True, True),
        (2, True, True),
        (3, False, True),
        (4, False, True),
        (255, False, False),
    ],
)
def test_result_semantics_do_not_plot_uncomputed_innovation_or_nis(
    result,
    diagnostic_valid,
    result_valid,
):
    channels, _ = _Adapt((_Record(update_result=result),))
    assert channels["kf6.recorded.innovation.baro"].valid.tolist() == [diagnostic_valid]
    assert channels["kf6.recorded.nis.baro"].valid.tolist() == [diagnostic_valid]
    assert channels["kf6.recorded.update_result.baro"].valid.tolist() == [result_valid]


@pytest.mark.parametrize(
    "overrides",
    [
        {"valid_mask": 0},
        {"estimator_present_timestamp_us": 0},
        {"innovation_m": float("nan"), "nis": float("inf")},
    ],
)
def test_invalid_measurements_have_no_valid_diagnostic_points(overrides):
    channels, _ = _Adapt((_Record(**overrides),))
    assert not channels["kf6.recorded.innovation.baro"].valid.any()
    assert not channels["kf6.recorded.nis.baro"].valid.any()


@pytest.mark.parametrize(
    "missing", ["valid_mask", "update_result", "estimator_present_timestamp_us"]
)
def test_missing_diagnostic_boundary_fields_never_invent_time_or_validity(missing):
    record = _Record()
    record = replace(
        record, payload={key: value for key, value in record.payload.items() if key != missing}
    )
    channels, _ = _Adapt((record,), legacy=True)
    assert "kf6.recorded.innovation.baro" not in channels
    assert "kf6.recorded.nis.baro" not in channels


def test_baro_variance_scale_and_ages_match_update_semantics_and_present_time():
    records = [
        _Record(index + 1, update_result=result, nis=nis)
        for index, (result, nis) in enumerate(((0, 1.0), (1, 12.0), (2, 25.0), (3, 0.0)))
    ]
    params = {"nis_1d_soft": 6.0, "nis_1d_hard": 20.0, "nis_max_r_scale": 4.0}
    channels = RecordedMeasurementChannels_Build({"BARO_MEASUREMENT": records[::-1]}, params)
    prefix = "kf6.recorded.measurement_"
    effective = channels[prefix + "effective_variance.baro"]
    np.testing.assert_array_equal(
        effective.timestamp_us, [1_100_000, 1_200_000, 1_300_000, 1_400_000]
    )
    np.testing.assert_array_equal(effective.values[:2, 0], [25.0, 50.0])
    assert effective.valid.tolist() == [True, True, False, False]
    np.testing.assert_array_equal(channels[prefix + "r_scale.baro"].values[:2], [1.0, 2.0])
    np.testing.assert_array_equal(channels[prefix + "receive_age.baro"].values, [3.0] * 4)
    np.testing.assert_array_equal(channels[prefix + "fixed_lag_latency.baro"].values, [10.0] * 4)
    assert channels[prefix + "input_variance.baro"].valid.all()
    assert effective.source == "BARO_MEASUREMENT"
    unknown = RecordedMeasurementChannels_Build({"BARO_MEASUREMENT": records}, {})
    assert not unknown[prefix + "effective_variance.baro"].valid.any()
    missing = replace(
        records[0],
        payload={key: value for key, value in records[0].payload.items() if key != "valid_mask"},
    )
    assert not RecordedMeasurementChannels_Build({"BARO_MEASUREMENT": (missing,)}, params)


def test_recomputed_baro_scalar_result_preserves_attempt_and_fault_validity():
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin, _ReplaySnapshot

    snapshots = tuple(
        _ReplaySnapshot(
            timestamp_us=1_000_000 + index,
            q_nb=np.asarray([1.0, 0.0, 0.0, 0.0]),
            state=np.zeros(6),
            covariance=np.eye(6),
            position_innovation=np.zeros(3),
            velocity_innovation=np.zeros(3),
            baro_innovation=0.25,
            position_nis=0.0,
            velocity_nis=0.0,
            group_nis=np.zeros(4),
            group_result=np.full(4, 5),
            baro_nis=1.0,
            position_result=3,
            velocity_result=3,
            baro_result=result,
            attempt_mask=attempt,
            r_scale=np.ones(3),
            position_measurement_variance=np.ones(3),
            velocity_measurement_variance=np.ones(3),
            baro_measurement_variance=25.0,
        )
        for index, (result, attempt) in enumerate(((0, 0), (0, 4), (1, 4), (2, 4), (3, 4), (4, 4)))
    )
    channels = Kf6AlgorithmPlugin._Channels_Build(snapshots)
    np.testing.assert_array_equal(
        channels["kf6.update_result.baro"].values,
        channels["kf6.update_result"].values[:, 2],
    )
    assert channels["kf6.update_result.baro"].valid.tolist() == [
        False,
        True,
        True,
        True,
        True,
        True,
    ]
    for channel in ("kf6.innovation.baro", "kf6.nis.baro"):
        assert channels[channel].valid.tolist() == [False, True, True, True, False, False]
