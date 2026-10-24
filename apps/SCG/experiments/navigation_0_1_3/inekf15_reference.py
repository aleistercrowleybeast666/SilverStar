"""Bias-augmented left-invariant EKF, host float64 reference only.

Error: [Log(X_true^-1 X_hat), bg_hat-bg_true, ba_hat-ba_true].
The full augmented dynamics are NOT group-affine or exactly log-linear.
See INEKF_AUGMENTED_MODEL.md; no selectable component or device adapter.
"""
from dataclasses import dataclass, replace
from enum import Enum

import numpy as np
from scipy.linalg import expm

from inekf_reference import Navigation_ErrorDynamics, Navigation_PropagateGroup
from lie_group import (Array_Validate, Covariance_Validate, Group_Validate,
                       Lie_Exp, Lie_LeftJacobian, Scalar_Validate)


class NavigationAugmentedResult(Enum):
    OK = "ok"
    NO_OBSERVATION = "no_observation"
    INVALID_INPUT = "invalid_input"
    NUMERIC_ERROR = "numeric_error"
    REJECTED_NIS = "rejected_nis"
    REJECTED_CORRECTION = "rejected_correction"


@dataclass(frozen=True)
class InEkf15State:
    group: np.ndarray
    gyro_bias: np.ndarray
    accel_bias: np.ndarray
    covariance: np.ndarray
    time_s: float = 0.

    def __post_init__(self):
        fields = dict(group=Group_Validate(self.group),
            gyro_bias=Array_Validate(self.gyro_bias, (3,)),
            accel_bias=Array_Validate(self.accel_bias, (3,)),
            covariance=Covariance_Validate(self.covariance, 15))
        for name, array in fields.items():
            array.setflags(write=False)
            object.__setattr__(self, name, array)
        time = Scalar_Validate(self.time_s)
        if time < 0:
            raise ValueError("negative_time")
        object.__setattr__(self, "time_s", time)


@dataclass(frozen=True)
class AugmentedStep:
    result: NavigationAugmentedResult
    state: object
    nis: float | None = None
    magnetic_rank: int | None = None
    declination_sensitivity: float | None = None


def InEkf15_Dynamics(angular_rate, specific_force):
    matrix = np.zeros((15, 15))
    matrix[:9, :9] = Navigation_ErrorDynamics(angular_rate, specific_force)
    matrix[:3, 9:12] = -np.eye(3)
    matrix[3:6, 12:15] = -np.eye(3)
    return matrix


def InEkf15_NoiseMap():
    # Measurement noises enter positively; true bias random walks negatively.
    # Order: gyro, accel, gyro-bias RW, accel-bias RW.
    matrix = np.zeros((15, 12))
    matrix[:6, :6] = np.eye(6)
    matrix[9:15, 6:12] = -np.eye(6)
    return matrix


def InEkf15_Discretize(angular_rate, specific_force, density, dt):
    matrix = InEkf15_Dynamics(angular_rate, specific_force)
    density, dt = Array_Validate(density, (12,)), Scalar_Validate(dt)
    if np.any(density < 0) or not 0 < dt <= .02:
        raise ValueError("density_or_dt_domain")
    mapping = InEkf15_NoiseMap()
    spectral = mapping @ np.diag(density * density) @ mapping.T
    block = np.zeros((30, 30))
    block[:15, :15], block[:15, 15:], block[15:, 15:] = matrix, spectral, -matrix.T
    flow = expm(block * dt)
    transition = flow[:15, :15]
    covariance = flow[:15, 15:] @ transition.T
    return transition, .5 * (covariance + covariance.T)


def InEkf15_ResetJacobian(correction):
    delta = Array_Validate(correction, (15,))
    reset = np.eye(15)
    reset[:9, :9] = Lie_LeftJacobian(delta[:9])
    return reset


def InEkf15_Inject(state, correction, covariance=None):
    delta = Array_Validate(correction, (15,))
    return replace(state, group=state.group @ Lie_Exp(-delta[:9]),
        gyro_bias=state.gyro_bias - delta[9:12],
        accel_bias=state.accel_bias - delta[12:15],
        covariance=state.covariance if covariance is None else covariance)


def Coordinates_ToEskf15(group):
    """First-order map into [dp_n,dv_n,dtheta_b,dbg_true-hat,dba_true-hat]."""
    rotation = Group_Validate(group)[:3, :3]
    transform = np.zeros((15, 15))
    transform[:3, 6:9] = transform[3:6, 3:6] = -rotation
    transform[6:9, :3] = transform[9:12, 9:12] = transform[12:15, 12:15] = -np.eye(3)
    return transform


def Prediction_Inputs(state, angular_rate, specific_force, gravity, density, dt):
    omega, acceleration = Array_Validate(angular_rate, (3,)), Array_Validate(specific_force, (3,))
    gravity, density = Array_Validate(gravity, (3,)), Array_Validate(density, (12,))
    dt = Scalar_Validate(dt)
    if (not 0 < dt <= .02 or np.any(density < 0) or
            not np.isfinite(state.time_s + dt) or state.time_s + dt <= state.time_s):
        raise ValueError("noise_or_time_domain")
    return omega, acceleration, gravity, density, dt


def InEkf15_Predict(state, angular_rate, specific_force, gravity, density, dt):
    try:
        if type(state) is not InEkf15State:
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
            transition, noise = InEkf15_Discretize(omega, acceleration, density, dt)
            covariance = transition @ checked.covariance @ transition.T + noise
            updated = replace(checked, group=group, covariance=.5 * (covariance + covariance.T),
                              time_s=checked.time_s + dt)
        return AugmentedStep(NavigationAugmentedResult.OK, updated)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return AugmentedStep(NavigationAugmentedResult.NUMERIC_ERROR, state)


def Gate_Validate(gate):
    if gate is None:
        return None
    gate = Scalar_Validate(gate)
    if gate <= 0:
        raise ValueError("gate_domain")
    return gate


def Vector_Observation(group, measured, covariance_world, kind, size):
    # Caller has validated kind, arrays and state; helper is shared by the stages.
    rotation = group[:3, :3]
    column, offset = (4, 6) if kind == "position" else (3, 3)
    residual = rotation.T @ (group[:3, column] - measured)
    matrix = np.zeros((3, size))
    matrix[:, offset:offset + 3] = np.eye(3)
    return residual, matrix, rotation.T @ covariance_world @ rotation


def Kalman_Correction(covariance, residual, matrix, noise, gate):
    """Internal shared linear update; no state publication or covariance repair."""
    innovation = matrix @ covariance @ matrix.T + noise
    factor = np.linalg.cholesky(.5 * (innovation + innovation.T))
    whitened = np.linalg.solve(factor, residual)
    nis = float(whitened @ whitened)
    if not np.isfinite(nis):
        raise ArithmeticError("nonfinite_nis")
    if gate is not None and nis > gate:
        return NavigationAugmentedResult.REJECTED_NIS, None, None, nis
    gain = np.linalg.solve(factor.T, np.linalg.solve(factor, matrix @ covariance)).T
    correction = gain @ residual
    contraction = np.eye(covariance.shape[0]) - gain @ matrix
    posterior = contraction @ covariance @ contraction.T + gain @ noise @ gain.T
    return NavigationAugmentedResult.OK, correction, posterior, nis


def InEkf15_Update(state, measured, covariance_world, kind, time_s, gate=None):
    try:
        if type(state) is not InEkf15State:
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
            residual, matrix, noise = Vector_Observation(checked.group, measured, covariance_world, kind, 15)
            result, correction, posterior, nis = Kalman_Correction(checked.covariance, residual, matrix, noise, gate)
            if result is not NavigationAugmentedResult.OK:
                return AugmentedStep(result, state, nis)
            if np.linalg.norm(correction[:3]) > .35:
                return AugmentedStep(NavigationAugmentedResult.REJECTED_CORRECTION, state, nis)
            reset = InEkf15_ResetJacobian(correction)
            covariance = reset @ posterior @ reset.T
            updated = InEkf15_Inject(checked, correction, .5 * (covariance + covariance.T))
        return AugmentedStep(NavigationAugmentedResult.OK, updated, nis)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return AugmentedStep(NavigationAugmentedResult.NUMERIC_ERROR, state)
