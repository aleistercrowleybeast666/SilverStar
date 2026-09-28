"""Causal counterexamples required by joint prompt 22.1 and 22.2."""

import json
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_policy import (
    FusionSupervisor,
    NavigationHealth,
    StaggeredWindows,
)
from silverstar_flp.plugins.algorithms.eskf15.filter import (
    Covariance_Validate,
    Eskf15Filter,
    EskfState,
    EskfUpdateResult,
    Rotation_Exp,
)
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, DelayedReplay, Measurement


@pytest.mark.parametrize("gnss_hz", [10, 25])
def test_analytic_strong_acceleration_multiaxis_rotation_at_two_gnss_rates(gnss_hz):
    omega = np.array([0.7, -0.5, 0.4])
    axis = omega / np.linalg.norm(omega)
    skew = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])

    def BodyForce(time, navigation_accel):
        angle = np.linalg.norm(omega) * time
        rotation = np.eye(3) + np.sin(angle) * skew + (1 - np.cos(angle)) * (skew @ skew)
        return rotation.T @ (navigation_accel + np.array([0.0, 0.0, 9.78]))

    truth_position, truth_velocity = np.zeros(3), np.array([4.0, 2.0, 1.0])
    kernel = Eskf15Filter(EskfState(v=truth_velocity.copy()))
    accepted = 0
    for step in range(500):
        t = step * 0.02
        acceleration = np.array([12.0, -8.0, 6.0]) * (1 if step < 250 else -1)
        kernel.Prediction_ApplyPair(
            omega,
            BodyForce(t + 0.005, acceleration),
            0.01,
            omega,
            BodyForce(t + 0.015, acceleration),
            0.01,
        )
        truth_position += truth_velocity * 0.02 + 0.5 * acceleration * 0.02**2
        truth_velocity += acceleration * 0.02
        if (step + 1) % (50 // gnss_hz):
            continue
        for kind, axes in (
            ("position", (0, 1)),
            ("position", (2,)),
            ("velocity", (0, 1)),
            ("velocity", (2,)),
        ):
            observed = truth_position if kind == "position" else truth_velocity
            result = kernel.Measurement_Apply(
                kind,
                axes,
                observed[list(axes)],
                np.ones(len(axes)) * (1.5**2 if kind == "position" else 0.15**2),
            )
            assert result.result in (EskfUpdateResult.ACCEPTED, EskfUpdateResult.SOFT_WEIGHTED)
            accepted += 1
    assert accepted == 10 * gnss_hz * 4
    np.testing.assert_allclose(kernel.state.p, truth_position, atol=0.1)
    np.testing.assert_allclose(kernel.state.v, truth_velocity, atol=0.05)
    Covariance_Validate(kernel.state.covariance)


@pytest.mark.parametrize("flag", [0x02, 0x10, 0x20, 0x40])
def test_hard_imu_quality_and_runtime_history_reset_never_commit(flag):
    engine = DelayedReplay(Eskf15Filter(), 1_000_000)
    body = BodyStep(
        1_000_000,
        1_010_000,
        np.zeros(3),
        np.array([0.0, 0.0, 9.78]),
        np.zeros(3),
        np.array([0.0, 0.0, 9.78]),
        quality_flags=flag,
    )
    before = engine.kernel.state.State_Clone()
    with pytest.raises(ValueError, match="quality_hard"):
        engine.Body_Receive(body)
    assert engine.present_us == 1_000_000 and not engine.steps
    np.testing.assert_array_equal(engine.kernel.state.covariance, before.covariance)
    engine.Body_Receive(replace(body, quality_flags=0))
    with pytest.raises(ValueError, match="history_reset_requires"):
        engine.Body_Receive(replace(body, start_us=1_010_000, end_us=1_020_000, quality_flags=8))


@pytest.mark.parametrize("case,seconds", [("velocity_bias", 600), ("position_drift", 300)])
def test_long_causal_native_counterexamples_drive_actual_filter(case, seconds, tmp_path):
    kernel = Eskf15Filter()
    window = StaggeredWindows()
    supervisor = FusionSupervisor(1_000_000)
    accepted = rejected = soft = 0
    evidence = []
    max_scale = 1.0
    for step in range(1, seconds * 50 + 1):
        epoch = 1_000_000 + step * 20_000
        kernel.Prediction_Apply(np.zeros(3), np.array([0.0, 0.0, 9.78]), 0.02)
        if step % 5:
            continue
        elapsed = step * 0.02
        # Synthetic causal inputs only; future/endpoint truth is never used by the filter.
        position = (
            np.array([0.0, 0.0]) if case == "velocity_bias" else np.array([1.2 * elapsed, 0.0])
        )
        velocity = np.array([0.2, 0.0]) if case == "velocity_bias" else np.zeros(2)
        evidence.extend(
            window.Sample_Receive(
                epoch,
                position,
                velocity,
                position_valid=True,
                velocity_valid=True,
                sequence=step // 5,
            )
        )
        scale = window.VarianceScale_Get(epoch)
        max_scale = max(max_scale, scale)
        for group, kind, axes, value, variance in (
            (0, "position", (0, 1), position, np.ones(2) * 2.25 * scale),
            (1, "position", (2,), np.zeros(1), np.ones(1) * 6.25),
            (2, "velocity", (0, 1), velocity, np.ones(2) * 0.15**2),
            (3, "velocity", (2,), np.zeros(1), np.ones(1) * 0.15**2),
        ):
            result = kernel.Measurement_Apply(kind, axes, value, variance)
            supervisor.Decision_Record(
                group,
                epoch,
                physically_valid=True,
                result=int(result.result),
                nis=result.nis,
                gain_norm=result.gain_norm,
            )
            if group == 0:
                accepted += result.result in (
                    EskfUpdateResult.ACCEPTED,
                    EskfUpdateResult.SOFT_WEIGHTED,
                )
                rejected += result.result == EskfUpdateResult.REJECTED_NIS
                soft += scale > 1
        if step % 250 == 0:
            Covariance_Validate(kernel.state.covariance)
    assert evidence and all(w.valid for w in evidence)
    assert np.isfinite(kernel.state.p).all()
    if case == "velocity_bias":
        assert all(abs(w.closure_en[0] + 2.0) < 1e-8 for w in evidence)
        assert max_scale == 1.0
        assert accepted > seconds * 9
        assert supervisor.groups[0].last_successful_fusion_us == epoch
    else:
        assert max_scale == pytest.approx(1.44, abs=1e-9)
        assert soft > 2000
        # Internal inconsistency cannot establish which receiver field is true.
        assert accepted + rejected == seconds * 10
        assert supervisor.Health_Get(epoch) != NavigationHealth.HEALTHY or rejected == 0
    (tmp_path / (case + ".json")).write_text(
        json.dumps(
            {
                "duration_s": seconds,
                "prediction_epochs": seconds * 50,
                "position_accepted": int(accepted),
                "position_nis_rejected": int(rejected),
                "weighted_position_attempts": int(soft),
                "completed_windows": len(evidence),
                "maximum_variance_scale": max_scale,
                "final_health": int(supervisor.Health_Get(epoch)),
                "endpoint_output_m": kernel.state.p.tolist(),
            },
            indent=2,
        ),
        encoding="utf8",
    )


def test_bad_baro_prediction_and_four_groups_remain_independent():
    kernel = Eskf15Filter(EskfState(p=np.array([0.0, 0.0, 1000.0])))
    supervisor = FusionSupervisor(1_000_000)
    before = kernel.state.covariance.copy()
    for step in range(1, 601):
        epoch = 1_000_000 + step * 20_000
        kernel.Prediction_Apply(np.zeros(3), np.array([0.0, 0.0, 9.78]), 0.02)
        if step % 5:
            continue
        for group, kind, axes, value in (
            (0, "position", (0, 1), np.zeros(2)),
            (1, "position", (2,), np.zeros(1)),
            (2, "velocity", (0, 1), np.ones(2) * 1000),
            (3, "velocity", (2,), np.zeros(1)),
            (4, "position", (2,), np.zeros(1)),
        ):
            result = kernel.Measurement_Apply(kind, axes, value, np.ones(len(axes)))
            expected = (
                EskfUpdateResult.ACCEPTED if group in (0, 3) else EskfUpdateResult.REJECTED_NIS
            )
            assert result.result == expected
            supervisor.Decision_Record(
                group,
                epoch,
                physically_valid=True,
                result=int(result.result),
                nis=result.nis,
                gain_norm=result.gain_norm,
            )
    assert supervisor.groups[0].accepted == 120 and supervisor.groups[3].accepted == 120
    assert all(supervisor.groups[g].nis_rejected == 120 for g in (1, 2, 4))
    assert supervisor.Health_Get(epoch, 1 << 4) == NavigationHealth.INVALID
    assert supervisor.Health_Get(epoch) == NavigationHealth.INVALID
    assert kernel.state.covariance[2, 2] > before[2, 2]
    assert kernel.state.p[2] > 900  # No blind reanchor or forced barometer fusion.
    Covariance_Validate(kernel.state.covariance)


def test_small_tilt_and_observable_residual_bias_recovery():
    kernel = Eskf15Filter(EskfState(q=Rotation_Exp(np.array([0.03, -0.02, 0.0]))))
    gyro_bias = np.array([0.002, -0.003, 0.0])
    accel_bias = np.array([0.0, 0.0, 0.1])
    for step in range(3000):
        kernel.Prediction_Apply(gyro_bias, np.array([0.0, 0.0, 9.78]) + accel_bias, 0.02)
        if step % 5:
            continue
        for kind, axes in (
            ("position", (0, 1)),
            ("position", (2,)),
            ("velocity", (0, 1)),
            ("velocity", (2,)),
        ):
            kernel.Measurement_Apply(
                kind,
                axes,
                np.zeros(len(axes)),
                np.ones(len(axes)) * (0.1 if kind == "velocity" else 1.0),
            )
    assert np.linalg.norm(kernel.state.bg[:2] - gyro_bias[:2]) < 0.0005
    assert abs(kernel.state.ba[2] - 0.1) < 0.02
    assert np.linalg.norm(kernel.state.q[1:3]) < 0.012
    assert np.linalg.norm(kernel.state.v) < 0.05
    # Static yaw / horizontal bias-tilt separation is not declared observable.


def test_severe_tilt_with_valid_aids_cannot_remain_healthy_and_bad_p_rejects():
    kernel = Eskf15Filter(EskfState(q=Rotation_Exp(np.array([1.15, 0.0, 0.0]))))
    supervisor = FusionSupervisor(1_000_000)
    rejected = 0
    for index in range(600):
        kernel.Prediction_Apply(np.zeros(3), np.array([0.0, 0.0, 9.78]), 0.02)
        if index % 5:
            continue
        timestamp = 1_000_000 + (index + 1) * 20_000
        for group, kind, axes in ((0, "position", (0, 1)), (2, "velocity", (0, 1))):
            result = kernel.Measurement_Apply(kind, axes, np.zeros(2), np.ones(2) * 0.0225)
            rejected += result.result in (
                EskfUpdateResult.REJECTED_NIS,
                EskfUpdateResult.MODEL_MISMATCH,
            )
            supervisor.Decision_Record(
                group,
                timestamp,
                physically_valid=True,
                result=int(result.result),
                nis=result.nis,
                gain_norm=result.gain_norm,
            )
    assert rejected > 0
    assert supervisor.model_mismatch_latched
    assert supervisor.Health_Get(13_000_000, required_mask=0x05) == NavigationHealth.INVALID
    for value in (-1.0, np.nan):
        covariance = np.eye(15)
        covariance[0, 0] = value
        with pytest.raises(ValueError):
            Eskf15Filter(EskfState(covariance=covariance))


def test_constant_velocity_and_isolated_position_jump():
    kernel = Eskf15Filter(EskfState(v=np.array([3.0, -2.0, 1.0])))
    for _index in range(500):
        kernel.Prediction_Apply(np.zeros(3), np.array([0.0, 0.0, 9.78]), 0.02)
    np.testing.assert_allclose(kernel.state.p, [30.0, -20.0, 10.0], atol=1e-10)
    before = kernel.state.State_Clone()
    result = kernel.Measurement_Apply("position", (0, 1), np.array([1000.0, -1000.0]), np.ones(2))
    assert result.result == EskfUpdateResult.REJECTED_NIS
    np.testing.assert_array_equal(kernel.state.p, before.p)
    np.testing.assert_array_equal(kernel.state.covariance, before.covariance)


def test_replay_capacity_and_callback_failure_are_atomic(monkeypatch):
    engine = DelayedReplay(Eskf15Filter(), 1_000_000, max_steps=1)
    body = BodyStep(
        1_000_000,
        1_010_000,
        np.zeros(3),
        np.array([0.0, 0.0, 9.78]),
        np.zeros(3),
        np.array([0.0, 0.0, 9.78]),
    )
    engine.Body_Receive(body)
    before = engine.kernel.state.State_Clone()
    with pytest.raises(ValueError, match="history_capacity"):
        engine.Body_Receive(replace(body, start_us=1_010_000, end_us=1_020_000))
    assert engine.present_us == 1_010_000 and len(engine.steps) == 1
    np.testing.assert_array_equal(engine.kernel.state.covariance, before.covariance)
    item = Measurement((1, 0), 1_005_000, 1_010_000, 0, np.zeros(2), np.ones(2), True)

    def Fail(_measurement):
        raise RuntimeError("injected_callback_failure")

    monkeypatch.setattr(engine, "_Measurement_Apply", Fail)
    with pytest.raises(RuntimeError, match="injected_callback_failure"):
        engine.Measurement_Receive(item)
    for name in ("p", "v", "q", "bg", "ba", "covariance"):
        np.testing.assert_array_equal(getattr(engine.kernel.state, name), getattr(before, name))
    assert not engine.measurements and not engine.results


def test_replay_step_limit_and_all_aids_invalid_are_explicit():
    engine = DelayedReplay(Eskf15Filter(), 1_000_000, max_replay_steps=1)
    for index in range(2):
        t = 1_000_000 + index * 10_000
        engine.Body_Receive(
            BodyStep(
                t,
                t + 10_000,
                np.zeros(3),
                np.array([0.0, 0.0, 9.78]),
                np.zeros(3),
                np.array([0.0, 0.0, 9.78]),
            )
        )
    before = engine.kernel.state.State_Clone()
    with pytest.raises(ValueError, match="step_limit"):
        engine.Measurement_Receive(
            Measurement((1, 0), 1_005_000, 1_020_000, 0, np.zeros(2), np.ones(2), True)
        )
    np.testing.assert_array_equal(engine.kernel.state.covariance, before.covariance)
    kernel = Eskf15Filter()
    supervisor = FusionSupervisor(1_000_000)
    variance_before = kernel.state.covariance[0, 0]
    for index in range(600):
        kernel.Prediction_Apply(np.zeros(3), np.array([0.0, 0.0, 9.78]), 0.02)
        timestamp = 1_000_000 + (index + 1) * 20_000
        result = kernel.Measurement_Apply(
            "position", (0, 1), np.zeros(2), np.ones(2), physically_valid=False
        )
        assert result.result == EskfUpdateResult.REJECTED_INVALID
        supervisor.Decision_Record(
            0,
            timestamp,
            physically_valid=False,
            result=int(result.result),
            nis=result.nis,
            gain_norm=result.gain_norm,
        )
    assert supervisor.Health_Get(timestamp) == NavigationHealth.INVALID
    assert supervisor.groups[0].accepted == 0
    assert kernel.state.covariance[0, 0] > variance_before


def test_delayed_three_group_arrival_permutation_repropagates_bias_and_rejects_body_identity():
    engines = [DelayedReplay(Eskf15Filter(), 1_000_000) for _ in range(2)]
    events = [
        Measurement(
            (index, group),
            time,
            1_500_000,
            group,
            np.ones(dimension) * 0.2,
            np.ones(dimension),
            True,
        )
        for index, (group, time, dimension) in enumerate(
            ((0, 1_110_000, 2), (2, 1_170_000, 2), (4, 1_140_000, 1))
        )
    ]
    for index in range(50):
        begin = 1_000_000 + index * 10_000
        step = BodyStep(
            begin,
            begin + 10_000,
            np.array([0.01, -0.02, 0.01]),
            np.array([0.05, -0.03, 9.8]),
            np.array([0.01, -0.02, 0.01]),
            np.array([0.05, -0.03, 9.8]),
        )
        for engine in engines:
            engine.Body_Receive(step)
        for event in events:
            if event.timestamp_us == step.end_us:
                engines[0].Measurement_Receive(replace(event, receive_us=event.timestamp_us))
    for event in (events[1], events[2], events[0]):
        engines[1].Measurement_Receive(event)
    for field in ("p", "v", "q", "bg", "ba", "covariance"):
        np.testing.assert_allclose(
            getattr(engines[0].kernel.state, field),
            getattr(engines[1].kernel.state, field),
            atol=1e-12,
        )
    before = engines[1].kernel.state.State_Clone()
    for change in ({"source": 1}, {"generation": 1}):
        with pytest.raises(ValueError, match="source_generation"):
            engines[1].Body_Receive(replace(step, start_us=1_500_000, end_us=1_510_000, **change))
        np.testing.assert_array_equal(engines[1].kernel.state.covariance, before.covariance)
