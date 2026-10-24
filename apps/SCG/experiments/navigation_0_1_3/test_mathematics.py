"""Synthetic mathematical evidence only; no devices, datasets or firmware builds."""
import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec, solve_ivp
from scipy.linalg import expm, logm

from lie_group import (Group_Inverse, Lie_Adjoint, Lie_Exp, Lie_Hat, Lie_Log,
                       Lie_LeftJacobian, Vector_Skew)
from inekf_reference import (Navigation_ErrorDynamics, Navigation_Discretize,
    Navigation_ObservationMatrix, Navigation_PropagateGroup, Navigation_Residual,
    Navigation_VectorField, NavigationInEkf_Predict, NavigationInEkf_Update,
    NavigationInEkfResult as Result, NavigationState)

G = np.array([0., 0., -9.78])
W = np.array([0.3, -0.2, 0.4])
A = np.array([0.8, -0.4, 9.78])
DENSITY = np.array([.003] * 3 + [.08] * 3)


def State_Create():
    rng = np.random.default_rng(201017)
    factor = rng.normal(0, .15, (9, 9))
    return NavigationState(Lie_Exp(np.array([.3, -.2, .1, 1, 2, -.5, 5, -2, 3.])),
                           factor @ factor.T + np.diag(np.linspace(.2, 1., 9)))


def Difference_Columns(function, size, step=1e-6):
    basis = np.eye(size) * step
    return np.column_stack([(function(e) - function(-e)) / (2 * step) for e in basis])


@pytest.mark.parametrize("angle", [0., 1e-10, 1e-5, .3, 2., np.pi - 1e-5])
def test_group_maps_against_rodrigues_series_and_general_matrix_log(angle):
    phi = np.array([1., 2., -1.]) * angle / np.sqrt(6)
    vector = np.r_[phi, [.3, -2, 1], [4, .2, -.6]]
    group = Lie_Exp(vector)
    skew = Vector_Skew(phi)
    # Independent power-series integration (not the block-exponential method).
    rotation, jacobian, term = np.eye(3), np.eye(3), np.eye(3)
    for k in range(1, 60):
        term = term @ skew / k
        rotation += term
        jacobian += term / (k + 1)
    assert_allclose(group[:3, :3], rotation, atol=3e-15, rtol=1e-14)
    assert_allclose(group[:3, 3], jacobian @ vector[3:6], atol=3e-14)
    assert_allclose(group[:3, 4], jacobian @ vector[6:9], atol=3e-14)
    assert_allclose(Lie_Log(group), vector, atol=3e-10, rtol=1e-10)
    assert_allclose(logm(group).real, Lie_Hat(vector), atol=3e-10)
    assert_allclose(group @ Group_Inverse(group), np.eye(5), atol=3e-14)


def test_principal_log_rejects_pi_and_group_rejects_reflection():
    with pytest.raises(ValueError, match="cut_locus"):
        Lie_Log(Lie_Exp(np.r_[[np.pi, 0., 0.], np.zeros(6)]))
    reflection = np.eye(5)
    reflection[0, 0] = -1
    with pytest.raises(ValueError, match="not_se23"):
        Group_Inverse(reflection)


def test_left_invariance_and_adjoint_conjugation():
    state = State_Create().group
    other = Lie_Exp(np.arange(9) / 20)
    frame = Lie_Exp(np.arange(9)[::-1] / 10)
    assert_allclose(Group_Inverse(frame @ state) @ (frame @ other),
                    Group_Inverse(state) @ other, atol=3e-14)
    assert_allclose(frame @ other @ Group_Inverse(frame),
                    Lie_Exp(Lie_Adjoint(frame) @ Lie_Log(other)), atol=3e-14)


def test_group_affine_vector_field_identity():
    first, second = State_Create().group, Lie_Exp(np.arange(9) / 17)
    field = lambda x: Navigation_VectorField(x, W, A, G)
    assert_allclose(field(first @ second), field(first) @ second +
                    first @ field(second) - first @ field(np.eye(5)) @ second,
                    atol=3e-14)


def test_nominal_flow_against_independent_ode_integration():
    initial = State_Create().group
    # Integrate raw matrix differential equation without production propagation.
    def derivative(_time, flat):
        x = flat.reshape(5, 5)
        dx = np.zeros((5, 5))
        dx[:3, :3] = x[:3, :3] @ Vector_Skew(W)
        dx[:3, 3], dx[:3, 4] = x[:3, :3] @ A + G, x[:3, 3]
        return dx.ravel()
    oracle = solve_ivp(derivative, (0, .02), initial.ravel(), method="DOP853",
                       rtol=2e-13, atol=1e-14)
    assert oracle.success
    assert_allclose(Navigation_PropagateGroup(initial, W, A, G, .02),
                    oracle.y[:, -1].reshape(5, 5), atol=2e-13, rtol=2e-13)


def test_discrete_error_finite_difference_and_large_error_log_linearity():
    initial = State_Create().group
    predict = lambda x: Navigation_PropagateGroup(x, W, A, G, .02)
    predicted_true = predict(initial)
    error = lambda xi: Lie_Log(Group_Inverse(predicted_true) @ predict(initial @ Lie_Exp(xi)))
    transition = expm(Navigation_ErrorDynamics(W, A) * .02)
    # Central difference balances O(h^2) against O(eps * state_scale / h).
    # A fixed 1e-6 step loses digits when subtracting metre-scale positions.
    # Keep the same acceptance tolerance and scale h by cbrt(machine epsilon).
    step = np.cbrt(np.finfo(np.float64).eps) * max(1., np.linalg.norm(initial[:3, 3:], np.inf))
    assert_allclose(Difference_Columns(error, 9, step), transition, atol=1e-9, rtol=1e-8)
    # Not merely the small-error ESKF Jacobian: deterministic finite errors agree.
    xi = np.array([.7, -.4, .3, 1., -2., .6, -4., 2., 1.])
    assert_allclose(error(xi), transition @ xi, atol=2e-14, rtol=1e-13)
    alternative = Lie_Exp(np.array([-.4, .5, -.8, 4, 5, 6, -9, 2, 3]))
    alternative_error = Group_Inverse(predict(alternative)) @ predict(alternative @ Lie_Exp(xi))
    assert_allclose(Lie_Log(alternative_error), error(xi), atol=2e-14)


@pytest.mark.parametrize("kind", ["position", "velocity"])
def test_observation_jacobian_independent_finite_difference(kind):
    truth = State_Create().group
    observation = truth[:3, 4 if kind == "position" else 3]
    residual = lambda xi: Navigation_Residual(truth @ Lie_Exp(xi), observation, kind)
    assert_allclose(Difference_Columns(residual, 9), Navigation_ObservationMatrix(kind),
                    atol=1e-9, rtol=1e-8)


def test_body_noise_map_finite_difference():
    truth = State_Create().group
    dt = 1e-6
    estimate = Navigation_PropagateGroup(truth, W, A, G, dt)
    def error(noise):
        real = Navigation_PropagateGroup(truth, W - noise[:3], A - noise[3:], G, dt)
        return Lie_Log(Group_Inverse(real) @ estimate) / dt
    expected = np.zeros((9, 6))
    expected[:6] = np.eye(6)
    assert_allclose(Difference_Columns(error, 6, 1e-3), expected, atol=6e-6, rtol=1e-5)


def test_reset_jacobian_and_full_cross_covariance_finite_difference():
    delta = np.array([.2, -.15, .08, .3, -.5, .1, 2., -.4, .2])
    reset_map = lambda e: Lie_Log(Lie_Exp(delta + e) @ Lie_Exp(-delta))
    numerical = Difference_Columns(reset_map, 9)
    jacobian = Lie_LeftJacobian(delta)
    assert_allclose(jacobian, numerical, atol=8e-10, rtol=1e-7)
    covariance = State_Create().covariance
    assert_allclose(jacobian @ covariance @ jacobian.T,
                    numerical @ covariance @ numerical.T, atol=2e-9, rtol=1e-7)


def test_discrete_noise_integral_against_quadrature_and_step_composition():
    matrix = Navigation_ErrorDynamics(W, A)
    transition, noise = Navigation_Discretize(matrix, DENSITY, .02)
    spectral = np.diag(np.r_[DENSITY**2, np.zeros(3)])
    expected, error = quad_vec(lambda s: expm(matrix*s) @ spectral @ expm(matrix.T*s),
                               0, .02, epsabs=1e-14, epsrel=1e-12)
    assert error < 1e-12
    assert_allclose(noise, expected, atol=1e-16, rtol=1e-10)
    half_transition, half_noise = Navigation_Discretize(matrix, DENSITY, .01)
    assert_allclose(transition, half_transition @ half_transition, atol=1e-15)
    assert_allclose(noise, half_transition @ half_noise @ half_transition.T + half_noise,
                    atol=1e-16, rtol=1e-10)
    assert np.linalg.eigvalsh(noise).min() > 0


def test_world_frame_equivariance_of_prediction_and_update():
    initial = State_Create()
    frame = Lie_Exp(np.r_[[.4, -.1, .3], np.zeros(3), [2., -1., 3.]])
    rotation, translation = frame[:3, :3], frame[:3, 4]
    transformed = NavigationState(frame @ initial.group, initial.covariance)
    first = NavigationInEkf_Predict(initial, W, A, .01, DENSITY, G)
    second = NavigationInEkf_Predict(transformed, W, A, .01, DENSITY, rotation @ G)
    for kind in ("position", "velocity"):
        y, r = np.array([3., -1., .2]), np.diag([.2, .3, .5])
        changed_y = rotation @ y + (translation if kind == "position" else 0)
        first = NavigationInEkf_Update(first.state, y, r, kind, first.state.time_s)
        second = NavigationInEkf_Update(second.state, changed_y, rotation @ r @ rotation.T,
                                         kind, second.state.time_s)
        assert first.result is second.result is Result.OK
        assert_allclose(second.state.group, frame @ first.state.group, atol=3e-14)
        assert_allclose(second.state.covariance, first.state.covariance, atol=3e-14)
        assert second.nis == pytest.approx(first.nis, abs=1e-12)


def test_analytic_turning_acceleration_and_synthetic_correction():
    initial_group = np.eye(5)
    initial_group[:3, 4] = [.5, -.3, .2]
    state = NavigationState(initial_group, np.eye(9) * .2)
    truth = np.eye(5)
    worst_symmetry = 0.
    for index in range(1, 101):
        dt, yaw_rate = .01, .8
        truth = Navigation_PropagateGroup(truth, [0, 0, yaw_rate], [1, 0, 9.78], G, dt)
        time = index * dt
        velocity = np.array([np.sin(yaw_rate*time)/yaw_rate,
                              (1-np.cos(yaw_rate*time))/yaw_rate, 0.])
        position = np.array([(1-np.cos(yaw_rate*time))/yaw_rate**2,
                              time/yaw_rate-np.sin(yaw_rate*time)/yaw_rate**2, 0.])
        assert_allclose(truth[:3, 3], velocity, atol=2e-13)
        assert_allclose(truth[:3, 4], position, atol=2e-13)
        step = NavigationInEkf_Predict(state, [0, 0, yaw_rate], [1, 0, 9.78], dt, DENSITY, G)
        assert step.result is Result.OK
        state = step.state
        if index % 10 == 0:
            for kind, measurement in (("position", position), ("velocity", velocity)):
                step = NavigationInEkf_Update(state, measurement, np.eye(3)*.01, kind, state.time_s)
                assert step.result is Result.OK
                state = step.state
        np.linalg.cholesky(state.covariance)
        worst_symmetry = max(worst_symmetry, np.max(np.abs(state.covariance-state.covariance.T)))
    assert worst_symmetry == 0
    assert np.linalg.norm(state.group[:3, 4] - position) < .015


@pytest.mark.parametrize("field,value", [
    ("angular_rate", [np.nan, 0, 0]), ("angular_rate", [0, 0]),
    ("specific_force", [0, 0, np.inf]), ("gravity", [0, 0, complex(1, 2)]),
    ("density", [-1]*6), ("density", [np.inf]*6),
    ("dt", 0), ("dt", -.01), ("dt", .02001), ("dt", np.nan)])
def test_predict_invalid_inputs_preserve_state(field, value):
    state = State_Create()
    arguments = dict(angular_rate=W, specific_force=A, dt=.01, density=DENSITY, gravity=G)
    arguments[field] = value
    before = (state.group.tobytes(), state.covariance.tobytes(), state.time_s)
    step = NavigationInEkf_Predict(state, **arguments)
    assert step.result is Result.INVALID_INPUT and step.state is state
    assert before == (state.group.tobytes(), state.covariance.tobytes(), state.time_s)


@pytest.mark.parametrize("field,value", [
    ("observation", [np.nan, 0, 0]), ("observation", [1, 2]),
    ("covariance_world", np.zeros((3, 3))), ("covariance_world", -np.eye(3)),
    ("covariance_world", [[1, .1, 0], [0, 1, 0], [0, 0, 1]]),
    ("time_s", -.01), ("time_s", .01), ("nis_threshold", 0),
    ("nis_threshold", np.inf)])
def test_update_invalid_inputs_preserve_state(field, value):
    state = State_Create()
    arguments = dict(observation=np.zeros(3), covariance_world=np.eye(3),
                     kind="position", time_s=0., nis_threshold=None)
    arguments[field] = value
    step = NavigationInEkf_Update(state, **arguments)
    assert step.result is Result.INVALID_INPUT and step.state is state


def test_gating_unsupported_and_numeric_failure_do_not_publish():
    state = State_Create()
    rejected = NavigationInEkf_Update(state, [100, 100, 100], np.eye(3), "position", 0., 1.)
    assert rejected.result is Result.REJECTED_NIS and rejected.state is state and rejected.nis > 1
    unsupported = NavigationInEkf_Update(state, [0, 0, 0], np.eye(3), "magnetometer", 0.)
    assert unsupported.result is Result.UNSUPPORTED_OBSERVATION and unsupported.state is state
    numeric = NavigationInEkf_Predict(state, W, A, .01, np.full(6, 1e308), G)
    assert numeric.result is Result.NUMERIC_ERROR and numeric.state is state


@pytest.mark.parametrize("covariance", [np.zeros((9,9)), -np.eye(9), np.eye(8),
                                        np.full((9,9), np.nan)])
def test_invalid_initial_covariance_rejected(covariance):
    with pytest.raises(ValueError):
        NavigationState(np.eye(5), covariance)


def test_state_copies_arrays_and_zero_noise_preserves_spd():
    group, covariance = np.eye(5), np.eye(9)
    state = NavigationState(group, covariance)
    group[0, 4], covariance[0, 0] = 100, -1
    assert state.group[0, 4] == 0 and state.covariance[0, 0] == 1
    step = NavigationInEkf_Predict(state, [0]*3, [0, 0, 9.78], .02, np.zeros(6), G)
    assert step.result is Result.OK
    assert_allclose(step.state.group, np.eye(5), atol=1e-15)
    np.linalg.cholesky(step.state.covariance)


@pytest.mark.parametrize("field,value", [("group", np.eye(4)),
    ("time_s", np.nan), ("time_s", -1.), ("time_s", np.inf)])
def test_invalid_state_identity_and_time_rejected(field, value):
    arguments = dict(group=np.eye(5), covariance=np.eye(9), time_s=0.)
    arguments[field] = value
    with pytest.raises(ValueError):
        NavigationState(**arguments)


def test_malformed_group_and_corrupted_covariance_rejected_without_repair():
    for row, column, value in ((0, 0, 2.), (3, 0, 1e-16), (4, 4, 0.)):
        group = np.eye(5)
        group[row, column] = value
        with pytest.raises(ValueError):
            NavigationState(group, np.eye(9))
    state = State_Create()
    # Explicitly defeat NumPy's read-only flag to simulate stored-state damage.
    state.covariance.setflags(write=True)
    state.covariance[0, 0] = -1.
    state.covariance.setflags(write=False)
    before = state.covariance.tobytes()
    step = NavigationInEkf_Predict(state, W, A, .01, DENSITY, G)
    assert step.result is Result.INVALID_INPUT and step.state is state
    assert state.covariance.tobytes() == before


def test_nonadvancing_time_and_overflowing_update_are_rejected():
    state = NavigationState(np.eye(5), np.eye(9), 1e16)
    step = NavigationInEkf_Predict(state, W, A, .01, DENSITY, G)
    assert step.result is Result.INVALID_INPUT and step.state is state
    initial = State_Create()
    step = NavigationInEkf_Update(initial, np.full(3, 1e308), np.eye(3), "position", 0.)
    assert step.result is Result.NUMERIC_ERROR and step.state is initial
