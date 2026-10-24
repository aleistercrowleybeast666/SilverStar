"""Small independent physical checks; no production, adapter or device access."""
from dataclasses import replace
from pathlib import Path
import json
import sys

import numpy as np
from numpy.testing import assert_allclose
from scipy.linalg import expm, logm
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import inekf15_reference as r15
import inekf20_reference as r20
from eskf20_reference import MagneticSample

NODES, WEIGHTS = np.polynomial.legendre.leggauss(10)
WM = np.array([1.7, -.8, 2.2])
AM = np.array([1.3, -.9, 9.4])
GRAVITY = np.array([0., 0., -9.81])
DT = .019


def State_Create():
    group = np.eye(5)
    group[:3, :3] = Rotation.from_euler("zyx", [.8, -.4, .25]).as_matrix()
    group[:3, 3], group[:3, 4] = [.3, -.2, .5], [.4, -.6, .2]
    factor = np.random.default_rng(201813).normal(size=(20, 20)) * .025
    return r20.InEkf20State(group, [.03, -.02, .015], [.04, -.06, .03],
        Rotation.from_euler("xyz", [.3, -.5, .2]).as_matrix(), .81, -.47,
        factor @ factor.T + np.eye(20) * .004, 0.)


def Flow(group, bg, ba, dt):
    """Independent SO(3) rotation plus physical acceleration quadrature."""
    rotation, velocity, position = group[:3, :3], group[:3, 3], group[:3, 4]
    omega, force = WM - bg, AM - ba
    times = (NODES + 1.) * dt / 2
    accelerations = np.array([rotation @ Rotation.from_rotvec(omega * t).apply(force)
                              + GRAVITY for t in times])
    result = np.eye(5)
    result[:3, :3] = rotation @ Rotation.from_rotvec(omega * dt).as_matrix()
    result[:3, 3] = velocity + dt / 2 * WEIGHTS @ accelerations
    result[:3, 4] = position + velocity * dt + dt / 2 * (WEIGHTS * (dt - times)) @ accelerations
    return result


def Error(nominal, truth, bg_difference, ba_difference):
    matrix = logm(np.linalg.solve(truth, nominal))
    assert np.max(np.abs(matrix.imag)) < 1e-12
    matrix = matrix.real
    return np.r_[matrix[2, 1], matrix[0, 2], matrix[1, 0], matrix[:3, 3], matrix[:3, 4],
                 bg_difference, ba_difference]


def Physical_ImpulseCovariance():
    state, epsilon = State_Create(), 4e-5
    end = Flow(state.group, state.gyro_bias, state.accel_bias, DT)
    density = np.linspace(.004, .04, 12)
    expected = np.zeros((15, 15))
    for node, weight in zip(NODES, WEIGHTS):
        time = (node + 1.) * DT / 2
        at_impulse = Flow(state.group, state.gyro_bias, state.accel_bias, time)
        def Impulse(column, sign):
            impulse = np.eye(12)[column] * sign * epsilon
            truth = at_impulse.copy()
            # Fix measured IMU input: sensor noise gives the opposite true motion.
            truth[:3, :3] = at_impulse[:3, :3] @ Rotation.from_rotvec(-impulse[:3]).as_matrix()
            truth[:3, 3] -= at_impulse[:3, :3] @ impulse[3:6]
            bg, ba = state.gyro_bias + impulse[6:9], state.accel_bias + impulse[9:12]
            truth = Flow(truth, bg, ba, DT - time)
            return Error(end, truth, -impulse[6:9], -impulse[9:12])
        columns = np.column_stack([(Impulse(j, 1) - Impulse(j, -1)) / (2 * epsilon)
                                    for j in range(12)])
        expected += weight * DT / 2 * (columns * density ** 2) @ columns.T
    _, actual = r15.InEkf15_Discretize(WM - state.gyro_bias, AM - state.accel_bias, density, DT)
    assert_allclose(actual, expected, atol=3e-15, rtol=3e-7)
    return expected, density, float(np.max(np.abs(actual - expected)))


def Full_CovariancePrediction(noise, density):
    state, epsilon = State_Create(), 4e-5
    end = Flow(state.group, state.gyro_bias, state.accel_bias, DT)
    def Perturb(column, sign):
        # Perturb physical quantities one at a time, not the implementation's
        # retraction, F, G, or conventional-ESKF coordinate conversion.
        perturbation = np.eye(20)[column] * sign * epsilon
        truth = state.group.copy()
        truth[:3, :3] = state.group[:3, :3] @ Rotation.from_rotvec(-perturbation[:3]).as_matrix()
        truth[:3, 3] -= state.group[:3, :3] @ perturbation[3:6]
        truth[:3, 4] -= state.group[:3, :3] @ perturbation[6:9]
        truth = Flow(truth, state.gyro_bias - perturbation[9:12],
                     state.accel_bias - perturbation[12:15], DT)
        return np.r_[Error(end, truth, perturbation[9:12], perturbation[12:15]), perturbation[15:]]
    transition = np.column_stack([(Perturb(j, 1) - Perturb(j, -1)) / (2 * epsilon)
                                   for j in range(20)])
    full_noise = np.zeros((20, 20)); full_noise[:15, :15] = noise
    expected = transition @ state.covariance @ transition.T + full_noise
    step = r20.InEkf20_Predict(state, WM, AM, GRAVITY, density, DT)
    assert step.result is r15.NavigationAugmentedResult.OK
    assert_allclose(step.state.covariance, expected, atol=8e-12, rtol=5e-8)
    return float(np.max(np.abs(step.state.covariance - expected)))


def Bias_RandomWalkClosedForm():
    # Integrals of actual Brownian bias: e_phi=-int zeta_g, e_nu=-int zeta_a,
    # e_rho=-int int zeta_a. These signs and coefficients do not use F/G.
    density = np.r_[np.zeros(6), [.013, .021, .031], [.017, .023, .037]]
    _, actual = r15.InEkf15_Discretize(np.zeros(3), np.zeros(3), density, DT)
    expected = np.zeros((15, 15))
    for axis in range(3):
        g, a = density[6 + axis] ** 2, density[9 + axis] ** 2
        phi, nu, rho, bg, ba = axis, 3 + axis, 6 + axis, 9 + axis, 12 + axis
        expected[phi, phi], expected[bg, bg] = g * DT ** 3 / 3, g * DT
        expected[phi, bg] = expected[bg, phi] = -g * DT ** 2 / 2
        expected[nu, nu], expected[rho, rho], expected[ba, ba] = a * DT ** 3 / 3, a * DT ** 5 / 20, a * DT
        expected[nu, ba] = expected[ba, nu] = -a * DT ** 2 / 2
        expected[rho, ba] = expected[ba, rho] = -a * DT ** 3 / 6
        expected[nu, rho] = expected[rho, nu] = a * DT ** 4 / 8
    assert_allclose(actual, expected, atol=3e-21, rtol=3e-13)
    assert actual[0, 9] < 0 and actual[3, 12] < 0 and actual[6, 12] < 0
    return float(np.max(np.abs(actual - expected)))


def Sample_Create(state):
    field = Rotation.from_euler("z", -state.declination).apply(
        Rotation.from_euler("x", -state.inclination).apply([0., 1., 0.]))
    sensor = 48. * state.installation.T @ state.group[:3, :3].T @ field
    covariance = np.array([[.03, .004, -.002], [.004, .02, .001], [-.002, .001, .04]])
    return MagneticSample(sensor + [.025, -.035, .02], covariance, 48., state.time_s,
                          "magnetometer_sensor", "hard_soft_iron_only")


def Imu_BasisEquivariance():
    # Change IMU basis, leaving navigation and magnetometer coordinates fixed.
    # Isotropic densities per source make the diagonal-noise API closed under B.
    state = State_Create()
    basis = Rotation.from_euler("xyz", [-.7, .4, .6]).as_matrix()
    transform = np.eye(20)
    transform[:18, :18] = np.kron(np.eye(6), basis)
    group = state.group.copy(); group[:3, :3] = group[:3, :3] @ basis.T
    changed = replace(state, group=group, gyro_bias=basis @ state.gyro_bias,
        accel_bias=basis @ state.accel_bias, installation=basis @ state.installation,
        covariance=transform @ state.covariance @ transform.T)
    density = np.repeat([.004, .02, .001, .006], 3)
    first = r20.InEkf20_Predict(state, WM, AM, GRAVITY, density, DT)
    second = r20.InEkf20_Predict(changed, basis @ WM, basis @ AM, GRAVITY, density, DT)
    for a, b in ((first, second),
        (r20.InEkf20_UpdateMagnetic(first.state, Sample_Create(first.state)),
         r20.InEkf20_UpdateMagnetic(second.state, Sample_Create(first.state)))):
        assert a.result is b.result is r15.NavigationAugmentedResult.OK
        assert_allclose(a.state.group[:3, :3] @ basis.T, b.state.group[:3, :3], atol=2e-14, rtol=0.)
        assert_allclose(a.state.group[:3, 3:], b.state.group[:3, 3:], atol=2e-14, rtol=0.)
        assert_allclose(basis @ a.state.installation, b.state.installation, atol=2e-14, rtol=0.)
        assert_allclose(basis @ a.state.gyro_bias, b.state.gyro_bias, atol=2e-14, rtol=0.)
        assert_allclose(basis @ a.state.accel_bias, b.state.accel_bias, atol=2e-14, rtol=0.)
        assert_allclose([a.state.inclination, a.state.declination],
                        [b.state.inclination, b.state.declination], atol=2e-14, rtol=0.)
        assert_allclose(transform @ a.state.covariance @ transform.T, b.state.covariance,
                        atol=2e-15, rtol=2e-10)
    return float(np.max(np.abs(transform @ a.state.covariance @ transform.T - b.state.covariance)))


def Inclination_CrossCovarianceBoundary():
    covariance = np.eye(20) * .02
    covariance[18, 6] = covariance[6, 18] = .01
    state = replace(State_Create(), group=np.eye(5), inclination=np.pi / 2 - 1e-4,
                    covariance=covariance)
    before = (state.group.tobytes(), state.covariance.tobytes(), state.inclination)
    bad = r20.InEkf20_UpdateVector(state, [.01, 0., 0.], np.eye(3) * .01, "position", 0.)
    assert bad.result is r15.NavigationAugmentedResult.REJECTED_CORRECTION and bad.state is state
    assert before == (state.group.tobytes(), state.covariance.tobytes(), state.inclination)
    good = r20.InEkf20_UpdateVector(state, [-.01, 0., 0.], np.eye(3) * .01, "position", 0.)
    assert good.result is r15.NavigationAugmentedResult.OK
    assert good.state.inclination < state.inclination
    return dict(outward=bad.result.value, inward=good.result.value,
                inclination_delta=good.state.inclination - state.inclination)


if __name__ == "__main__":
    np.seterr(over="raise", invalid="raise", divide="raise")
    noise, density, impulse_error = Physical_ImpulseCovariance()
    metrics = dict(physical_impulse_q_max_abs_error=impulse_error,
        bias_random_walk_closed_form_max_abs_error=Bias_RandomWalkClosedForm(),
        independent_full_p_max_abs_error=Full_CovariancePrediction(noise, density),
        imu_basis_reset_covariance_max_abs_error=Imu_BasisEquivariance(),
        inclination_cross_covariance_transaction=Inclination_CrossCovarianceBoundary())
    print(json.dumps(dict(result="PASS", scope="five independent targeted host mathematical checks",
                         metrics=metrics), indent=2))
