"""Independent boundary/gauge/impulse checks; no adapter, hardware or data input."""
from dataclasses import replace

import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.linalg import expm, logm
from scipy.spatial.transform import Rotation

import eskf20_reference as eskf
import inekf_reference as inekf
import lie_group as lie


def State_Create():
    rng = np.random.default_rng(20261018)
    factor = rng.normal(size=(20, 20)) * .01
    return eskf.Eskf20State(np.array([.3, -.6, .1]), np.array([.4, .2, -.3]),
        Rotation.from_euler("xyz", [.3, -.5, .7]).as_matrix(),
        np.array([.01, -.02, .03]), np.array([.02, .04, -.03]),
        Rotation.from_euler("zyx", [-.4, .2, .3]).as_matrix(),
        .6, -.2, factor @ factor.T + np.eye(20) * .002)


def MagneticSample_Create(state):
    # Construct north/east/down geometry with rotations, not Magnetic_Field.
    field = Rotation.from_euler("z", -state.declination).apply(
        Rotation.from_euler("x", -state.inclination).apply([0., 1., 0.]))
    if abs(state.inclination) == np.pi / 2:
        field = np.array([0., 0., -np.sign(state.inclination)])
    return eskf.MagneticSample(48. * state.installation.T @ state.rotation.T @ field,
        np.diag([.02, .04, .03]), 48., state.time_s,
        "magnetometer_sensor", "hard_soft_iron_only")


@pytest.mark.parametrize("inclination", [-np.pi / 2, np.pi / 2])
def test_exact_pole_does_not_invent_declination_information(inclination):
    # Stress the declared finite/SPD domain, not a realistic sensor prior.
    # The exact geometric identity h(+-pi/2,D)=(0,0,-+1) is independent of D.
    state = replace(State_Create(), inclination=inclination,
                    covariance=np.diag([1e-6] * 19 + [1e28]))
    step = eskf.Eskf20_UpdateMagnetic(state, MagneticSample_Create(state))
    assert step.result is eskf.NavigationEskf20Result.OK
    assert step.state.covariance[19, 19] == state.covariance[19, 19]
    assert step.declination_sensitivity == 0.
    field, derivative_i, derivative_d = eskf.Magnetic_Field(inclination, -.2)
    assert_allclose(field, [0., 0., -np.sign(inclination)], atol=0., rtol=0.)
    assert_allclose(derivative_d, 0., atol=0., rtol=0.)
    assert np.linalg.norm(derivative_i) == pytest.approx(1.)


@pytest.mark.parametrize("distance", [1e-7, 1e-10])
def test_near_pole_is_not_clipped_to_zero(distance):
    # Compare against sin(distance), not cos(pi/2-distance) from the implementation.
    _, _, derivative_d = eskf.Magnetic_Field(np.pi / 2 - distance, .9)
    assert np.linalg.norm(derivative_d) == pytest.approx(np.sin(distance), abs=2e-16)
    assert np.linalg.norm(derivative_d) > 0.


@pytest.mark.parametrize("api", ["inekf_predict", "inekf_update", "eskf_predict",
                                  "eskf_vector", "eskf_magnetic"])
def test_oversized_integer_is_rejected_without_escaping_transaction(api):
    # A finite Python integer need not be representable as a finite float64.
    huge_vector = [10 ** 1000, 0, 0]
    if api.startswith("inekf"):
        state = inekf.NavigationState(np.eye(5), np.eye(9))
        before = state.group.tobytes(), state.covariance.tobytes()
        if api == "inekf_predict":
            step = inekf.NavigationInEkf_Predict(state, huge_vector, np.zeros(3),
                .01, np.zeros(6), np.zeros(3))
        else:
            step = inekf.NavigationInEkf_Update(state, huge_vector, np.eye(3), "position", 0.)
        assert step.result is inekf.NavigationInEkfResult.INVALID_INPUT
        assert before == (state.group.tobytes(), state.covariance.tobytes())
    else:
        state = State_Create()
        before = state.position.tobytes(), state.covariance.tobytes()
        if api == "eskf_predict":
            step = eskf.Eskf20_Predict(state, huge_vector, np.zeros(3),
                np.zeros(3), np.zeros(12), .01)
        elif api == "eskf_vector":
            step = eskf.Eskf20_UpdateVector(state, huge_vector, np.eye(3), "position", 0.)
        else:
            step = eskf.Eskf20_UpdateMagnetic(state,
                replace(MagneticSample_Create(state), corrected_sensor_uT=huge_vector))
        assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT
        assert before == (state.position.tobytes(), state.covariance.tobytes())
    assert step.state is state


@pytest.mark.parametrize("field", ["time_s", "inclination", "declination"])
@pytest.mark.parametrize("value", ["0.6", np.array([.6]), .6 + 0j])
def test_state_scalars_reject_non_real_scalar_values(field, value):
    with pytest.raises(ValueError):
        replace(State_Create(), **{field: value})


@pytest.mark.parametrize("value", [np.array([0.]), np.array([]), "0", 0j])
def test_inekf_time_requires_a_real_scalar(value):
    with pytest.raises(ValueError):
        inekf.NavigationState(np.eye(5), np.eye(9), value)


def test_scalar_state_values_are_copied_and_canonical():
    time, inclination, declination = np.array(0.), np.array(.6), np.array(-.2)
    first = inekf.NavigationState(np.eye(5), np.eye(9), time)
    second = replace(State_Create(), time_s=time, inclination=inclination, declination=declination)
    time[()], inclination[()], declination[()] = 2., .7, .3
    assert type(first.time_s) is type(second.time_s) is float
    assert type(second.inclination) is type(second.declination) is float
    assert first.time_s == second.time_s == 0.
    assert second.inclination == .6 and second.declination == -.2


@pytest.mark.parametrize("value", [np.array([0.]), 0j])
def test_eskf_observation_timestamp_requires_scalar_real_value(value):
    state = State_Create()
    for step in (eskf.Eskf20_UpdateVector(state, state.position, np.eye(3), "position", value),
                 eskf.Eskf20_UpdateMagnetic(state,
                    replace(MagneticSample_Create(state), time_s=value))):
        assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT
        assert step.state is state


def test_array_observation_kind_does_not_escape_inekf_transaction():
    state = inekf.NavigationState(np.eye(5), np.eye(9))
    step = inekf.NavigationInEkf_Update(state, np.zeros(3), np.eye(3),
                                      np.array(["position", "velocity"]), 0.)
    assert step.result is inekf.NavigationInEkfResult.UNSUPPORTED_OBSERVATION
    assert step.state is state


@pytest.mark.parametrize("api", ["inekf", "eskf"])
def test_vector_time_step_is_not_a_scalar(api):
    if api == "inekf":
        state = inekf.NavigationState(np.eye(5), np.eye(9))
        step = inekf.NavigationInEkf_Predict(state, np.zeros(3), np.zeros(3),
            np.array([.01]), np.zeros(6), np.zeros(3))
        assert step.result is inekf.NavigationInEkfResult.INVALID_INPUT
    else:
        state = State_Create()
        step = eskf.Eskf20_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3),
            np.zeros(12), np.array([.01]))
        assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


@pytest.mark.parametrize("api", ["inekf", "eskf"])
@pytest.mark.parametrize("field", ["rotation", "covariance"])
def test_overflow_while_validating_corrupt_state_is_transactional(api, field):
    state = inekf.NavigationState(np.eye(5), np.eye(9)) if api == "inekf" else State_Create()
    array = (state.covariance if field == "covariance" else
             state.group if api == "inekf" else state.rotation)
    array.setflags(write=True)
    if field == "rotation":
        array[0, 0] = 1e308
    else:
        array[0, 1], array[1, 0] = 1e308, -1e308
    array.setflags(write=False)
    before = array.tobytes()
    if api == "inekf":
        step = inekf.NavigationInEkf_Predict(state, np.zeros(3), np.zeros(3),
            .01, np.zeros(6), np.zeros(3))
        assert step.result is inekf.NavigationInEkfResult.INVALID_INPUT
    else:
        step = eskf.Eskf20_Predict(state, np.zeros(3), np.zeros(3), np.zeros(3),
            np.zeros(12), .01)
        assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state and array.tobytes() == before


@pytest.mark.parametrize("value", [np.array([48.]), np.complex128(48.), "48"])
def test_magnetic_strength_requires_real_scalar(value):
    state = State_Create()
    step = eskf.Eskf20_UpdateMagnetic(state,
        replace(MagneticSample_Create(state), reference_strength_uT=value))
    assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT
    assert step.state is state


@pytest.mark.parametrize("value", [np.array([20.]), np.complex128(20.), "20"])
def test_all_update_gates_require_real_scalars(value):
    state = State_Create()
    for step in (eskf.Eskf20_UpdateMagnetic(state, MagneticSample_Create(state), value),
                 eskf.Eskf20_UpdateVector(state, state.position, np.eye(3), "position", 0., value)):
        assert step.result is eskf.NavigationEskf20Result.INVALID_INPUT and step.state is state
    initial = inekf.NavigationState(np.eye(5), np.eye(9))
    step = inekf.NavigationInEkf_Update(initial, np.zeros(3), np.eye(3), "position", 0., value)
    assert step.result is inekf.NavigationInEkfResult.INVALID_INPUT and step.state is initial


def test_zero_dimensional_numeric_observations_remain_supported():
    state = State_Create()
    sample = replace(MagneticSample_Create(state), time_s=np.array(0.), reference_strength_uT=np.array(48.))
    step = eskf.Eskf20_UpdateMagnetic(state, sample, np.array(20.))
    assert step.result is eskf.NavigationEskf20Result.OK
    first = inekf.NavigationState(np.eye(5), np.eye(9))
    step = inekf.NavigationInEkf_Predict(first, np.zeros(3), np.zeros(3),
        np.array(.01), np.zeros(6), np.zeros(3))
    assert step.result is inekf.NavigationInEkfResult.OK and type(step.state.time_s) is float


def test_magnetometer_axis_relabeling_commutes_with_update():
    state = State_Create()
    sample = MagneticSample_Create(state)
    sample = replace(sample, corrected_sensor_uT=sample.corrected_sensor_uT + [.03, -.02, .01])
    axes = Rotation.from_euler("xyz", [.8, -.5, .6]).as_matrix()
    relabeled = replace(state, installation=state.installation @ axes)
    relabeled_sample = replace(sample, corrected_sensor_uT=axes.T @ sample.corrected_sensor_uT,
        covariance_sensor_uT2=axes.T @ sample.covariance_sensor_uT2 @ axes)
    first = eskf.Eskf20_UpdateMagnetic(state, sample)
    second = eskf.Eskf20_UpdateMagnetic(relabeled, relabeled_sample)
    assert first.result is second.result is eskf.NavigationEskf20Result.OK
    assert_allclose(first.state.rotation, second.state.rotation, atol=5e-15, rtol=0.)
    assert_allclose(first.state.installation @ axes, second.state.installation, atol=5e-15, rtol=0.)
    assert_allclose(first.state.covariance, second.state.covariance, atol=5e-17, rtol=1e-10)
    # Residual subtraction near zero amplifies coordinate roundoff in NIS.
    # Bound that amplification with ||S^-1|| <= 1/lambda_min(measurement noise).
    transform = state.rotation @ state.installation
    noise = transform @ sample.covariance_sensor_uT2 @ transform.T / 48. ** 2
    minimum = np.linalg.eigvalsh(noise)[0]
    residual_roundoff = 32 * np.finfo(float).eps
    nis_roundoff = (2 * np.sqrt(max(first.nis, second.nis) / minimum) * residual_roundoff
                   + residual_roundoff ** 2 / minimum)
    assert first.nis == pytest.approx(second.nis, abs=nis_roundoff)


def test_static_yaw_declination_gauge_survives_dynamics():
    state = replace(State_Create(), position=np.zeros(3), velocity=np.zeros(3))
    axis = np.array([0., 0., 1.])
    yaw = .4
    changed = replace(state, rotation=Rotation.from_rotvec(axis * yaw).as_matrix() @ state.rotation,
                      declination=state.declination - yaw)
    assert_allclose(MagneticSample_Create(state).corrected_sensor_uT,
                    MagneticSample_Create(changed).corrected_sensor_uT, atol=2e-14, rtol=0.)
    tangent = np.zeros(20)
    tangent[6:9], tangent[19] = state.rotation.T @ axis, 1.
    force = state.rotation.T @ np.array([0., 0., 9.81])
    transition, _ = eskf.Covariance_Discretize(state.rotation, np.zeros(3), force, np.zeros(12), .02)
    for count in range(6):
        propagated = np.linalg.matrix_power(transition, count) @ tangent
        # Products of three 3D rotations and repeated transition powers do not
        # preserve algebraic zeros to less than two machine epsilons.
        roundoff = 32 * np.finfo(float).eps
        assert_allclose(eskf.Magnetic_Jacobian(state) @ propagated, 0., atol=roundoff)
        assert_allclose(propagated[:6], 0., atol=roundoff)


def test_inekf_reset_with_general_matrix_exp_log_oracle():
    delta = np.array([.25, -.18, .11, .6, -.2, .3, 1.2, -.7, .2])
    def Hat(value):
        x, y, z = value[:3]
        matrix = np.zeros((5, 5))
        matrix[:3, :3] = [[0., -z, y], [z, 0., -x], [-y, x, 0.]]
        matrix[:3, 3], matrix[:3, 4] = value[3:6], value[6:9]
        return matrix
    def Reset(error):
        matrix = logm(expm(Hat(delta + error)) @ expm(-Hat(delta))).real
        return np.r_[matrix[2, 1], matrix[0, 2], matrix[1, 0], matrix[:3, 3], matrix[:3, 4]]
    step = 1e-5
    numeric = np.column_stack([(Reset(column) - Reset(-column)) / (2 * step)
                               for column in np.eye(9) * step])
    assert_allclose(lie.Lie_LeftJacobian(delta), numeric, atol=9e-11, rtol=1e-8)


def test_rotating_process_covariance_from_independent_physical_impulses():
    # Quadrature of physical noise impulses, never using F, G or the reference
    # retraction/propagator to construct the expected covariance.
    state = State_Create()
    omega_m, force_m = np.array([1.2, -.8, 2.1]), np.array([1.3, -.6, 9.4])
    gravity, duration = np.array([0., 0., -9.81]), .017
    nodes, weights = np.polynomial.legendre.leggauss(10)
    def Flow(position, velocity, rotation, gyro_bias, accel_bias, dt):
        omega, force = omega_m - gyro_bias, force_m - accel_bias
        times = (nodes + 1.) * dt / 2
        accelerations = np.array([rotation @ Rotation.from_rotvec(omega * t).apply(force)
                                  + gravity for t in times])
        final_velocity = velocity + dt / 2 * (weights @ accelerations)
        final_position = position + velocity * dt + dt / 2 * ((weights * (dt - times)) @ accelerations)
        return final_position, final_velocity, rotation @ Rotation.from_rotvec(omega * dt).as_matrix()
    base = (state.position, state.velocity, state.rotation, state.gyro_bias, state.accel_bias)
    end = Flow(*base, duration)
    density = np.linspace(.003, .04, 12)
    expected = np.zeros((20, 20))
    epsilon = 3e-5
    for node, weight in zip(nodes, weights):
        time = (node + 1.) * duration / 2
        position, velocity, rotation = Flow(*base, time)
        def Impulse(column, sign):
            noise = np.eye(12)[column] * (sign * epsilon)
            bg, ba = state.gyro_bias + noise[6:9], state.accel_bias + noise[9:12]
            actual = Flow(position, velocity + rotation @ noise[:3],
                rotation @ Rotation.from_rotvec(-noise[3:6]).as_matrix(), bg, ba, duration - time)
            return np.r_[actual[0] - end[0], actual[1] - end[1],
                Rotation.from_matrix(end[2].T @ actual[2]).as_rotvec(),
                noise[6:12], np.zeros(5)]
        columns = np.column_stack([(Impulse(j, 1) - Impulse(j, -1)) / (2 * epsilon)
                                    for j in range(12)])
        expected += weight * duration / 2 * (columns * density ** 2) @ columns.T
    _, actual = eskf.Covariance_Discretize(state.rotation, omega_m - state.gyro_bias,
        force_m - state.accel_bias, density, duration)
    assert_allclose(actual, expected, atol=5e-15, rtol=2e-7)
