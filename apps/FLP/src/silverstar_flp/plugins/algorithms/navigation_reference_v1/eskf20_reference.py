"""Float64 host experiment; see ESKF20_MODEL.md. No production entry point."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

from .navigation_flow import Navigation_PropagateGroup
from .lie_group import (Array_Validate, Covariance_Validate, Group_Validate,
                       Matrix_IntegralExp, Scalar_Validate, Vector_Skew)


class NavigationEskf20Result(Enum):
    OK = "ok"
    NO_OBSERVATION = "no_observation"
    INVALID_INPUT = "invalid_input"
    NUMERIC_ERROR = "numeric_error"
    REJECTED_NIS = "rejected_nis"
    REJECTED_CORRECTION = "rejected_correction"


def Rotation_Validate(value):
    group = np.eye(5)
    group[:3, :3] = Array_Validate(value, (3, 3))
    return Group_Validate(group)[:3, :3].copy()


@dataclass(frozen=True)
class Eskf20State:
    position: np.ndarray
    velocity: np.ndarray
    rotation: np.ndarray                 # C^n_b, IMU -> ENU
    gyro_bias: np.ndarray
    accel_bias: np.ndarray
    installation: np.ndarray             # A = C^b_bm, magnetometer -> IMU
    inclination: float                    # radians, downward positive
    declination: float                    # radians, east of north positive
    covariance: np.ndarray               # dp,dv,dtheta_b,dbg,dba,gamma_b,dI,dD
    time_s: float = 0.

    def __post_init__(self):
        for name in ("position", "velocity", "gyro_bias", "accel_bias"):
            array = Array_Validate(getattr(self, name), (3,))
            array.setflags(write=False)
            object.__setattr__(self, name, array)
        for name in ("rotation", "installation"):
            array = Rotation_Validate(getattr(self, name))
            array.setflags(write=False)
            object.__setattr__(self, name, array)
        for name in ("inclination", "declination", "time_s"):
            object.__setattr__(self, name, Scalar_Validate(getattr(self, name)))
        if abs(self.inclination) > np.pi / 2 or self.time_s < 0:
            raise ValueError("inclination_or_time_domain")
        covariance = Covariance_Validate(self.covariance, 20)
        covariance.setflags(write=False)
        object.__setattr__(self, "covariance", covariance)


@dataclass(frozen=True)
class MagneticSample:
    corrected_sensor_uT: np.ndarray
    covariance_sensor_uT2: np.ndarray
    reference_strength_uT: float
    time_s: float
    frame: str
    calibration: str


@dataclass(frozen=True)
class Eskf20Step:
    result: NavigationEskf20Result
    state: Eskf20State
    nis: float | None = None
    magnetic_rank: int | None = None       # instantaneous H rank, not observability
    declination_sensitivity: float | None = None


def Magnetic_Field(inclination, declination):
    inclination, declination = Scalar_Validate(inclination), Scalar_Validate(declination)
    if abs(inclination) > np.pi / 2:
        raise ValueError("inclination_domain")
    si, ci, sd, cd = (np.sin(inclination), np.cos(inclination),
                      np.sin(declination), np.cos(declination))
    # The chart endpoints denote exact poles: D cannot affect the field there.
    # cos(pi/2)'s ~6e-17 residue can invent information when multiplied by P_D.
    # Do not snap nearby inclinations; their small D sensitivity is physical.
    if abs(inclination) == np.pi / 2:
        si, ci = np.sign(inclination), 0.
    field = np.array([sd * ci, cd * ci, -si])
    derivative_i = np.array([-sd * si, -cd * si, -ci])
    derivative_d = np.array([cd * ci, -sd * ci, 0.])
    return field, derivative_i, derivative_d


def Magnetic_Jacobian(state):
    """Exact angle derivatives, adapted right-local attitude; not book H verbatim."""
    field, derivative_i, derivative_d = Magnetic_Field(
        state.inclination, state.declination)
    matrix = np.zeros((3, 20))
    matrix[:, 6:9] = Vector_Skew(field) @ state.rotation
    matrix[:, 15:18] = -Vector_Skew(field) @ state.rotation
    matrix[:, 18], matrix[:, 19] = -derivative_i, -derivative_d
    return matrix


def Error_Inject(state, correction, covariance=None):
    """Public mathematical retraction; operational update also bounds rotations."""
    delta = Array_Validate(correction, (20,))
    return replace(state, position=state.position + delta[:3],
                   velocity=state.velocity + delta[3:6],
                   rotation=state.rotation @ expm(Vector_Skew(delta[6:9])),
                   gyro_bias=state.gyro_bias + delta[9:12],
                   accel_bias=state.accel_bias + delta[12:15],
                   installation=expm(-Vector_Skew(delta[15:18])) @ state.installation,
                   inclination=state.inclination - delta[18],
                   declination=state.declination - delta[19],
                   covariance=state.covariance if covariance is None else covariance)


def Error_ResetJacobian(correction):
    delta = Array_Validate(correction, (20,))
    matrix = np.eye(20)
    matrix[6:9, 6:9] = Matrix_IntegralExp(-Vector_Skew(delta[6:9]))
    matrix[15:18, 15:18] = Matrix_IntegralExp(-Vector_Skew(delta[15:18]))
    return matrix


def Dynamics_Matrix(rotation, angular_rate, specific_force):
    rotation = Rotation_Validate(rotation)
    matrix = np.zeros((20, 20))
    matrix[:3, 3:6] = np.eye(3)
    matrix[3:6, 6:9] = -rotation @ Vector_Skew(specific_force)
    matrix[3:6, 12:15] = -rotation
    matrix[6:9, 6:9] = -Vector_Skew(angular_rate)
    matrix[6:9, 9:12] = -np.eye(3)
    return matrix


def Noise_Matrix(rotation):
    matrix = np.zeros((20, 12))
    matrix[3:6, :3] = Rotation_Validate(rotation)
    matrix[6:9, 3:6] = -np.eye(3)
    matrix[9:12, 6:9] = matrix[12:15, 9:12] = np.eye(3)
    return matrix


def Covariance_Discretize(rotation, angular_rate, specific_force, density, dt):
    """Integrate time-varying F/Q along the exact held-input nominal rotation."""
    rotation = Rotation_Validate(rotation)
    omega = Array_Validate(angular_rate, (3,))
    force = Array_Validate(specific_force, (3,))
    density = Array_Validate(density, (12,))
    dt = Scalar_Validate(dt)
    if np.any(density < 0) or not 0 < dt <= .02:
        raise ValueError("noise_or_dt_domain")
    spectral = np.diag(density * density)

    def Derivative(time, packed):
        current = rotation @ expm(Vector_Skew(omega * time))
        matrix = Dynamics_Matrix(current, omega, force)
        noise = Noise_Matrix(current)
        transition, covariance = packed[:400].reshape(20, 20), packed[400:].reshape(20, 20)
        return np.r_[(matrix @ transition).ravel(),
                     (matrix @ covariance + covariance @ matrix.T +
                      noise @ spectral @ noise.T).ravel()]

    solution = solve_ivp(Derivative, (0., dt), np.r_[np.eye(20).ravel(), np.zeros(400)],
                         method="DOP853", rtol=2e-11, atol=2e-13)
    if not solution.success or not np.isfinite(solution.y[:, -1]).all():
        raise ArithmeticError("covariance_integration_failed")
    transition = solution.y[:400, -1].reshape(20, 20)
    covariance = solution.y[400:, -1].reshape(20, 20)
    return transition, .5 * (covariance + covariance.T)


def Nominal_Propagate(state, angular_rate_measured, specific_force_measured, gravity, dt):
    dt = Scalar_Validate(dt)
    group = np.eye(5)
    group[:3, :3], group[:3, 3], group[:3, 4] = state.rotation, state.velocity, state.position
    result = Navigation_PropagateGroup(group,
        Array_Validate(angular_rate_measured, (3,)) - state.gyro_bias,
        Array_Validate(specific_force_measured, (3,)) - state.accel_bias, gravity, dt)
    return replace(state, rotation=result[:3, :3], velocity=result[:3, 3],
                   position=result[:3, 4], time_s=state.time_s + dt)


def Eskf20_Predict(state, angular_rate_measured, specific_force_measured, gravity, density, dt):
    try:
        checked = replace(state)
        omega_m = Array_Validate(angular_rate_measured, (3,))
        force_m = Array_Validate(specific_force_measured, (3,))
        gravity = Array_Validate(gravity, (3,))
        density = Array_Validate(density, (12,))
        dt = Scalar_Validate(dt)
        if (np.any(density < 0) or not 0 < dt <= .02 or
                not np.isfinite(checked.time_s + dt) or checked.time_s + dt <= checked.time_s):
            raise ValueError("noise_or_time_domain")
    except (ValueError, TypeError, AttributeError):
        return Eskf20Step(NavigationEskf20Result.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            propagated = Nominal_Propagate(checked, omega_m, force_m, gravity, dt)
            transition, noise = Covariance_Discretize(checked.rotation,
                omega_m - checked.gyro_bias, force_m - checked.accel_bias, density, dt)
            covariance = transition @ checked.covariance @ transition.T + noise
            result = replace(propagated, covariance=.5 * (covariance + covariance.T))
        return Eskf20Step(NavigationEskf20Result.OK, result)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return Eskf20Step(NavigationEskf20Result.NUMERIC_ERROR, state)


def Update_Apply(state, residual, matrix, measurement_covariance, gate):
    """Internal update: called only after validating observations and gate."""
    innovation = matrix @ state.covariance @ matrix.T + measurement_covariance
    factor = np.linalg.cholesky(.5 * (innovation + innovation.T))
    whitened = np.linalg.solve(factor, residual)
    nis = float(whitened @ whitened)
    if not np.isfinite(nis):
        raise ArithmeticError("nonfinite_nis")
    if gate is not None and nis > gate:
        return Eskf20Step(NavigationEskf20Result.REJECTED_NIS, state, nis)
    right = matrix @ state.covariance
    gain = np.linalg.solve(factor.T, np.linalg.solve(factor, right)).T
    correction = gain @ residual
    if (np.linalg.norm(correction[6:9]) > .35 or np.linalg.norm(correction[15:18]) > .35 or
            abs(state.inclination - correction[18]) > np.pi / 2):
        return Eskf20Step(NavigationEskf20Result.REJECTED_CORRECTION, state, nis)
    contraction = np.eye(20) - gain @ matrix
    posterior = (contraction @ state.covariance @ contraction.T +
                 gain @ measurement_covariance @ gain.T)
    reset = Error_ResetJacobian(correction)
    covariance = reset @ posterior @ reset.T
    updated = Error_Inject(state, correction, .5 * (covariance + covariance.T))
    return Eskf20Step(NavigationEskf20Result.OK, updated, nis)


def Gate_Validate(gate):
    if gate is not None:
        gate = Scalar_Validate(gate)
        if gate <= 0:
            raise ValueError("invalid_nis_gate")
    return gate


def Eskf20_UpdateMagnetic(state, sample, gate=None):
    try:
        if type(state) is not Eskf20State:
            raise ValueError("wrong_state_type")
        checked, gate = replace(state), Gate_Validate(gate)
        if sample is None:
            return Eskf20Step(NavigationEskf20Result.NO_OBSERVATION, state)
        time_s = Scalar_Validate(sample.time_s)
        strength = Scalar_Validate(sample.reference_strength_uT)
        if (not isinstance(sample.frame, str) or sample.frame != "magnetometer_sensor" or
                not isinstance(sample.calibration, str) or sample.calibration != "hard_soft_iron_only" or
                time_s != checked.time_s or strength <= 0):
            raise ValueError("magnetic_boundary")
        measured = Array_Validate(sample.corrected_sensor_uT, (3,))
        covariance = Covariance_Validate(sample.covariance_sensor_uT2, 3)
        gate = Gate_Validate(gate)
    except (ValueError, TypeError, AttributeError):
        return Eskf20Step(NavigationEskf20Result.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            measured = measured / strength
            covariance = covariance / strength / strength
            transform = checked.rotation @ checked.installation
            field, _, derivative_d = Magnetic_Field(checked.inclination, checked.declination)
            residual = transform @ measured - field
            matrix = Magnetic_Jacobian(checked)
            step = Update_Apply(checked, residual, matrix,
                                transform @ covariance @ transform.T, gate)
        # Any rejected step retains the actual caller's original object.
        return replace(step, state=step.state if step.result is NavigationEskf20Result.OK else state,
                       magnetic_rank=int(np.linalg.matrix_rank(matrix)),
                       declination_sensitivity=float(np.linalg.norm(derivative_d)))
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return Eskf20Step(NavigationEskf20Result.NUMERIC_ERROR, state)


def Eskf20_UpdateVector(state, measured, covariance, kind, time_s, gate=None):
    """Synthetic co-timed position/velocity at the IMU origin; no device adapter."""
    try:
        checked = replace(state)
        measured = Array_Validate(measured, (3,))
        covariance = Covariance_Validate(covariance, 3)
        time_s = Scalar_Validate(time_s)
        if (not isinstance(kind, str) or kind not in ("position", "velocity") or
                time_s != checked.time_s):
            raise ValueError("observation_boundary")
        gate = Gate_Validate(gate)
    except (ValueError, TypeError, AttributeError):
        return Eskf20Step(NavigationEskf20Result.INVALID_INPUT, state)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            matrix = np.zeros((3, 20))
            offset = 0 if kind == "position" else 3
            matrix[:, offset:offset + 3] = np.eye(3)
            residual = measured - getattr(checked, kind)
            step = Update_Apply(checked, residual, matrix, covariance, gate)
        return replace(step, state=step.state if step.result is NavigationEskf20Result.OK else state)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError):
        return Eskf20Step(NavigationEskf20Result.NUMERIC_ERROR, state)
