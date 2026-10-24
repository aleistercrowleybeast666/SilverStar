"""Independent physical perturbation oracles for the 15-error-state extension."""
from dataclasses import replace

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec, solve_ivp
from scipy.linalg import expm, logm
from scipy.spatial.transform import Rotation

import inekf15_reference as ref
import eskf20_reference as eskf
from inekf_reference import Navigation_VectorField


def Hat_Oracle(vector):
    x, y, z = vector[:3]
    hat = np.zeros((5, 5))
    hat[:3, :3] = [[0., -z, y], [z, 0., -x], [-y, x, 0.]]
    hat[:3, 3], hat[:3, 4] = vector[3:6], vector[6:9]
    return hat


def Exp_Oracle(vector):
    result = np.eye(5)
    result[:3] = expm(Hat_Oracle(vector))[:3]
    return result


def Log_Oracle(group):
    matrix = logm(group)
    assert np.max(np.abs(np.imag(matrix))) < 1e-10
    matrix = np.real(matrix)
    return np.r_[matrix[2, 1], matrix[0, 2], matrix[1, 0], matrix[:3, 3], matrix[:3, 4]]


def State_Create():
    group = Exp_Oracle(np.array([.3, -.2, .7, .2, -.1, .4, .5, -.4, .2]))
    rng = np.random.default_rng(15018)
    factor = rng.normal(size=(15, 15)) * .008
    return ref.InEkf15State(group, [.03, -.02, .01], [.04, -.05, .02],
                            factor @ factor.T + np.eye(15) * .003, 1.)


def Truth_Oracle(estimate, error):
    return replace(estimate, group=estimate.group @ Exp_Oracle(-error[:9]),
        gyro_bias=estimate.gyro_bias - error[9:12], accel_bias=estimate.accel_bias - error[12:15])


def Error_Oracle(estimate, truth):
    return np.r_[Log_Oracle(np.linalg.solve(truth.group, estimate.group)),
                 estimate.gyro_bias - truth.gyro_bias, estimate.accel_bias - truth.accel_bias]


def Jacobian_Finite(function, size, step=2e-5):
    identity = np.eye(size) * step
    return np.column_stack([(function(e) - function(-e)) / (2 * step) for e in identity])


def Flow_Oracle(state, omega_m, force_m, gravity, dt):
    omega, force = np.asarray(omega_m) - state.gyro_bias, np.asarray(force_m) - state.accel_bias
    rotation = state.group[:3, :3]
    def Derivative(time, translation):
        current = rotation @ Rotation.from_rotvec(omega * time).as_matrix()
        return np.r_[translation[3:], current @ force + gravity]
    solution = solve_ivp(Derivative, (0., dt), np.r_[state.group[:3, 4], state.group[:3, 3]],
                         method="DOP853", rtol=3e-13, atol=3e-14)
    assert solution.success
    group = np.eye(5)
    group[:3, :3] = rotation @ Rotation.from_rotvec(omega * dt).as_matrix()
    group[:3, 3], group[:3, 4] = solution.y[3:, -1], solution.y[:3, -1]
    return replace(state, group=group, time_s=state.time_s + dt)


def test_augmented_discrete_f_and_nominal_flow_independent_finite_difference():
    state = State_Create()
    omega, force, gravity, dt = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81]), .02
    nominal = Flow_Oracle(state, omega, force, gravity, dt)
    transition, _ = ref.InEkf15_Discretize(omega - state.gyro_bias, force - state.accel_bias, np.zeros(12), dt)
    numeric = Jacobian_Finite(lambda e: Error_Oracle(nominal,
        Flow_Oracle(Truth_Oracle(state, e), omega, force, gravity, dt)), 15)
    assert_allclose(transition, numeric, atol=1e-10, rtol=3e-7)
    result = ref.InEkf15_Predict(state, omega, force, gravity, np.zeros(12), dt)
    assert result.result is ref.NavigationAugmentedResult.OK
    assert_allclose(result.state.group, nominal.group, atol=3e-15, rtol=0)


def test_continuous_f_from_physical_error_rates():
    state = State_Create()
    omega, force, gravity, dt = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81]), 2e-4
    forward, backward = (Flow_Oracle(state, omega, force, gravity, time) for time in (dt, -dt))
    def Rate(error):
        truth = Truth_Oracle(state, error)
        return (Error_Oracle(forward, Flow_Oracle(truth, omega, force, gravity, dt)) -
                Error_Oracle(backward, Flow_Oracle(truth, omega, force, gravity, -dt))) / (2 * dt)
    numeric = Jacobian_Finite(Rate, 15, step=2e-4)
    expected = ref.InEkf15_Dynamics(omega - state.gyro_bias, force - state.accel_bias)
    assert_allclose(numeric, expected, atol=3e-7, rtol=2e-6)


@pytest.mark.parametrize("kind", ["position", "velocity"])
def test_h_all_columns_and_bias_cross_covariance_update(kind):
    state = State_Create()
    column = 4 if kind == "position" else 3
    def Residual(error):
        truth = Truth_Oracle(state, error)
        return state.group[:3, :3].T @ (state.group[:3, column] - truth.group[:3, column])
    numeric = Jacobian_Finite(Residual, 15)
    _, matrix, _ = ref.Vector_Observation(state.group, state.group[:3, column], np.eye(3), kind, 15)
    assert_allclose(matrix, numeric, atol=2e-11, rtol=1e-9)
    result = ref.InEkf15_Update(state, state.group[:3, column] + [.01, -.02, .03], np.eye(3) * .001, kind, state.time_s)
    assert result.result is ref.NavigationAugmentedResult.OK
    assert np.linalg.norm(result.state.gyro_bias - state.gyro_bias) > 1e-5
    assert np.linalg.norm(result.state.accel_bias - state.accel_bias) > 1e-5


@pytest.mark.parametrize("scale", [0., .1, 1.])
def test_full_se23_reset_and_dense_fifteen_covariance(scale):
    state, delta = State_Create(), np.linspace(-.1, .12, 15) * scale
    updated = ref.InEkf15_Inject(state, delta)
    expected = Truth_Oracle(state, delta)
    assert_allclose(updated.group, expected.group, atol=4e-16)
    numeric = Jacobian_Finite(lambda e: Error_Oracle(updated, Truth_Oracle(state, delta + e)), 15)
    reset = ref.InEkf15_ResetJacobian(delta)
    assert_allclose(reset, numeric, atol=4e-11, rtol=1e-8)
    assert_allclose(reset @ state.covariance @ reset.T, numeric @ state.covariance @ numeric.T,
                    atol=4e-13, rtol=2e-8)
    if scale:
        assert np.linalg.norm(reset[3:9, :3]) > .001  # Not separate Euclidean translations.


def test_joint_group_affine_and_finite_loglinearity_are_not_claimed():
    state = State_Create()
    other = Exp_Oracle(np.linspace(.1, .4, 9))
    biases = np.array([.12, -.07, .04, -.2, .1, .3])
    omega, force, gravity = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81])
    def Field(group, bias):
        return Navigation_VectorField(group, omega - bias[:3], force - bias[3:], gravity)
    first_bias = np.r_[state.gyro_bias, state.accel_bias]
    defect = (Field(state.group @ other, first_bias + biases) - Field(state.group, first_bias) @ other -
              state.group @ Field(other, biases) + state.group @ Field(np.eye(5), np.zeros(6)) @ other)
    assert np.linalg.norm(defect) > .02
    error = np.linspace(-.1, .15, 15)
    transition, _ = ref.InEkf15_Discretize(omega - state.gyro_bias, force - state.accel_bias, np.zeros(12), .02)
    forecast = Flow_Oracle(state, omega, force, gravity, .02)
    actual = Error_Oracle(forecast, Flow_Oracle(Truth_Oracle(state, error), omega, force, gravity, .02))
    assert np.linalg.norm(actual - transition @ error) > 1e-5
    error[9:] = 0.
    actual = Error_Oracle(forecast, Flow_Oracle(Truth_Oracle(state, error), omega, force, gravity, .02))
    assert_allclose(actual, transition @ error, atol=3e-15, rtol=0)


def test_navigation_left_action_and_conditional_trajectory_independence():
    state = State_Create()
    truth = Truth_Oracle(state, np.linspace(-.03, .04, 15))
    action = Exp_Oracle(np.linspace(.1, .2, 9))
    assert_allclose(Error_Oracle(replace(state, group=action @ state.group),
                                replace(truth, group=action @ truth.group)), Error_Oracle(state, truth), atol=2e-15)
    omega, force = np.array([.4, -.3, .7]), np.array([1., 2., 9.5])
    a = ref.InEkf15_Dynamics(omega - state.gyro_bias, force - state.accel_bias)
    b = ref.InEkf15_Dynamics(omega - truth.gyro_bias, force - truth.accel_bias)
    assert np.linalg.norm(a - b) > .01  # Bias estimates still enter the linearization.


def test_noise_map_physical_impulses_and_independent_q_quadrature():
    state, dt = State_Create(), 1e-4
    omega, force, gravity = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81])
    def Rate(noise):
        errors = []
        for time in (dt, -dt):
            nominal = Flow_Oracle(state, omega, force, gravity, time)
            truth = Flow_Oracle(state, omega - noise[:3], force - noise[3:6], gravity, time)
            truth = replace(truth, gyro_bias=truth.gyro_bias + noise[6:9] * time,
                            accel_bias=truth.accel_bias + noise[9:12] * time)
            errors.append(Error_Oracle(nominal, truth))
        return (errors[0] - errors[1]) / (2 * dt)
    assert_allclose(Jacobian_Finite(Rate, 12, step=1e-3), ref.InEkf15_NoiseMap(), atol=2e-7, rtol=1e-6)
    density = np.linspace(.002, .02, 12)
    matrix = ref.InEkf15_Dynamics(omega, force)
    mapping = ref.InEkf15_NoiseMap()
    continuous = mapping @ np.diag(density ** 2) @ mapping.T
    expected, _ = quad_vec(lambda t: expm(matrix * t) @ continuous @ expm(matrix.T * t), 0., .02)
    transition, noise = ref.InEkf15_Discretize(omega, force, density, .02)
    half, qhalf = ref.InEkf15_Discretize(omega, force, density, .01)
    _, qscaled = ref.InEkf15_Discretize(omega, force, density * 3, .02)
    assert_allclose(noise, expected, atol=1e-19, rtol=1e-10)
    assert_allclose(noise, half @ qhalf @ half.T + qhalf, atol=1e-19, rtol=1e-10)
    assert_allclose(qscaled, 9 * noise, atol=1e-18, rtol=1e-10)
    assert_allclose(transition, half @ half, atol=4e-16)


def test_common_error_coordinate_map_matches_eskf_prediction_and_h():
    state = State_Create()
    omega, force, gravity, dt = np.array([.4, -.3, .7]), np.array([1., 2., 9.5]), np.array([0., 0., -9.81]), .02
    transform = ref.Coordinates_ToEskf15(state.group)
    def Common_Error(error):
        truth = Truth_Oracle(state, error)
        return np.r_[truth.group[:3, 4] - state.group[:3, 4], truth.group[:3, 3] - state.group[:3, 3],
            Rotation.from_matrix(state.group[:3, :3].T @ truth.group[:3, :3]).as_rotvec(),
            truth.gyro_bias - state.gyro_bias, truth.accel_bias - state.accel_bias]
    assert_allclose(transform, Jacobian_Finite(Common_Error, 15), atol=2e-11, rtol=1e-9)
    covariance = np.eye(20) * .001
    covariance[:15, :15] = transform @ state.covariance @ transform.T
    conventional = eskf.Eskf20State(state.group[:3, 4], state.group[:3, 3], state.group[:3, :3],
        state.gyro_bias, state.accel_bias, np.eye(3), .5, .3, covariance, state.time_s)
    density = np.linspace(.001, .012, 12)
    conventional_density = np.r_[density[3:6], density[:3], density[6:]]
    result = ref.InEkf15_Predict(state, omega, force, gravity, density, dt)
    compared = eskf.Eskf20_Predict(conventional, omega, force, gravity, conventional_density, dt)
    assert result.result is ref.NavigationAugmentedResult.OK
    assert compared.result is eskf.NavigationEskf20Result.OK
    new_map = ref.Coordinates_ToEskf15(result.state.group)
    assert_allclose(new_map @ result.state.covariance @ new_map.T, compared.state.covariance[:15, :15], atol=3e-17, rtol=1e-10)
    for kind, offset in (("position", 0), ("velocity", 3)):
        _, hinv, _ = ref.Vector_Observation(state.group, np.zeros(3), np.eye(3), kind, 15)
        hcommon = np.zeros((3, 15)); hcommon[:, offset:offset+3] = np.eye(3)
        assert_allclose(hinv, -state.group[:3, :3].T @ hcommon @ transform, atol=4e-16)


def Scenario_Run(excited, observe=True, count=650):
    truth = ref.InEkf15State(np.eye(5), [.015, -.012, .01], [.06, -.04, .05], np.eye(15) * .01)
    error = np.r_[[.012, -.01, .015], np.zeros(6), [.008, -.006, .007], [.035, -.03, .025]]
    estimate = Truth_Oracle(truth, -error)
    estimate = replace(estimate, covariance=np.diag(np.r_[np.full(3, .02), np.full(6, .04), np.full(3, .005), np.full(3, .02)]))
    density, gravity, dt = np.r_[np.full(3, 1e-4), np.full(3, 1e-3), np.full(6, 1e-6)], np.array([0., 0., -9.81]), .02
    transition, rows, missing = np.eye(15), [], 0
    initial_bias = np.r_[estimate.gyro_bias - truth.gyro_bias, estimate.accel_bias - truth.accel_bias]
    for index in range(count):
        time = index * dt
        omega = np.array([.5 * np.sin(.9*time), .4 * np.cos(.7*time), .3 * np.sin(1.1*time)]) if excited else np.zeros(3)
        force = np.array([1.3 * np.sin(.8*time), .9 * np.cos(1.2*time), 9.81 + .7*np.sin(.6*time)]) if excited else -gravity
        omega_m, force_m = omega + truth.gyro_bias, force + truth.accel_bias
        truth = Flow_Oracle(truth, omega_m, force_m, gravity, dt)
        phi, _ = ref.InEkf15_Discretize(omega, force, np.zeros(12), dt)
        transition = phi @ transition
        predicted = ref.InEkf15_Predict(estimate, omega_m, force_m, gravity, density, dt)
        assert predicted.result is ref.NavigationAugmentedResult.OK
        estimate = predicted.state
        for kind, column, offset in (("position", 4, 6), ("velocity", 3, 3)):
            matrix = np.zeros((3, 15)); matrix[:, offset:offset+3] = np.eye(3)
            if index % 5 == 0:
                rows.append(matrix @ transition)
            measured = truth.group[:3, column] if observe and index % 5 == 0 else None
            step = ref.InEkf15_Update(estimate, measured, np.eye(3) * .0025, kind, truth.time_s)
            if measured is None:
                assert step.result is ref.NavigationAugmentedResult.NO_OBSERVATION and step.state is estimate
                missing += 1
            else:
                assert step.result is ref.NavigationAugmentedResult.OK
            estimate = step.state
        np.linalg.cholesky(estimate.covariance)
    singular = np.linalg.svd(np.vstack(rows), compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * 1e-8))
    final_bias = np.r_[estimate.gyro_bias - truth.gyro_bias, estimate.accel_bias - truth.accel_bias]
    return initial_bias, final_bias, rank, singular[-1] / singular[0], missing, estimate


def test_excited_observable_synthetic_bias_convergence():
    before, after, rank, ratio, missing, _ = Scenario_Run(True)
    print(f"Excited 13s window: rank={rank}/15, singular_ratio={ratio:.6g}, bias_initial={before.tolist()}, bias_final={after.tolist()}, missing={missing}")
    assert rank == 15 and ratio > 1e-5
    assert np.linalg.norm(after[:3]) < .2 * np.linalg.norm(before[:3])
    assert np.linalg.norm(after[3:]) < .2 * np.linalg.norm(before[3:])
    assert missing > 0


def test_static_poor_excitation_does_not_identify_all_biases():
    before, after, rank, ratio, _, _ = Scenario_Run(False, count=160)
    print(f"Static 3.2s window: rank={rank}/15, singular_ratio={ratio:.6g}, gyro_z_initial={before[2]:.6g}, gyro_z_final={after[2]:.6g}")
    assert rank < 15
    assert abs(after[2]) > .5 * abs(before[2])


def test_no_observations_do_not_estimate_biases():
    before, after, _, _, _, _ = Scenario_Run(True, observe=False, count=80)
    assert_allclose(after, before, atol=0., rtol=0.)


@pytest.mark.parametrize("bad", [True, "0.01", 1+0j, [0.01], np.array([.01]), np.nan, np.inf, 10**1000])
def test_invalid_scalar_transactions(bad):
    state = State_Create()
    step = ref.InEkf15_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(12), bad)
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state
    step = ref.InEkf15_Update(state, np.ones(3), np.eye(3), "position", bad)
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


@pytest.mark.parametrize("bad", [[10**1000,0,0], [np.nan,0,0], [1j,0,0], [1,2]])
def test_invalid_arrays_transaction(bad):
    state = State_Create()
    step = ref.InEkf15_Predict(state, bad, np.zeros(3), np.zeros(3), np.zeros(12), .01)
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


@pytest.mark.parametrize("kind", [np.array(["position", "velocity"]), [], 1, "barometer"])
def test_invalid_kind_transaction(kind):
    state = State_Create()
    step = ref.InEkf15_Update(state, np.ones(3), np.eye(3), kind, state.time_s)
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state


def test_scalar_aliases_overflow_and_gate_preserve_transaction():
    alias = np.array(1.)
    state = replace(State_Create(), time_s=alias)
    alias[...] = 5.
    assert state.time_s == 1. and isinstance(state.time_s, float)
    step = ref.InEkf15_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), np.full(12, 1e308), .01)
    assert step.result is ref.NavigationAugmentedResult.NUMERIC_ERROR and step.state is state
    step = ref.InEkf15_Update(state, np.full(3, 100.), np.eye(3), "position", state.time_s, .001)
    assert step.result is ref.NavigationAugmentedResult.REJECTED_NIS and step.state is state
    step = ref.InEkf15_Update(state, np.full(3, 1e308), np.eye(3), "position", state.time_s)
    assert step.result is ref.NavigationAugmentedResult.NUMERIC_ERROR and step.state is state


@pytest.mark.parametrize("field", ["group", "covariance"])
def test_corrupt_stored_state_is_rejected_without_warning_escape(field):
    state = State_Create()
    bad = getattr(state, field).copy(); bad[0, 0] = 1e308
    if field == "covariance":
        bad[0, 1], bad[1, 0] = 1e308, -1e308
    object.__setattr__(state, field, bad)
    step = ref.InEkf15_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(12), .01)
    assert step.result is ref.NavigationAugmentedResult.INVALID_INPUT and step.state is state
