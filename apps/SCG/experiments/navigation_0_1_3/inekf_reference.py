"""Host-only, bias-free left-invariant EKF on SE_2(3), reference revision 1.

No sensor decoder, calibration/alignment implementation, scheduling, logging,
READY flag, firmware binding or selectable component is provided here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy.linalg import expm

from lie_group import (Array_Validate, Covariance_Validate, Group_Validate,
                       Lie_Exp, Lie_LeftJacobian, Scalar_Validate, Vector_Skew)


class NavigationInEkfResult(Enum):
    OK = "ok"
    INVALID_INPUT = "invalid_input"
    NUMERIC_ERROR = "numeric_error"
    REJECTED_NIS = "rejected_nis"
    UNSUPPORTED_OBSERVATION = "unsupported_observation"


@dataclass(frozen=True)
class NavigationState:
    group: np.ndarray
    covariance: np.ndarray
    time_s: float = 0.

    def __post_init__(self):
        group = Group_Validate(self.group)
        covariance = Covariance_Validate(self.covariance, 9)
        time_s = Scalar_Validate(self.time_s)
        if time_s < 0:
            raise ValueError("invalid_time")
        group.setflags(write=False)
        covariance.setflags(write=False)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "time_s", time_s)


@dataclass(frozen=True)
class NavigationStep:
    result: NavigationInEkfResult
    state: NavigationState
    nis: float | None = None


def Navigation_ErrorDynamics(angular_rate, specific_force):
    omega = Vector_Skew(angular_rate)
    acceleration = Vector_Skew(specific_force)
    matrix = np.kron(np.eye(3), -omega)
    matrix[3:6, :3] = -acceleration
    matrix[6:9, 3:6] = np.eye(3)
    return matrix


def Navigation_VectorField(group, angular_rate, specific_force, gravity):
    group = Group_Validate(group)
    acceleration = Array_Validate(specific_force, (3,))
    gravity = Array_Validate(gravity, (3,))
    field = np.zeros((5, 5))
    field[:3, :3] = group[:3, :3] @ Vector_Skew(angular_rate)
    field[:3, 3] = group[:3, :3] @ acceleration + gravity
    field[:3, 4] = group[:3, 3]
    return field


def Navigation_PropagateGroup(group, angular_rate, specific_force, gravity, dt):
    """Exact nominal flow for held body omega/a and constant world gravity."""
    group = Group_Validate(group)
    acceleration = Array_Validate(specific_force, (3,))
    gravity = Array_Validate(gravity, (3,))
    dt = Scalar_Validate(dt)
    if not 0 < dt <= 0.02:
        raise ValueError("dt_outside_reference_domain")
    block = np.zeros((9, 9))
    block[:3, :3] = Vector_Skew(angular_rate)
    block[:3, 3:6] = np.eye(3)
    block[3:6, 6:9] = np.eye(3)
    flow = expm(block * dt)
    result = np.eye(5)
    rotation, velocity, position = group[:3, :3], group[:3, 3], group[:3, 4]
    result[:3, :3] = rotation @ flow[:3, :3]
    result[:3, 3] = velocity + gravity * dt + rotation @ flow[:3, 3:6] @ acceleration
    result[:3, 4] = (position + velocity * dt + gravity * (0.5 * dt * dt) +
                      rotation @ flow[:3, 6:9] @ acceleration)
    return Group_Validate(result)


def Navigation_Discretize(matrix, density, dt):
    """Held A, body gyro/accel amplitude densities; exact linear SDE integral."""
    matrix = Array_Validate(matrix, (9, 9))
    density = Array_Validate(density, (6,))
    dt = Scalar_Validate(dt)
    if np.any(density < 0) or not 0 < dt <= 0.02:
        raise ValueError("invalid_noise_or_dt")
    continuous = np.diag(np.r_[density * density, np.zeros(3)])
    block = np.zeros((18, 18))
    block[:9, :9], block[:9, 9:] = matrix, continuous
    block[9:, 9:] = -matrix.T
    flow = expm(block * dt)
    transition = flow[:9, :9]
    noise = flow[:9, 9:] @ transition.T
    return transition, 0.5 * (noise + noise.T)


def NavigationInEkf_Predict(state, angular_rate, specific_force, dt, density, gravity):
    """Return a new state on success; any rejection preserves the input object."""
    try:
        checked = NavigationState(state.group, state.covariance, state.time_s)
        omega = Array_Validate(angular_rate, (3,))
        acceleration = Array_Validate(specific_force, (3,))
        gravity = Array_Validate(gravity, (3,))
        density = Array_Validate(density, (6,))
        dt = Scalar_Validate(dt)
        if (not 0 < dt <= 0.02 or np.any(density < 0) or
                not np.isfinite(checked.time_s + dt) or checked.time_s + dt <= checked.time_s):
            raise ValueError("invalid_noise_or_time")
    except (ValueError, TypeError, AttributeError):
        return NavigationStep(NavigationInEkfResult.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            group = Navigation_PropagateGroup(checked.group, omega, acceleration, gravity, dt)
            transition, noise = Navigation_Discretize(
                Navigation_ErrorDynamics(omega, acceleration), density, dt)
            covariance = transition @ checked.covariance @ transition.T + noise
            covariance = 0.5 * (covariance + covariance.T)
            result = NavigationState(group, covariance, checked.time_s + dt)
        return NavigationStep(NavigationInEkfResult.OK, result)
    except (ValueError, np.linalg.LinAlgError, FloatingPointError):
        return NavigationStep(NavigationInEkfResult.NUMERIC_ERROR, state)


def Navigation_ObservationMatrix(kind):
    if not isinstance(kind, str) or kind not in ("position", "velocity"):
        raise ValueError("unsupported_observation")
    matrix = np.zeros((3, 9))
    start = 6 if kind == "position" else 3
    matrix[:, start:start + 3] = np.eye(3)
    return matrix


def Navigation_Residual(group, observation, kind):
    group = Group_Validate(group)
    observation = Array_Validate(observation, (3,))
    Navigation_ObservationMatrix(kind)
    column = 4 if kind == "position" else 3
    return group[:3, :3].T @ (group[:3, column] - observation)


def NavigationInEkf_Update(state, observation, covariance_world, kind, time_s,
                          nis_threshold=None):
    """Co-timed 3D world position/velocity, zero lever arm, explicit optional gate."""
    if not isinstance(kind, str) or kind not in ("position", "velocity"):
        return NavigationStep(NavigationInEkfResult.UNSUPPORTED_OBSERVATION, state)
    try:
        checked = NavigationState(state.group, state.covariance, state.time_s)
        observation = Array_Validate(observation, (3,))
        covariance_world = Covariance_Validate(covariance_world, 3)
        time_s = Scalar_Validate(time_s)
        if time_s != checked.time_s:
            raise ValueError("measurement_not_at_state_time")
        if nis_threshold is not None:
            nis_threshold = Scalar_Validate(nis_threshold)
            if nis_threshold <= 0:
                raise ValueError("invalid_gate")
    except (ValueError, TypeError, AttributeError):
        return NavigationStep(NavigationInEkfResult.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _Navigation_UpdateValidated(checked, state, observation, covariance_world,
                                               kind, nis_threshold)
    except (ValueError, np.linalg.LinAlgError, FloatingPointError):
        return NavigationStep(NavigationInEkfResult.NUMERIC_ERROR, state)


def _Navigation_UpdateValidated(checked, original, observation, covariance_world, kind, threshold):
    rotation = checked.group[:3, :3]
    residual = Navigation_Residual(checked.group, observation, kind)
    matrix = Navigation_ObservationMatrix(kind)
    noise = rotation.T @ covariance_world @ rotation
    innovation = matrix @ checked.covariance @ matrix.T + noise
    lower = np.linalg.cholesky(innovation)
    whitened = np.linalg.solve(lower, residual)
    nis = float(whitened @ whitened)
    if not np.isfinite(nis):
        raise ValueError("nonfinite_nis")
    if threshold is not None and nis > threshold:
        return NavigationStep(NavigationInEkfResult.REJECTED_NIS, original, nis)
    gain = np.linalg.solve(lower.T, np.linalg.solve(lower, matrix @ checked.covariance)).T
    correction = gain @ residual
    if np.linalg.norm(correction[:3]) >= np.pi - 1e-7:
        raise ValueError("correction_outside_principal_chart")
    group = checked.group @ Lie_Exp(-correction)
    residual_map = np.eye(9) - gain @ matrix
    joseph = (residual_map @ checked.covariance @ residual_map.T + gain @ noise @ gain.T)
    # eta_new = Exp(xi) Exp(-correction); derivative at xi=correction is J_left.
    reset = Lie_LeftJacobian(correction)
    covariance = reset @ joseph @ reset.T
    covariance = 0.5 * (covariance + covariance.T)
    result = NavigationState(group, covariance, checked.time_s)
    return NavigationStep(NavigationInEkfResult.OK, result, nis)
