"""Revision-3 effective-gain and quality-health product regressions."""

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_policy import FusionSupervisor, NavigationHealth
from silverstar_flp.analysis.navigation_revision3 import Revision3Health_Build
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.plugins.algorithms.eskf15.replay import Measurement
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6GnssGroup, Kf6UpdateResult
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    EpochState_Restore,
    Filter_Clone,
    FixedLagReplay,
    ReplayEvent,
    ReplayResult,
)
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin, _ScheduledMeasurement
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.synthetic_parameter_navigation import NavigationPair_Open
from tests.test_kf6_outage import Filter_Create


def Update(kf, group, variance, observed=0.0):
    if group == 4:
        return kf.Kf6_UpdateBaro(observed, variance)
    return kf.Kf6_GroupUpdate(Kf6GnssGroup(group), np.full(3, observed), np.full(3, variance))


@pytest.mark.parametrize("group", range(5))
@pytest.mark.parametrize("revision", [2, 3])
def test_actual_float32_zero_gain_qualification_keeps_legacy(group, revision):
    kf = Filter_Create()
    kf.require_effective_gain = revision == 3
    kf.covariance = np.eye(6, dtype=np.float32) * np.float32(1e-8)
    before = (kf.state.copy(), kf.covariance.copy())
    outcome = Update(kf, group, np.finfo(np.float32).max)
    assert outcome == (Kf6UpdateResult.NUMERIC_ERROR if revision == 3 else Kf6UpdateResult.ACCEPTED)
    np.testing.assert_array_equal(kf.state, before[0])
    np.testing.assert_array_equal(kf.covariance, before[1])
    assert kf.counters.get("numeric_error_count", 0) == (revision == 3)
    supervisor = FusionSupervisor(1_000_000)
    supervisor.Decision_Record(
        group,
        1_100_000,
        physically_valid=True,
        result=int(outcome),
        nis=0.0,
        gain_norm=0.0,
        evaluation_us=1_200_000,
    )
    assert supervisor.groups[group].last_successful_fusion_us == 0


@pytest.mark.parametrize("group", range(5))
@pytest.mark.parametrize("variance", [1.0, 1e30])
def test_tiny_nonzero_gain_and_zero_innovation_are_real_updates(group, variance):
    kf = Filter_Create()
    kf.require_effective_gain = True
    kf.covariance = np.eye(6, dtype=np.float32) * np.float32(1e-8)
    gain = np.float32(1e-8) / np.float32(variance)
    assert gain != 0
    if variance > 1e20:
        assert np.float32(gain * gain) == 0
    assert Update(kf, group, variance) == Kf6UpdateResult.ACCEPTED
    assert kf.counters.get("numeric_error_count", 0) == 0
    np.testing.assert_array_equal(kf.state, np.zeros(6))


@pytest.mark.parametrize("bad", [np.inf, -np.inf, np.nan])
@pytest.mark.parametrize("group", range(5))
def test_nonfinite_cross_gain_rejects_before_state_or_p_mutation(group, bad):
    kf = Filter_Create()
    kf.require_effective_gain = True
    kf.covariance = np.eye(6, dtype=np.float32)
    observed_index = (0, 2, 3, 5, 2)[group]
    other_index = (5, 5, 0, 0, 5)[group]
    kf.covariance[other_index, observed_index] = bad
    before = (kf.state.copy(), kf.covariance.copy())
    expected_warning = (
        pytest.warns(RuntimeWarning, match="invalid value encountered in matmul")
        if group in (0, 2) and np.isinf(bad)
        else nullcontext()
    )
    with expected_warning:
        assert Update(kf, group, 1.0) == Kf6UpdateResult.NUMERIC_ERROR
    np.testing.assert_array_equal(kf.state, before[0])
    np.testing.assert_array_equal(kf.covariance, before[1])
    assert kf.counters["numeric_error_count"] == 1


@pytest.mark.parametrize("gain", [0.0, -1.0, np.inf, -np.inf, np.nan])
def test_supervisor_never_refreshes_success_from_invalid_gain(gain):
    supervisor = FusionSupervisor(1_000_000)
    supervisor.Decision_Record(
        0,
        1_100_000,
        physically_valid=True,
        result=0,
        nis=0.0,
        gain_norm=gain,
        evaluation_us=1_200_000,
    )
    assert supervisor.groups[0].accepted == 0
    assert supervisor.groups[0].last_successful_fusion_us == 0
    assert supervisor.Health_Get(11_000_000) == NavigationHealth.INVALID


def test_clone_checkpoint_rollback_and_epoch_restore_preserve_gain_qualification():
    state = Filter_Create()
    state.require_effective_gain = True
    assert Filter_Clone(state).require_effective_gain
    engine = FixedLagReplay(state, timestamp_us=1_000_000)
    for i in range(1, 21):
        assert engine.Predict(1_000_000 + i * 10_000, [0, 0, 0], 0.01) == ReplayResult.OK
    assert all(
        item.require_effective_gain
        for item in (engine.state, engine.tracker, *(s for _, s in engine.checkpoints))
    )
    assert (
        engine.Insert(
            ReplayEvent(1_100_000, 1_200_000, 1, 4, 1, {"relative_altitude_m": 0, "variance_m2": 1})
        )
        == ReplayResult.OK
    )
    assert (
        engine.Insert(
            ReplayEvent(1_100_000, 1_200_001, 2, 4, 2, {"relative_altitude_m": 0, "variance_m2": 1})
        )
        == ReplayResult.EPOCH_MISMATCH
    )
    assert engine.state.require_effective_gain
    snapshot = DecodedRecord(
        4,
        "ESTIMATOR",
        1,
        0,
        100,
        0,
        0,
        dict(
            replay_epoch=2,
            operation_sequence=0,
            position_enu_m=[0] * 3,
            velocity_enu_mps=[0] * 3,
            q_nb=[1, 0, 0, 0],
        ),
        0,
    )
    full = DecodedRecord(
        8,
        "KF6_FULL_P",
        0,
        0,
        101,
        0,
        0,
        {"covariance_upper_triangle": np.eye(6)[np.triu_indices(6)]},
        0,
    )
    dataset = FlightDataset(
        Path("synthetic"),
        0,
        {},
        ParserDiagnostics(),
        {"ESTIMATOR": (snapshot,), "KF6_FULL_P": (full,)},
        {},
    )
    restored, _ = EpochState_Restore(dataset, 2, state)
    assert all(
        item.require_effective_gain
        for item in (restored.state, restored.tracker, restored.checkpoints[0][1])
    )
    restored.state.require_effective_gain = False
    assert restored.Predict(10_000, [0, 0, 0], 0.01) == ReplayResult.EPOCH_MISMATCH


def Observe(supervisor, group, time, *, result=0, scale=1.0, physical=True):
    supervisor.Decision_Record(
        group,
        time,
        physically_valid=physical,
        result=result,
        nis=0.1,
        gain_norm=1 if result in (0, 1) and physical else 0,
        variance_scale=scale,
        evaluation_us=time + 10_000,
    )


@pytest.mark.parametrize("case", ["variance", "soft", "physical"])
def test_received_quality_degrades_independent_groups_before_timeout(case):
    supervisor = FusionSupervisor(1_000_000)
    assert supervisor.Health_Get(1_000_001) == NavigationHealth.WARMUP
    for group in range(5):
        Observe(supervisor, group, 1_100_000)
    assert supervisor.Health_Get(1_120_000) == NavigationHealth.HEALTHY
    for group in (1, 2):
        Observe(
            supervisor,
            group,
            1_200_000,
            result=1 if case == "soft" else 0,
            scale=3.0 if case == "variance" else 1.0,
            physical=case != "physical",
        )
    assert supervisor.Health_Get(1_220_000) == NavigationHealth.DEGRADED
    assert supervisor.Health_Get(3_220_000) == NavigationHealth.DEAD_RECKONING
    assert supervisor.Health_Get(11_220_000) == NavigationHealth.INVALID
    Observe(supervisor, 1, 11_230_000)
    assert supervisor.Health_Get(11_240_000) == NavigationHealth.INVALID


def test_nonrequired_baro_and_single_nis_rejection_do_not_redefine_overall_quality():
    supervisor = FusionSupervisor(1_000_000)
    for group in range(4):
        Observe(supervisor, group, 1_100_000)
    Observe(supervisor, 4, 1_200_000, scale=4)
    Observe(supervisor, 0, 1_200_000, result=2)
    assert supervisor.Health_Get(1_220_000) == NavigationHealth.HEALTHY
    assert supervisor.Health_Get(1_220_000, required_mask=31) == NavigationHealth.DEGRADED
    assert supervisor.groups[0].last_successful_fusion_us == 1_110_000


def test_kf_product_events_propagate_total_variance_once_to_health():
    kf = Filter_Create()
    kf.last_group_result[:] = 1
    kf.last_position_effective_variance[:] = [6, 6, 6]
    kf.last_velocity_effective_variance[:] = [6, 6, 6]
    payload = dict(
        receive_timestamp_us=1_100_000,
        position_measurement_timestamp_us=1_090_000,
        velocity_measurement_timestamp_us=1_090_000,
        valid_group_mask=15,
        position_variance_m2=[3, 3, 3],
        velocity_variance_m2ps2=[3, 3, 3],
        _quality_variance_scales=(12, 3, 3, 3),
    )
    record = DecodedRecord(0, "GNSS_MEASUREMENT", 0, 0, 1, 1_100_000, 0, payload, 0)
    events = []
    Kf6AlgorithmPlugin._MeasurementEvents_Append(
        events, kf, _ScheduledMeasurement(1_120_000, 1, "gnss", record, False), 1_120_000
    )
    assert [row["variance_scale"] for row in events] == [24, 6, 6, 6]
    updates = [
        dict(group=name, timestamp_us=1_120_000, result=1, valid=True, nis=0.1)
        for name in ("Pos EN", "Pos U", "Vel EN", "Vel U")
    ]
    health, facts = Revision3Health_Build([1_120_000], updates, events, 1_000_000)
    assert health.values.tolist() == [NavigationHealth.DEGRADED]
    assert [g["last_variance_scale"] for g in facts["fusion_groups"][:4]] == [24, 6, 6, 6]
    assert [g["last_successful_fusion_us"] for g in facts["fusion_groups"][:4]] == [1_120_000] * 4


def test_actual_baro_result_wins_over_finite_diagnostics():
    events = [
        dict(
            group="baro",
            timestamp_us=1_100_000,
            receive_timestamp_us=1_090_000,
            valid=True,
            result=4,
            effective_variance=[1.0],
            r_scale=1.0,
            variance_scale=1.0,
        )
    ]
    _, facts = Revision3Health_Build([1_100_000], [], events, 1_000_000)
    assert facts["fusion_groups"][4]["last_successful_fusion_us"] == 0
    assert facts["fusion_groups"][4]["last_result"] == 4


@pytest.mark.parametrize("revision", [2, 3])
def test_real_plugin_selects_gain_qualification_only_for_revision3(tmp_path, monkeypatch, revision):
    dataset = NavigationPair_Open(tmp_path / "input", flight_samples=21).dataset
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.kf6")
    captured = []

    def Capture(dataset, schedule, parameters, **kwargs):
        return schedule, {"window_evidence": []}

    original_init = FixedLagReplay.__init__

    def Initialize(self, state, *args, **kwargs):
        captured.append(state.require_effective_gain)
        original_init(self, state, *args, **kwargs)

    monkeypatch.setattr(plugin, "_IntegritySchedule_Apply", Capture)
    monkeypatch.setattr(FixedLagReplay, "__init__", Initialize)
    metadata = dict(dataset.semantic_context.raw_metadata)
    metadata["metadata_declarations"] = {
        **metadata.get("metadata_declarations", {}),
        "navigation_replay": {"gnss_integrity_revision": 2},
    }
    dataset = replace(
        dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata)
    )
    plugin.run(
        dataset,
        ReplayRequest(
            mode=ReplayMode.WHAT_IF, quality_policy_revision=3 if revision == 3 else None
        ),
    )
    assert captured and all(value == (revision == 3) for value in captured)


def test_eskf_real_plugin_consumes_accepted_quality_scale(tmp_path, monkeypatch):
    dataset = NavigationPair_Open(tmp_path / "input", flight_samples=21).dataset
    plugin = builtin_registry().Algorithm_Get("silverstar.algorithm.estimator.eskf15")

    def Measurements(dataset, parameters, start, end, request):
        time = start + 40_000
        events = [
            (
                time,
                g,
                Measurement(
                    (g, 1),
                    time,
                    time,
                    g,
                    np.zeros(2 if g in (0, 2) else 1),
                    np.ones(2 if g in (0, 2) else 1),
                    True,
                    quality_scale=3.0,
                ),
            )
            for g in range(4)
        ]
        return events, [], set()

    monkeypatch.setattr(plugin, "_Measurements_Build", Measurements)
    result = plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF))
    for name in ("position_en", "position_u", "velocity_en", "velocity_u"):
        assert result.channels["eskf15.update_result." + name].values.tolist() == [0]
        np.testing.assert_allclose(result.channels["eskf15.r_scale." + name].values, 3)
    assert result.channels["eskf15.navigation_health"].values[-1] == NavigationHealth.DEGRADED
    from silverstar_flp.plugins.algorithms.eskf15.plugin import _Visualization_Build

    spec = _Visualization_Build()
    assert spec.state_groups[-1].unit == "m/s\u00b2"
    assert spec.full_covariance.state_units[-3:] == ("m/s\u00b2",) * 3
    assert result.channels["eskf15.accel_bias"].unit == "m/s\u00b2"


def test_accepted_float32_roundtrip_does_not_invent_variance_degradation():
    kf = Filter_Create()
    kf.last_group_result[:] = 0
    kf.last_position_effective_variance[:] = np.float32(0.7)
    kf.last_velocity_effective_variance[:] = np.float32(0.7)
    assert float(np.float32(0.7)) / 0.7 < 1.0
    payload = dict(
        receive_timestamp_us=1_100_000,
        position_measurement_timestamp_us=1_090_000,
        velocity_measurement_timestamp_us=1_090_000,
        valid_group_mask=15,
        position_variance_m2=[0.7] * 3,
        velocity_variance_m2ps2=[0.7] * 3,
        _quality_variance_scales=(1, 1, 1, 1),
    )
    record = DecodedRecord(0, "GNSS_MEASUREMENT", 0, 0, 1, 1_100_000, 0, payload, 0)
    events = []
    Kf6AlgorithmPlugin._MeasurementEvents_Append(
        events, kf, _ScheduledMeasurement(1_120_000, 1, "gnss", record, False), 1_120_000
    )
    assert [row["variance_scale"] for row in events] == [1] * 4
    updates = [
        dict(group=name, timestamp_us=1_120_000, result=0, valid=True, nis=0.1)
        for name in ("Pos EN", "Pos U", "Vel EN", "Vel U")
    ]
    health, facts = Revision3Health_Build([1_120_000], updates, events, 1_000_000)
    assert health.values.tolist() == [NavigationHealth.HEALTHY]
    assert [g["accepted"] for g in facts["fusion_groups"][:4]] == [1] * 4


def test_native_satellite_and_window_scales_remain_separate():
    from silverstar_flp.analysis.navigation_revision3 import QualitySchedule_Apply
    from tests.test_gnss_integrity import Dataset_Build

    dataset = Dataset_Build(position_e_rate=3.0, velocity_e=0.0)
    initial = replace(
        dataset.initial_state,
        payload={**dataset.initial_state.payload, "gnss_origin_position_std_m": (0, 0, 0)},
    )
    native = tuple(
        replace(
            r,
            payload={
                **r.payload,
                "supported_fields": 1023,
                "valid_fields": 1023,
                "fix_type": 3,
                "fix_ok": 1,
                "online": 1,
                "receive_timestamp_us": r.timestamp_us,
                "satellite_count": 4,
            },
        )
        for r in dataset.Records_Get("GNSS_NATIVE")
    )
    dataset = replace(dataset, records={"INITIAL_STATE": (initial,), "GNSS_NATIVE": native})
    measurement = replace(native[-1], record_name="GNSS_MEASUREMENT")
    parameters = (
        builtin_registry().Algorithm_Get("silverstar.algorithm.kf6").OfflineParameters_Get()
    )
    schedule, evidence = QualitySchedule_Apply(
        dataset,
        (_ScheduledMeasurement(measurement.timestamp_us, 1, "gnss", measurement, False),),
        parameters,
    )
    assert evidence["window_evidence"][-1]["variance_scale"] == 4
    assert schedule[0].record.payload["_quality_variance_scales"] == (12, 3, 3, 3)
