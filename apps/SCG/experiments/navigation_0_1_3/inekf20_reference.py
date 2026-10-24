"""Host-only imperfect InEKF20: SE_2(3), biases, magnetometer installation/I/D.

Error = [phi,nu,rho,zeta_g,zeta_a,gamma_b,dI,dD]; full 20x20 covariance.
No strict group-affine/log-linear assertion for this augmented model.
"""
from dataclasses import dataclass, replace

import numpy as np
from scipy.linalg import expm

from eskf20_reference import Magnetic_Field, Rotation_Validate
from inekf_reference import Navigation_PropagateGroup
from inekf15_reference import (AugmentedStep, Coordinates_ToEskf15, Gate_Validate,
    InEkf15_Discretize, InEkf15_Dynamics, InEkf15_ResetJacobian, Kalman_Correction,
    NavigationAugmentedResult, Prediction_Inputs, Vector_Observation)
from lie_group import (Array_Validate, Covariance_Validate, Group_Validate, Lie_Exp,
                       Matrix_IntegralExp, Scalar_Validate, Vector_Skew)


@dataclass(frozen=True)
class InEkf20State:
    group: np.ndarray
    gyro_bias: np.ndarray
    accel_bias: np.ndarray
    installation: np.ndarray            # A: magnetic sensor -> IMU
    inclination: float                  # downward positive, radians
    declination: float                  # east of north positive, radians
    covariance: np.ndarray
    time_s: float = 0.

    def __post_init__(self):
        fields = dict(group=Group_Validate(self.group),
            gyro_bias=Array_Validate(self.gyro_bias, (3,)),
            accel_bias=Array_Validate(self.accel_bias, (3,)),
            installation=Rotation_Validate(self.installation),
            covariance=Covariance_Validate(self.covariance, 20))
        for name, array in fields.items():
            array.setflags(write=False)
            object.__setattr__(self, name, array)
        for name in ("time_s", "inclination", "declination"):
            object.__setattr__(self, name, Scalar_Validate(getattr(self, name)))
        if self.time_s < 0 or abs(self.inclination) > np.pi / 2:
            raise ValueError("time_or_inclination_domain")


def InEkf20_Dynamics(angular_rate, specific_force):
    matrix = np.zeros((20, 20))
    matrix[:15, :15] = InEkf15_Dynamics(angular_rate, specific_force)
    return matrix


def InEkf20_Discretize(angular_rate, specific_force, density, dt):
    transition, noise = InEkf15_Discretize(angular_rate, specific_force, density, dt)
    full_transition, full_noise = np.eye(20), np.zeros((20, 20))
    full_transition[:15, :15], full_noise[:15, :15] = transition, noise
    return full_transition, full_noise


def Coordinates_ToEskf20(group):
    transform = np.eye(20)
    transform[:15, :15] = Coordinates_ToEskf15(group)
    return transform


def InEkf20_ResetJacobian(correction):
    delta = Array_Validate(correction, (20,))
    reset = np.eye(20)
    reset[:15, :15] = InEkf15_ResetJacobian(delta[:15])
    reset[15:18, 15:18] = Matrix_IntegralExp(-Vector_Skew(delta[15:18]))
    return reset


def InEkf20_Inject(state, correction, covariance=None):
    delta = Array_Validate(correction, (20,))
    return replace(state, group=state.group @ Lie_Exp(-delta[:9]),
        gyro_bias=state.gyro_bias - delta[9:12], accel_bias=state.accel_bias - delta[12:15],
        installation=expm(-Vector_Skew(delta[15:18])) @ state.installation,
        inclination=state.inclination - delta[18], declination=state.declination - delta[19],
        covariance=state.covariance if covariance is None else covariance)


def InEkf20_MagneticJacobian(state):
    field, derivative_i, derivative_d = Magnetic_Field(state.inclination, state.declination)
    matrix = np.zeros((3, 20))
    # phi is estimate-minus-true: opposite attitude sign to ESKF20 theta.
    matrix[:, :3] = matrix[:, 15:18] = -Vector_Skew(field) @ state.group[:3, :3]
    matrix[:, 18], matrix[:, 19] = -derivative_i, -derivative_d
    return matrix


def InEkf20_Predict(state, angular_rate, specific_force, gravity, density, dt):
    try:
        if type(state) is not InEkf20State:
            raise ValueError("wrong_state_type")
        checked = replace(state)
        omega, acceleration, gravity, density, dt = Prediction_Inputs(
            checked, angular_rate, specific_force, gravity, density, dt)
    except (ValueError, TypeError, AttributeError):
        return AugmentedStep(NavigationAugmentedResult.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            omega, acceleration = omega - checked.gyro_bias, acceleration - checked.accel_bias
            group = Navigation_PropagateGroup(checked.group, omega, acceleration, gravity, dt)
            transition, noise = InEkf20_Discretize(omega, acceleration, density, dt)
            covariance = transition @ checked.covariance @ transition.T + noise
            updated = replace(checked, group=group, covariance=.5 * (covariance + covariance.T),
                              time_s=checked.time_s + dt)
        return AugmentedStep(NavigationAugmentedResult.OK, updated)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return AugmentedStep(NavigationAugmentedResult.NUMERIC_ERROR, state)


def InEkf20_Apply(state, residual, matrix, noise, gate):
    """Internal helper; state publication only after full injection/reset succeeds."""
    result, correction, posterior, nis = Kalman_Correction(state.covariance, residual, matrix, noise, gate)
    if result is not NavigationAugmentedResult.OK:
        return AugmentedStep(result, state, nis)
    if (np.linalg.norm(correction[:3]) > .35 or np.linalg.norm(correction[15:18]) > .35 or
            abs(state.inclination - correction[18]) > np.pi / 2):
        return AugmentedStep(NavigationAugmentedResult.REJECTED_CORRECTION, state, nis)
    reset = InEkf20_ResetJacobian(correction)
    covariance = reset @ posterior @ reset.T
    updated = InEkf20_Inject(state, correction, .5 * (covariance + covariance.T))
    return AugmentedStep(NavigationAugmentedResult.OK, updated, nis)


def InEkf20_UpdateMagnetic(state, sample, gate=None):
    try:
        if type(state) is not InEkf20State:
            raise ValueError("wrong_state_type")
        checked, gate = replace(state), Gate_Validate(gate)
        if sample is None:
            return AugmentedStep(NavigationAugmentedResult.NO_OBSERVATION, state)
        time_s, strength = Scalar_Validate(sample.time_s), Scalar_Validate(sample.reference_strength_uT)
        if (not isinstance(sample.frame, str) or sample.frame != "magnetometer_sensor" or
                not isinstance(sample.calibration, str) or sample.calibration != "hard_soft_iron_only" or
                time_s != checked.time_s or strength <= 0):
            raise ValueError("magnetic_boundary")
        measured = Array_Validate(sample.corrected_sensor_uT, (3,))
        noise = Covariance_Validate(sample.covariance_sensor_uT2, 3)
    except (ValueError, TypeError, AttributeError):
        return AugmentedStep(NavigationAugmentedResult.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            measured, noise = measured / strength, noise / strength / strength
            noise = Covariance_Validate(noise, 3)
            transform = checked.group[:3, :3] @ checked.installation
            field, _, derivative_d = Magnetic_Field(checked.inclination, checked.declination)
            residual = transform @ measured - field
            matrix = InEkf20_MagneticJacobian(checked)
            step = InEkf20_Apply(checked, residual, matrix, transform @ noise @ transform.T, gate)
        return replace(step, state=step.state if step.result is NavigationAugmentedResult.OK else state,
            magnetic_rank=int(np.linalg.matrix_rank(matrix)),
            declination_sensitivity=float(np.linalg.norm(derivative_d)))
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return AugmentedStep(NavigationAugmentedResult.NUMERIC_ERROR, state)


def InEkf20_UpdateVector(state, measured, covariance_world, kind, time_s, gate=None):
    try:
        if type(state) is not InEkf20State:
            raise ValueError("wrong_state_type")
        checked = replace(state)
        time_s, gate = Scalar_Validate(time_s), Gate_Validate(gate)
        if not isinstance(kind, str) or kind not in ("position", "velocity") or time_s != checked.time_s:
            raise ValueError("observation_boundary")
        if measured is None:
            return AugmentedStep(NavigationAugmentedResult.NO_OBSERVATION, state)
        measured = Array_Validate(measured, (3,))
        covariance_world = Covariance_Validate(covariance_world, 3)
    except (ValueError, TypeError, AttributeError):
        return AugmentedStep(NavigationAugmentedResult.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            residual, matrix, noise = Vector_Observation(checked.group, measured, covariance_world, kind, 20)
            step = InEkf20_Apply(checked, residual, matrix, noise, gate)
        return replace(step, state=step.state if step.result is NavigationAugmentedResult.OK else state)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return AugmentedStep(NavigationAugmentedResult.NUMERIC_ERROR, state)
