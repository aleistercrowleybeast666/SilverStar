from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_policy import (
    FusionSupervisor,
    GnssQuality_VarianceScale,
    NavigationHealth,
    StaggeredWindows,
)
from silverstar_flp.plugins.algorithms.eskf15.filter import (
    Covariance_Validate,
    Eskf15Filter,
    EskfState,
    EskfUpdateResult,
    Quaternion_Matrix,
    Quaternion_Multiply,
    Rotation_Exp,
    Rotation_RightJacobian,
)
from silverstar_flp.plugins.algorithms.eskf15.plugin import Native_PhysicalMask
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, DelayedReplay, Measurement


def _Log(q):
    q = np.asarray(q)
    if q[0] < 0:
        q = -q
    sine = np.linalg.norm(q[1:])
    return 2 * q[1:] if sine < 1e-12 else q[1:] * (2 * np.arctan2(sine, q[0]) / sine)


def _Conjugate(q):
    return np.r_[q[0], -q[1:]]


def test_stationary_gravity_and_bias_prediction():
    state = EskfState(bg=np.array([0.02, -0.01, 0.005]), ba=np.array([0.1, -0.2, 0.03]))
    kernel = Eskf15Filter(state)
    for _ in range(300):
        kernel.Prediction_Apply(state.bg, np.array([0, 0, 9.78]) + state.ba, 0.01)
    np.testing.assert_allclose(kernel.state.p, 0, atol=1e-12)
    np.testing.assert_allclose(kernel.state.v, 0, atol=1e-12)
    np.testing.assert_allclose(kernel.state.q, [1, 0, 0, 0], atol=1e-12)
    Covariance_Validate(kernel.state.covariance)


@pytest.mark.parametrize("angle", [0.0, 1e-8, 0.25, np.pi - 0.0001])
def test_right_reset_jacobian_independent_finite_difference(angle):
    a = np.array([0.2, -0.7, 0.3])
    a *= angle / np.linalg.norm(a)
    jacobian = np.zeros((3, 3))
    epsilon = 1e-7
    for i in range(3):
        perturb = np.eye(3)[i] * epsilon
        plus = _Log(Quaternion_Multiply(_Conjugate(Rotation_Exp(a)), Rotation_Exp(a + perturb)))
        minus = _Log(Quaternion_Multiply(_Conjugate(Rotation_Exp(a)), Rotation_Exp(a - perturb)))
        jacobian[:, i] = (plus - minus) / (2 * epsilon)
    np.testing.assert_allclose(Rotation_RightJacobian(a), jacobian, atol=5e-9, rtol=1e-7)


@pytest.mark.parametrize("kind", ["position", "velocity"])
@pytest.mark.parametrize("lever", [np.zeros(3), np.array([0.2, -0.3, 0.5])])
def test_measurement_jacobian_independent_finite_difference(kind, lever):
    kernel = Eskf15Filter(EskfState(q=Rotation_Exp(np.array([0.4, -0.2, 0.5]))))
    kernel.last_omega = np.array([0.3, -0.2, 0.1])
    _, h = kernel.Measurement_Model(kind, (0, 1, 2), lever)
    numerical = np.zeros((3, 15))
    epsilon = 1e-6
    for axis in range(15):
        values = []
        for sign in (-1, 1):
            dx = np.eye(15)[axis] * epsilon * sign
            rotation = Quaternion_Matrix(Quaternion_Multiply(kernel.state.q, Rotation_Exp(dx[6:9])))
            value = (
                kernel.state.p + dx[:3] + rotation @ lever
                if kind == "position"
                else kernel.state.v
                + dx[3:6]
                + rotation @ np.cross(kernel.last_omega - dx[9:12], lever)
            )
            values.append(value)
        numerical[:, axis] = (values[1] - values[0]) / (2 * epsilon)
    np.testing.assert_allclose(h, numerical, atol=2e-10)


def test_continuous_dynamics_jacobian_independent_finite_difference():
    kernel = Eskf15Filter(EskfState(q=Rotation_Exp(np.array([0.2, -0.3, 0.4]))))
    w, a = np.array([0.7, -0.5, 0.4]), np.array([2.0, -1.0, 8.0])
    expected = kernel.Dynamics_Jacobian(w, a)
    numerical = np.zeros((15, 15))
    epsilon, dt = 1e-5, 1e-6
    nominal_next = Quaternion_Multiply(kernel.state.q, Rotation_Exp(w * dt))
    for axis in range(15):
        derivatives = []
        for sign in (-1, 1):
            error = np.eye(15)[axis] * epsilon * sign
            true_q = Quaternion_Multiply(kernel.state.q, Rotation_Exp(error[6:9]))
            true_next = Quaternion_Multiply(true_q, Rotation_Exp((w - error[9:12]) * dt))
            theta_next = _Log(Quaternion_Multiply(_Conjugate(nominal_next), true_next))
            acceleration = (
                Quaternion_Matrix(true_q) @ (a - error[12:15])
                - Quaternion_Matrix(kernel.state.q) @ a
            )
            derivatives.append(
                np.r_[error[3:6], acceleration, (theta_next - error[6:9]) / dt, np.zeros(6)]
            )
        numerical[:, axis] = (derivatives[1] - derivatives[0]) / (2 * epsilon)
    np.testing.assert_allclose(expected, numerical, atol=8e-6)


def test_psd_q_sign_rotation_and_invalid_transaction():
    rng = np.random.default_rng(45991)
    first = Eskf15Filter(EskfState(q=Rotation_Exp(np.array([0.0, 3.13, 0.1]))))
    second = Eskf15Filter(first.state)
    second.state.q *= -1
    for _ in range(100):
        w, a = rng.normal(0, 0.5, 3), rng.normal(0, 2, 3) + [0, 0, 9.78]
        for k in (first, second):
            k.Prediction_Apply(w, a, 0.01)
        np.testing.assert_allclose(first.state.p, second.state.p, atol=1e-13)
        Covariance_Validate(first.state.covariance)
    state = first.state.State_Clone()
    result = first.Measurement_Apply("position", (0, 1), np.array([np.nan, 0]), np.ones(2))
    assert result.result == EskfUpdateResult.REJECTED_INVALID
    np.testing.assert_array_equal(first.state.covariance, state.covariance)
    with pytest.raises(ValueError):
        first.Prediction_Apply(np.zeros(3), np.zeros(3), 0.1)
    np.testing.assert_array_equal(first.state.p, state.p)


def test_soft_quality_has_effective_nonzero_gain_and_no_fix_stays_invalid():
    for satellites in (6, 5, 4, 6):
        k = Eskf15Filter()
        r = np.ones(2) * GnssQuality_VarianceScale(satellites)
        result = k.Measurement_Apply("position", (0, 1), np.array([1.0, 0]), r)
        assert result.result == EskfUpdateResult.ACCEPTED
        assert result.gain_norm > 0.5
        assert k.state.p[0] > 0.5
    raw = dict(
        supported_fields=1023,
        valid_fields=1023,
        fix_type=3,
        fix_ok=1,
        online=1,
        velocity_valid_mask=7,
        satellite_count=4,
        valid_group_mask=0,
        horizontal_accuracy_m=1.0,
        vertical_accuracy_m=2.0,
        speed_accuracy_mps=0.1,
    )
    assert Native_PhysicalMask(raw) == 15
    raw["fix_ok"] = 0
    assert Native_PhysicalMask(raw) == 0


def test_supervisor_effective_fusion_timeout_not_receive_timeout():
    supervisor = FusionSupervisor(1_000_000)
    for t in range(1_100_000, 13_000_000, 100_000):
        supervisor.Decision_Record(0, t, physically_valid=True, result=2, nis=50.0, gain_norm=0.0)
    assert supervisor.Health_Get(13_000_000, 1) == NavigationHealth.INVALID
    assert supervisor.groups[0].last_successful_fusion_us == 0
    assert not supervisor.Decision_Record(
        0, 12_000_000, physically_valid=True, result=0, nis=0.0, gain_norm=1.0
    )
    supervisor.Decision_Record(
        0, 13_100_000, physically_valid=True, result=0, nis=0.1, gain_norm=0.5
    )
    assert supervisor.Health_Get(13_100_000, 1) == NavigationHealth.HEALTHY


def test_staggered_windows_boundaries_gaps_warmup_and_small_velocity_bias():
    windows = StaggeredWindows()
    evidence = []
    for t in range(1_000_000, 601_000_000, 97_000):
        seconds = (t - 1_000_000) * 1e-6
        evidence.extend(
            windows.Sample_Receive(
                t,
                np.array([seconds, 0]),
                np.array([1.1, 0]),
                position_valid=True,
                velocity_valid=True,
            )
        )
    assert len(evidence) == 118
    assert all(item.valid for item in evidence)
    np.testing.assert_allclose([e.closure_en[0] for e in evidence], -1.0, atol=1e-10)
    assert all(item.variance_scale == 1 for item in evidence)
    assert windows.Evidence_Get(700_000_000) is None
    gap = StaggeredWindows()
    assert gap.Evidence_Get(0) is None
    results = []
    for t in range(100_000, 12_000_000, 100_000):
        results.extend(
            gap.Sample_Receive(
                t, np.zeros(2), np.zeros(2), position_valid=True, velocity_valid=t != 5_000_000
            )
        )
    assert not results
    assert gap.Evidence_Get(12_000_000) is None
    assert gap.reset_count >= 1


def test_delayed_body_replay_matches_chronological_and_history_miss():
    engines = [DelayedReplay(Eskf15Filter(), 1_000_000) for _ in range(2)]
    item = Measurement((1, 0), 1_200_000, 1_400_000, 0, np.array([0.3, -0.2]), np.ones(2), True)
    for index in range(60):
        start = 1_000_000 + index * 10_000
        step = BodyStep(
            start,
            start + 10_000,
            np.array([0.01, 0.02, 0.03]),
            np.array([0.1, -0.2, 9.78]),
            np.array([0.02, -0.01, 0.04]),
            np.array([0.2, -0.1, 9.78]),
        )
        for engine in engines:
            engine.Body_Receive(step)
        if index == 19:
            engines[0].Measurement_Receive(replace(item, receive_us=item.timestamp_us))
        if index == 39:
            engines[1].Measurement_Receive(item)
    a, b = [engine.kernel.state for engine in engines]
    for name in ("p", "v", "q", "bg", "ba", "covariance"):
        np.testing.assert_allclose(getattr(a, name), getattr(b, name), atol=1e-13)
    assert engines[1].maximum_replay_steps > engines[0].maximum_replay_steps
    missing = Measurement((2, 0), 500_000, 1_600_000, 0, np.zeros(2), np.ones(2), True)
    assert engines[0].Measurement_Receive(missing).result == EskfUpdateResult.HISTORY_MISS
