"""Float64 reference ESKF: Hamilton q_nb, ENU, right multiplicative error.

The input is calibrated BODY specific force and angular rate; residual biases
belong to this filter. Coning/sculling is applied here exactly once. No recorded
attitude or navigation-frame increment enters prediction. Noise densities are
continuous standard deviations, and covariance is always a variance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np


class EskfUpdateResult(IntEnum):
    ACCEPTED = 0
    SOFT_WEIGHTED = 1
    REJECTED_NIS = 2
    REJECTED_INVALID = 3
    NUMERIC_ERROR = 4
    MODEL_MISMATCH = 5
    TIMING_INVALID = 17
    HISTORY_MISS = 18
    HISTORY_OVERFLOW = 19


def Vector_Skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.array(((0.0, -z, y), (z, 0.0, -x), (-y, x, 0.0)))


def Quaternion_Multiply(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    a, b = first[0], first[1:]
    c, d = second[0], second[1:]
    return np.r_[a * c - b @ d, a * d + c * b + np.cross(b, d)]


def Rotation_Exp(vector: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(vector))
    factor = 0.5 - angle * angle / 48 if angle < 1e-8 else np.sin(angle / 2) / angle
    return np.r_[np.cos(angle / 2), factor * vector]


def Quaternion_Matrix(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        (
            (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
        )
    )


def Rotation_RightJacobian(vector: np.ndarray) -> np.ndarray:
    """Exact derivative of Log(Exp(-a) Exp(a+da)) at da=0."""
    angle = float(np.linalg.norm(vector))
    skew = Vector_Skew(vector)
    if angle < 1e-5:
        return np.eye(3) - 0.5 * skew + skew @ skew / 6
    return (
        np.eye(3)
        - (1 - np.cos(angle)) / angle**2 * skew
        + (angle - np.sin(angle)) / angle**3 * skew @ skew
    )


@dataclass(frozen=True, slots=True)
class EskfNoise:
    gyro: float = 0.003
    accel: float = 0.08
    gyro_bias: float = 0.0001
    accel_bias: float = 0.001

    def __post_init__(self):
        if not all(
            np.isfinite(v) and v >= 0
            for v in (self.gyro, self.accel, self.gyro_bias, self.accel_bias)
        ):
            raise ValueError("eskf_noise_invalid")


@dataclass(slots=True)
class EskfState:
    p: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v: np.ndarray = field(default_factory=lambda: np.zeros(3))
    q: np.ndarray = field(default_factory=lambda: np.array((1.0, 0.0, 0.0, 0.0)))
    bg: np.ndarray = field(default_factory=lambda: np.zeros(3))
    ba: np.ndarray = field(default_factory=lambda: np.zeros(3))
    covariance: np.ndarray = field(
        default_factory=lambda: np.diag(
            [
                4.0,
                4.0,
                9.0,
                0.25,
                0.25,
                0.25,
                *([0.030461742] * 3),
                0.0001,
                0.0001,
                0.0001,
                0.01,
                0.01,
                0.01,
            ]
        )
    )

    def State_Clone(self) -> EskfState:
        return EskfState(
            *(getattr(self, n).copy() for n in ("p", "v", "q", "bg", "ba", "covariance"))
        )

    def State_Validate(self) -> None:
        for name, size in (("p", 3), ("v", 3), ("q", 4), ("bg", 3), ("ba", 3)):
            value = np.asarray(getattr(self, name), dtype=np.float64)
            if value.shape != (size,) or not np.isfinite(value).all():
                raise ValueError("eskf_state_invalid:" + name)
            setattr(self, name, value.copy())
        norm = np.linalg.norm(self.q)
        if norm < 1e-10:
            raise ValueError("eskf_quaternion_invalid")
        self.q /= norm
        self.covariance = np.asarray(self.covariance, dtype=np.float64).copy()
        Covariance_Validate(self.covariance)


def Covariance_Validate(covariance: np.ndarray) -> None:
    if (
        covariance.shape != (15, 15)
        or not np.isfinite(covariance).all()
        or not np.allclose(covariance, covariance.T, atol=1e-10, rtol=1e-10)
    ):
        raise ValueError("eskf_covariance_invalid")
    # Only floating point roundoff is tolerated. Do not repair a failed P.
    try:
        np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as exc:
        raise ValueError("eskf_covariance_not_positive_definite") from exc


@dataclass(frozen=True, slots=True)
class EskfMeasurementResult:
    result: EskfUpdateResult
    innovation: np.ndarray
    nis: float
    effective_r: np.ndarray
    gain_norm: float = 0.0


class Eskf15Filter:
    def __init__(
        self,
        state: EskfState | None = None,
        *,
        gravity: float = 9.78,
        noise: EskfNoise | None = None,
    ):
        if not np.isfinite(gravity) or not 1 <= gravity <= 20:
            raise ValueError("eskf_gravity_invalid")
        self.state = (state or EskfState()).State_Clone()
        self.state.State_Validate()
        self.gravity = gravity
        self.noise = noise or EskfNoise()
        self.last_omega = np.zeros(3)

    def Dynamics_Jacobian(
        self, omega: np.ndarray, force: np.ndarray, rotation: np.ndarray | None = None
    ) -> np.ndarray:
        rotation = Quaternion_Matrix(self.state.q) if rotation is None else rotation
        f = np.zeros((15, 15))
        f[:3, 3:6] = np.eye(3)
        f[3:6, 6:9] = -rotation @ Vector_Skew(force)
        f[3:6, 12:15] = -rotation
        f[6:9, 6:9] = -Vector_Skew(omega)
        f[6:9, 9:12] = -np.eye(3)
        return f

    def Prediction_Apply(
        self, gyro: np.ndarray, accel: np.ndarray, dt: float, *, process_noise_scale: float = 1.0
    ) -> None:
        """Constant sample special case of the two-subinterval body path."""
        self.Prediction_ApplyPair(
            gyro, accel, dt / 2, gyro, accel, dt / 2, process_noise_scale=process_noise_scale
        )

    def Prediction_ApplyPair(
        self,
        gyro1: np.ndarray,
        accel1: np.ndarray,
        dt1: float,
        gyro2: np.ndarray,
        accel2: np.ndarray,
        dt2: float,
        *,
        process_noise_scale: float = 1.0,
    ) -> None:
        values = np.asarray((gyro1, accel1, gyro2, accel2), dtype=np.float64)
        if (
            values.shape != (4, 3)
            or not np.isfinite(values).all()
            or not 0 < dt1 <= 0.02
            or not 0 < dt2 <= 0.02
            or dt1 + dt2 > 0.020000001
            or process_noise_scale not in (1.0, 4.0)
        ):
            raise ValueError("eskf_body_input_invalid")
        state = self.state
        w1, a1, w2, a2 = values
        w1, w2 = w1 - state.bg, w2 - state.bg
        a1, a2 = a1 - state.ba, a2 - state.ba
        t1, t2, u1, u2 = w1 * dt1, w2 * dt2, a1 * dt1, a2 * dt2
        theta = t1 + t2 + (2 / 3) * np.cross(t1, t2)
        dv = u1 + u2 + 0.5 * np.cross(t1 + t2, u1 + u2)
        dv += (2 / 3) * (np.cross(t1, u2) + np.cross(u1, t2))
        dt = dt1 + dt2
        rotation = Quaternion_Matrix(state.q)
        nav_dv = rotation @ dv - np.array((0.0, 0.0, self.gravity * dt))
        candidate = state.State_Clone()
        candidate.p += state.v * dt + 0.5 * nav_dv * dt
        candidate.v += nav_dv
        candidate.q = Quaternion_Multiply(state.q, Rotation_Exp(theta))
        candidate.q /= np.linalg.norm(candidate.q)
        omega, force = (t1 + t2) / dt, (u1 + u2) / dt
        f = self.Dynamics_Jacobian(omega, force, rotation)
        phi = np.eye(15) + f * dt + 0.5 * f @ f * dt**2
        g = np.zeros((15, 12))
        g[3:6, :3], g[6:9, 3:6] = rotation, -np.eye(3)
        g[9:12, 6:9], g[12:15, 9:12] = np.eye(3), np.eye(3)
        density = np.repeat(
            np.square(
                (self.noise.accel, self.noise.gyro, self.noise.gyro_bias, self.noise.accel_bias)
            ),
            3,
        )
        continuous = process_noise_scale * (g * density) @ g.T
        # Positive Simpson weights preserve PSD. Q uses the first-order noise
        # mapping; deterministic Phi separately retains its F² term.
        qd = np.zeros((15, 15))
        for node, weight in ((0.0, 1 / 6), (0.5, 4 / 6), (1.0, 1 / 6)):
            tau = dt * node
            transition = np.eye(15) + f * tau
            qd += weight * dt * transition @ continuous @ transition.T
        p = phi @ state.covariance @ phi.T + qd
        candidate.covariance = 0.5 * (p + p.T)
        Covariance_Validate(candidate.covariance)
        self.state = candidate
        # Retain calibrated raw angular rate. Each measurement subtracts the
        # current residual bias, including corrections from earlier groups.
        self.last_omega = (values[0] * dt1 + values[2] * dt2) / dt

    def Measurement_Model(
        self, kind: str, axes: tuple[int, ...], lever_arm: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray]:
        lever = np.zeros(3) if lever_arm is None else np.asarray(lever_arm, dtype=np.float64)
        if lever.shape != (3,) or not np.isfinite(lever).all() or not axes:
            raise ValueError("eskf_measurement_model_invalid")
        r = Quaternion_Matrix(self.state.q)
        h = np.zeros((3, 15))
        if kind == "position":
            prediction = self.state.p + r @ lever
            h[:, :3], h[:, 6:9] = np.eye(3), -r @ Vector_Skew(lever)
        elif kind == "velocity":
            turning = np.cross(self.last_omega - self.state.bg, lever)
            prediction = self.state.v + r @ turning
            h[:, 3:6], h[:, 6:9] = np.eye(3), -r @ Vector_Skew(turning)
            h[:, 9:12] = r @ Vector_Skew(lever)
        else:
            raise ValueError("eskf_measurement_kind_invalid")
        return prediction[list(axes)], h[list(axes)]

    def Measurement_Apply(
        self,
        kind: str,
        axes: tuple[int, ...],
        measurement: np.ndarray,
        variance: np.ndarray,
        *,
        physically_valid: bool = True,
        lever_arm: np.ndarray | None = None,
        soft: float = 9.21,
        hard: float = 25.0,
        max_scale: float = 16.0,
        max_injection_rad: float = 0.35,
    ) -> EskfMeasurementResult:
        z, variance = np.asarray(measurement), np.asarray(variance)
        invalid = EskfMeasurementResult(
            EskfUpdateResult.REJECTED_INVALID, np.full(len(axes), np.nan), np.nan, variance.copy()
        )
        if (
            not physically_valid
            or z.shape != (len(axes),)
            or variance.shape != z.shape
            or not np.isfinite(z).all()
            or not np.isfinite(variance).all()
            or np.any(variance <= 0)
        ):
            return invalid
        predicted, h = self.Measurement_Model(kind, axes, lever_arm)
        innovation = z - predicted
        p = self.state.covariance
        r = variance.copy()
        try:
            s = h @ p @ h.T + np.diag(r)
            chol = np.linalg.cholesky(s)
            whitened = np.linalg.solve(chol, innovation)
            nis = float(whitened @ whitened)
            if nis > hard:
                return EskfMeasurementResult(EskfUpdateResult.REJECTED_NIS, innovation, nis, r)
            result = EskfUpdateResult.ACCEPTED
            if nis > soft:
                r *= min(max_scale, nis / soft)
                result = EskfUpdateResult.SOFT_WEIGHTED
                s = h @ p @ h.T + np.diag(r)
                chol = np.linalg.cholesky(s)
            k = np.linalg.solve(chol.T, np.linalg.solve(chol, h @ p)).T
            delta = k @ innovation
            if np.linalg.norm(delta[6:9]) > max_injection_rad:
                return EskfMeasurementResult(EskfUpdateResult.MODEL_MISMATCH, innovation, nis, r)
            if float(np.linalg.norm(k)) <= 1e-12:
                return invalid
            residual = np.eye(15) - k @ h
            joseph = residual @ p @ residual.T + (k * r) @ k.T
            reset = np.eye(15)
            reset[6:9, 6:9] = Rotation_RightJacobian(delta[6:9])
            updated = reset @ joseph @ reset.T
            candidate = self.state.State_Clone()
            candidate.p += delta[:3]
            candidate.v += delta[3:6]
            candidate.q = Quaternion_Multiply(candidate.q, Rotation_Exp(delta[6:9]))
            candidate.q /= np.linalg.norm(candidate.q)
            candidate.bg += delta[9:12]
            candidate.ba += delta[12:15]
            if np.linalg.norm(candidate.bg) > 1.0 or np.linalg.norm(candidate.ba) > 5.0:
                return EskfMeasurementResult(EskfUpdateResult.MODEL_MISMATCH, innovation, nis, r)
            candidate.covariance = 0.5 * (updated + updated.T)
            Covariance_Validate(candidate.covariance)
            self.state = candidate
            return EskfMeasurementResult(result, innovation, nis, r, float(np.linalg.norm(k)))
        except (np.linalg.LinAlgError, ValueError):
            return EskfMeasurementResult(EskfUpdateResult.NUMERIC_ERROR, innovation, np.nan, r)
