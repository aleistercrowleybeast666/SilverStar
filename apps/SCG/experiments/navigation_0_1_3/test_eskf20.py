"""Independent physical perturbations, SO(3) oracle and synthetic-only checks."""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec, solve_ivp
from scipy.linalg import expm
from scipy.spatial.transform import Rotation

import eskf20_reference as ref


def Rotation_Oracle(vector):
    return Rotation.from_rotvec(vector).as_matrix()


def State_Create():
    rng = np.random.default_rng(2043)
    factor = rng.normal(size=(20, 20)) * .006
    covariance = factor @ factor.T + np.diag(np.linspace(.001, .003, 20))
    return ref.Eskf20State(np.array([.4, -.2, .7]), np.array([.2, .5, -.3]),
        Rotation_Oracle([.3, -.2, .8]), np.array([.02, -.03, .01]),
        np.array([.05, -.02, .03]), Rotation_Oracle([.24, -.15, .11]),
        .72, -.38, covariance)


def State_Oracle(nominal, error):
    return replace(nominal, position=nominal.position + error[:3],
        velocity=nominal.velocity + error[3:6],
        rotation=nominal.rotation @ Rotation_Oracle(error[6:9]),
        gyro_bias=nominal.gyro_bias + error[9:12],
        accel_bias=nominal.accel_bias + error[12:15],
        installation=Rotation_Oracle(-error[15:18]) @ nominal.installation,
        inclination=nominal.inclination - error[18],
        declination=nominal.declination - error[19])


def Error_Oracle(nominal, truth):
    return np.r_[truth.position - nominal.position, truth.velocity - nominal.velocity,
        Rotation.from_matrix(nominal.rotation.T @ truth.rotation).as_rotvec(),
        truth.gyro_bias - nominal.gyro_bias, truth.accel_bias - nominal.accel_bias,
        -Rotation.from_matrix(truth.installation @ nominal.installation.T).as_rotvec(),
        nominal.inclination - truth.inclination, nominal.declination - truth.declination]


def Field_Oracle(state):
    # North rotated east by D, inclined downward by I; independent construction.
    # At exact poles the geometric result is known without evaluating a
    # quaternion half-angle: that route leaves 2.22e-16 spurious horizontal
    # terms. Keep the pole assertion's original 2e-16 tolerance.
    if abs(state.inclination) == np.pi / 2:
        return np.array([0., 0., -np.sign(state.inclination)])
    return (Rotation_Oracle([0., 0., -state.declination]) @
            Rotation_Oracle([-state.inclination, 0., 0.]) @ np.array([0., 1., 0.]))


def Sample_Create(truth, strength=48.):
    measured = truth.installation.T @ truth.rotation.T @ Field_Oracle(truth)
    return ref.MagneticSample(strength * measured, np.diag([.03, .02, .04]),
        strength, truth.time_s, "magnetometer_sensor", "hard_soft_iron_only")


def Jacobian_Finite(function, size, step=2e-6):
    identity = np.eye(size) * step
    return np.column_stack([(function(column) - function(-column)) / (2 * step)
                            for column in identity])


def Flow_Oracle(state, omega_m, force_m, gravity, dt):
    omega, force = omega_m - state.gyro_bias, force_m - state.accel_bias
    # Integrate navigation translation independently; rotation has closed form.
    def Derivative(time, vector):
        rotation = state.rotation @ Rotation_Oracle(omega * time)
        return np.r_[vector[3:], rotation @ force + gravity]
    solution = solve_ivp(Derivative, (0., dt), np.r_[state.position, state.velocity],
                         method="DOP853", rtol=3e-13, atol=3e-14)
    assert solution.success
    return replace(state, position=solution.y[:3, -1], velocity=solution.y[3:, -1],
        rotation=state.rotation @ Rotation_Oracle(omega * dt), time_s=state.time_s + dt)


@pytest.mark.parametrize("inclination", [-1.4, -.7, 0., .72, 1.4])
@pytest.mark.parametrize("installation", [[0., 0., 0.], [.24, -.15, .11]])
def test_magnetic_all_twenty_columns_finite_difference(inclination, installation):
    nominal = replace(State_Create(), inclination=inclination,
                      installation=Rotation_Oracle(installation))
    def Residual(error):
        truth = State_Oracle(nominal, error)
        sensor = truth.installation.T @ truth.rotation.T @ Field_Oracle(truth)
        return nominal.rotation @ nominal.installation @ sensor - Field_Oracle(nominal)
    numeric = Jacobian_Finite(Residual, 20)
    assert_allclose(ref.Magnetic_Jacobian(nominal), numeric, atol=4e-10, rtol=2e-9)
    assert np.max(np.abs(numeric[:, 15:18])) > .5
    assert_allclose(numeric[:, :6], 0., atol=1e-12)
    assert_allclose(numeric[:, 9:15], 0., atol=1e-12)


def test_exact_declination_derivative_is_half_unit_axis_at_sixty_degrees():
    state = replace(State_Create(), inclination=np.pi / 3)
    _, derivative_i, derivative_d = ref.Magnetic_Field(state.inclination, state.declination)
    assert_allclose(np.linalg.norm(derivative_i), 1., atol=1e-15)
    assert_allclose(np.linalg.norm(derivative_d), .5, atol=1e-15)
    assert_allclose(1. / np.linalg.norm(derivative_d), 2., atol=1e-15)


@pytest.mark.parametrize("inclination", [-np.pi / 2, -np.pi / 2 + 1e-7,
                                          np.pi / 2 - 1e-7, np.pi / 2])
def test_poles_lose_declination_sensitivity_without_numeric_repair(inclination):
    state = replace(State_Create(), inclination=inclination, covariance=np.eye(20) * .001)
    matrix = ref.Magnetic_Jacobian(state)
    assert np.linalg.norm(matrix[:, 19]) < 1.01e-7
    assert np.linalg.matrix_rank(matrix, tol=1e-10) == 2
    step = ref.Eskf20_UpdateMagnetic(state, Sample_Create(state))
    assert step.result is ref.NavigationEskf20Result.OK
    assert step.magnetic_rank == 2
    assert step.declination_sensitivity < 1.01e-7
    if abs(inclination) == np.pi / 2:
        assert_allclose(step.state.covariance[19, 19], state.covariance[19, 19], atol=1e-17)
        assert_allclose(Field_Oracle(replace(state, declination=1.7)), Field_Oracle(state), atol=2e-16)
        assert_allclose(ref.Magnetic_Field(inclination, 1.7)[0], Field_Oracle(state), atol=2e-16)
        assert_allclose(ref.Magnetic_Field(inclination, state.declination)[0], Field_Oracle(state), atol=2e-16)


def test_attitude_installation_gauge_and_static_rank_do_not_prove_identifiability():
    state = State_Create()
    direction = np.zeros(20)
    direction[6:9] = direction[15:18] = [.1, -.2, .15]
    matrix = ref.Magnetic_Jacobian(state)
    assert_allclose(matrix @ direction, 0., atol=1e-16)
    shifted = State_Oracle(state, direction)
    assert_allclose(shifted.rotation @ shifted.installation,
                    state.rotation @ state.installation, atol=5e-16)
    assert np.linalg.matrix_rank(np.tile(matrix, (12, 1)), tol=1e-10) == 2


@pytest.mark.parametrize("scale", [0., .1, 1.])
def test_injection_and_full_reset_covariance_finite_difference(scale):
    state = State_Create()
    correction = np.linspace(-.09, .08, 20) * scale
    updated = ref.Error_Inject(state, correction)
    assert_allclose(Error_Oracle(updated, State_Oracle(state, correction)), 0., atol=2e-16)
    numeric = Jacobian_Finite(lambda perturbation:
        Error_Oracle(updated, State_Oracle(state, correction + perturbation)), 20)
    reset = ref.Error_ResetJacobian(correction)
    assert_allclose(reset, numeric, atol=5e-11, rtol=1e-8)
    assert_allclose(reset @ state.covariance @ reset.T,
                    numeric @ state.covariance @ numeric.T, atol=3e-13, rtol=1e-8)
    assert np.any(np.abs(state.covariance[:15, 15:]) > 1e-5)


def test_continuous_f_finite_difference_from_physical_error_rates():
    nominal = State_Create()
    omega_m, force_m = np.array([.4, -.3, .7]), np.array([1., -.4, 9.6])
    wn, an = omega_m - nominal.gyro_bias, force_m - nominal.accel_bias
    def Rate(error):
        truth = State_Oracle(nominal, error)
        wt = omega_m - truth.gyro_bias
        relative = nominal.rotation.T @ truth.rotation
        time_step = 1e-4
        def Attitude_Error(time):
            matrix = Rotation_Oracle(-wn * time) @ relative @ Rotation_Oracle(wt * time)
            return Rotation.from_matrix(matrix).as_rotvec()
        attitude_rate = (Attitude_Error(time_step) - Attitude_Error(-time_step)) / (2 * time_step)
        return np.r_[truth.velocity - nominal.velocity,
            truth.rotation @ (force_m - truth.accel_bias) - nominal.rotation @ an,
            attitude_rate, np.zeros(11)]
    numeric = Jacobian_Finite(Rate, 20, step=2e-4)
    expected = ref.Dynamics_Matrix(nominal.rotation, wn, an)
    assert_allclose(numeric, expected, atol=6e-8, rtol=3e-7)


def test_discrete_transition_finite_difference_and_independent_nominal_flow():
    nominal = State_Create()
    omega_m, force_m = np.array([.4, -.3, .7]), np.array([1., -.4, 9.6])
    gravity, dt = np.array([0., 0., -9.80665]), .015
    propagated = Flow_Oracle(nominal, omega_m, force_m, gravity, dt)
    transition, noise = ref.Covariance_Discretize(nominal.rotation,
        omega_m - nominal.gyro_bias, force_m - nominal.accel_bias, np.zeros(12), dt)
    numeric = Jacobian_Finite(lambda perturbation:
        Error_Oracle(propagated, Flow_Oracle(State_Oracle(nominal, perturbation),
                     omega_m, force_m, gravity, dt)), 20, step=3e-5)
    assert_allclose(transition, numeric, atol=1e-10, rtol=2e-8)
    assert_allclose(noise, 0., atol=0.)
    actual = ref.Nominal_Propagate(nominal, omega_m, force_m, gravity, dt)
    assert_allclose(Error_Oracle(propagated, actual), 0., atol=2e-15)


def test_noise_mapping_finite_difference_and_density_squared_once():
    state = State_Create()
    def Noise_Rate(noise):
        # Fixed sensor reading: gyro measurement error enters opposite sign;
        # accelerometer driving process chosen positive (symmetric white noise).
        return np.r_[np.zeros(3), state.rotation @ noise[:3], -noise[3:6],
                     noise[6:9], noise[9:12], np.zeros(5)]
    assert_allclose(ref.Noise_Matrix(state.rotation), Jacobian_Finite(Noise_Rate, 12), atol=2e-15)
    density = np.linspace(.001, .02, 12)
    _, q1 = ref.Covariance_Discretize(state.rotation, [.3, .1, -.2], [1., 2., 9.], density, .02)
    _, q2 = ref.Covariance_Discretize(state.rotation, [.3, .1, -.2], [1., 2., 9.], density * 3, .02)
    assert_allclose(q2, q1 * 9, atol=3e-18, rtol=1e-10)
    assert np.linalg.eigvalsh(q1).min() > -1e-18
    assert_allclose(q1[15:, :], 0., atol=0.)


def test_first_fifteen_error_coordinates_match_existing_pure_math_reference():
    path = Path(__file__).resolve().parents[3] / "FLP/src/silverstar_flp/plugins/algorithms/eskf15/filter.py"
    spec = importlib.util.spec_from_file_location("eskf15_existing_math_only", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    state, omega, force = State_Create(), np.array([.2, -.3, .7]), np.array([1., 2., 9.])
    expected = module.Eskf15Filter().Dynamics_Jacobian(omega, force, state.rotation)
    assert_allclose(ref.Dynamics_Matrix(state.rotation, omega, force)[:15, :15], expected, atol=0.)
    correction = np.linspace(-.12, .12, 20)
    actual = ref.Error_ResetJacobian(correction)
    assert_allclose(actual[6:9, 6:9], module.Rotation_RightJacobian(correction[6:9]), atol=4e-16)


def test_static_noise_integral_independent_quadrature():
    state = State_Create()
    force, density, dt = np.array([1., 2., 9.]), np.linspace(.001, .02, 12), .02
    matrix = ref.Dynamics_Matrix(state.rotation, np.zeros(3), force)
    mapping = ref.Noise_Matrix(state.rotation)
    spectral = mapping @ np.diag(density ** 2) @ mapping.T
    expected, _ = quad_vec(lambda time: expm(matrix * time) @ spectral @ expm(matrix.T * time), 0., dt)
    transition, noise = ref.Covariance_Discretize(state.rotation, np.zeros(3), force, density, dt)
    assert_allclose(transition, expm(matrix * dt), atol=3e-16, rtol=1e-12)
    assert_allclose(noise, expected, atol=1e-19, rtol=2e-10)


def test_prediction_semigroup_preserves_full_cross_covariance_and_constants():
    state = State_Create()
    args = (np.array([.4, -.3, .7]), np.array([1., -.4, 9.6]),
            np.array([0., 0., -9.80665]), np.linspace(.001, .02, 12))
    full = ref.Eskf20_Predict(state, *args, .02)
    first = ref.Eskf20_Predict(state, *args, .01)
    second = ref.Eskf20_Predict(first.state, *args, .01)
    assert full.result is first.result is second.result is ref.NavigationEskf20Result.OK
    assert_allclose(Error_Oracle(full.state, second.state), 0., atol=5e-16)
    assert_allclose(full.state.covariance, second.state.covariance, atol=2e-17, rtol=2e-12)
    assert_allclose(full.state.covariance[15:, 15:], state.covariance[15:, 15:], atol=0.)
    assert not np.array_equal(full.state.covariance[:15, 15:], state.covariance[:15, 15:])


def test_magnetic_update_matches_independent_full_joseph_and_reset():
    state = State_Create()
    error = np.linspace(-.004, .005, 20)
    truth, sample = State_Oracle(state, error), Sample_Create(State_Oracle(state, error))
    matrix = ref.Magnetic_Jacobian(state)
    transform = state.rotation @ state.installation
    residual = transform @ sample.corrected_sensor_uT / sample.reference_strength_uT - Field_Oracle(state)
    noise = transform @ sample.covariance_sensor_uT2 @ transform.T / sample.reference_strength_uT ** 2
    gain = state.covariance @ matrix.T @ np.linalg.inv(matrix @ state.covariance @ matrix.T + noise)
    correction = gain @ residual
    updated = State_Oracle(state, correction)
    numeric_reset = Jacobian_Finite(lambda e: Error_Oracle(updated, State_Oracle(state, correction + e)), 20)
    contraction = np.eye(20) - gain @ matrix
    posterior = contraction @ state.covariance @ contraction.T + gain @ noise @ gain.T
    step = ref.Eskf20_UpdateMagnetic(state, sample, gate=20.)
    assert step.result is ref.NavigationEskf20Result.OK
    assert_allclose(Error_Oracle(updated, step.state), 0., atol=2e-15)
    assert_allclose(step.state.covariance, numeric_reset @ posterior @ numeric_reset.T, atol=4e-13, rtol=3e-8)
    before = np.linalg.norm(transform @ sample.corrected_sensor_uT / 48. - Field_Oracle(state))
    after = np.linalg.norm(step.state.rotation @ step.state.installation @ sample.corrected_sensor_uT / 48. - Field_Oracle(step.state))
    assert after < before / 10
    # Reduced residual is deliberately not an assertion that individual parameters converge.
    assert np.linalg.norm(Error_Oracle(step.state, truth)[6:]) > 1e-3


def test_nonzero_installation_synthetic_sequence_spd_with_missing_magnetics():
    truth = State_Create()
    estimate = State_Oracle(truth, np.linspace(-.001, .001, 20))
    gravity, density = np.array([0., 0., -9.80665]), np.full(12, .002)
    missing = 0
    for index in range(18):
        omega_m = np.array([.2 + .01 * index, -.1, .35]) + truth.gyro_bias
        force_m = np.array([.3, -.2 + .01 * index, 9.7]) + truth.accel_bias
        truth = Flow_Oracle(truth, omega_m, force_m, gravity, .01)
        step = ref.Eskf20_Predict(estimate, omega_m, force_m, gravity, density, .01)
        assert step.result is ref.NavigationEskf20Result.OK
        estimate = step.state
        sample = None if index % 3 else Sample_Create(truth)
        update = ref.Eskf20_UpdateMagnetic(estimate, sample, gate=20.)
        if sample is None:
            assert update.result is ref.NavigationEskf20Result.NO_OBSERVATION
            assert update.state is estimate
            missing += 1
        else:
            assert update.result is ref.NavigationEskf20Result.OK
        estimate = update.state
        for kind in ("position", "velocity"):
            update = ref.Eskf20_UpdateVector(estimate, getattr(truth, kind),
                                            np.eye(3) * .002, kind, truth.time_s, gate=20.)
            assert update.result is ref.NavigationEskf20Result.OK
            estimate = update.state
        np.linalg.cholesky(estimate.covariance)
        assert_allclose(estimate.covariance, estimate.covariance.T, atol=0.)
    assert missing == 12
    assert np.linalg.norm(Error_Oracle(estimate, truth)[:6]) < .002


@pytest.mark.parametrize("change", [
    {"frame": "system_body"}, {"calibration": "hard_soft_iron_and_installation"},
    {"calibration": "raw"}, {"time_s": -.01}, {"time_s": .01},
    {"reference_strength_uT": 0.}, {"reference_strength_uT": np.nan},
    {"corrected_sensor_uT": np.array([np.nan, 0., 1.])},
    {"corrected_sensor_uT": np.ones(2)}, {"corrected_sensor_uT": np.ones(3) * 1j},
    {"covariance_sensor_uT2": np.zeros((3, 3))},
    {"covariance_sensor_uT2": np.array([[1., .1, 0.], [0., 1., 0.], [0., 0., 1.]])},
])
def test_invalid_magnetic_boundary_is_transactional(change):
    state = State_Create()
    before = state.covariance.tobytes()
    result = ref.Eskf20_UpdateMagnetic(state, replace(Sample_Create(state), **change))
    assert result.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert result.state is state
    assert state.covariance.tobytes() == before


@pytest.mark.parametrize("gate", [0., -1., np.nan, np.inf])
def test_invalid_gate_is_transactional(gate):
    state = State_Create()
    step = ref.Eskf20_UpdateMagnetic(state, Sample_Create(state), gate)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


def test_nis_rejection_and_overflow_are_transactional():
    state = State_Create()
    sample = replace(Sample_Create(state), corrected_sensor_uT=np.array([480., 480., 480.]))
    step = ref.Eskf20_UpdateMagnetic(state, sample, .01)
    assert step.result is ref.NavigationEskf20Result.REJECTED_NIS
    assert step.state is state
    sample = replace(sample, corrected_sensor_uT=np.full(3, 1e308), reference_strength_uT=1e-308)
    step = ref.Eskf20_UpdateMagnetic(state, sample)
    assert step.result is ref.NavigationEskf20Result.NUMERIC_ERROR
    assert step.state is state


def test_large_correction_rejected_without_partial_injection():
    state = replace(State_Create(), covariance=np.eye(20) * .1)
    matrix = ref.Magnetic_Jacobian(state)
    direction = matrix[:, 6]
    transform = state.rotation @ state.installation
    measured = transform.T @ (Field_Oracle(state) + 10 * direction) * 48.
    step = ref.Eskf20_UpdateMagnetic(state, replace(Sample_Create(state), corrected_sensor_uT=measured))
    assert step.result is ref.NavigationEskf20Result.REJECTED_CORRECTION
    assert step.state is state


@pytest.mark.parametrize("dt", [0., -.01, .02001, np.nan, np.inf])
def test_invalid_prediction_time_transaction(dt):
    state = State_Create()
    step = ref.Eskf20_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(12), dt)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


@pytest.mark.parametrize("density", [np.full(12, -1.), np.full(12, np.nan), np.ones(11)])
def test_invalid_prediction_noise_transaction(density):
    state = State_Create()
    step = ref.Eskf20_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), density, .01)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


def test_predict_numeric_overflow_transaction():
    state = State_Create()
    step = ref.Eskf20_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3), np.full(12, 1e308), .01)
    assert step.result is ref.NavigationEskf20Result.NUMERIC_ERROR
    assert step.state is state


@pytest.mark.parametrize("change", [{"inclination": 1.6}, {"declination": np.nan},
    {"installation": np.diag([1., 1., -1.])}, {"covariance": np.eye(15)},
    {"covariance": np.zeros((20, 20))}])
def test_invalid_initial_state_rejected(change):
    with pytest.raises(ValueError):
        replace(State_Create(), **change)


def test_arrays_are_copied_read_only_and_input_measurement_unchanged():
    original = State_Create()
    position, covariance = original.position.copy(), original.covariance.copy()
    state = replace(original, position=position, covariance=covariance)
    position[0], covariance[0, 0] = 100., 100.
    assert state.position[0] == original.position[0]
    assert state.covariance[0, 0] == original.covariance[0, 0]
    with pytest.raises(ValueError):
        state.installation[0, 0] = 2.
    sample = Sample_Create(state)
    before = sample.corrected_sensor_uT.tobytes(), sample.covariance_sensor_uT2.tobytes()
    assert ref.Eskf20_UpdateMagnetic(state, sample).result is ref.NavigationEskf20Result.OK
    assert before == (sample.corrected_sensor_uT.tobytes(), sample.covariance_sensor_uT2.tobytes())


@pytest.mark.parametrize("kind,time", [("height", 0.), ("position", .1), ("velocity", -1.)])
def test_synthetic_vector_boundary_transaction(kind, time):
    state = State_Create()
    step = ref.Eskf20_UpdateVector(state, np.zeros(3), np.eye(3), kind, time)
    assert step.result is ref.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state
