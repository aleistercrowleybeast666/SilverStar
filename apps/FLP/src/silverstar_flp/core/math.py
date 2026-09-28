from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float32]


def Quaternion_Normalize(quaternion: NDArray[np.floating]) -> FloatArray:
    q = np.asarray(quaternion, dtype=np.float32).copy()
    if q.shape != (4,):
        raise ValueError("quaternion_shape_invalid")
    norm = np.float32(np.sqrt(np.sum(q * q, dtype=np.float32)))
    if not np.isfinite(norm) or norm < np.float32(1.0e-6):
        raise ValueError("quaternion_norm_invalid")
    return np.asarray(q / norm, dtype=np.float32)


def Quaternion_Multiply(left: NDArray[np.floating], right: NDArray[np.floating]) -> FloatArray:
    lhs = np.asarray(left, dtype=np.float32)
    rhs = np.asarray(right, dtype=np.float32)
    if lhs.shape != (4,) or rhs.shape != (4,):
        raise ValueError("quaternion_shape_invalid")
    result = np.empty(4, dtype=np.float32)
    result[0] = lhs[0] * rhs[0] - lhs[1] * rhs[1] - lhs[2] * rhs[2] - lhs[3] * rhs[3]
    result[1] = lhs[0] * rhs[1] + lhs[1] * rhs[0] + lhs[2] * rhs[3] - lhs[3] * rhs[2]
    result[2] = lhs[0] * rhs[2] - lhs[1] * rhs[3] + lhs[2] * rhs[0] + lhs[3] * rhs[1]
    result[3] = lhs[0] * rhs[3] + lhs[1] * rhs[2] - lhs[2] * rhs[1] + lhs[3] * rhs[0]
    return result


def Quaternion_Conjugate(quaternion: NDArray[np.floating]) -> FloatArray:
    q = np.asarray(quaternion, dtype=np.float32)
    if q.shape != (4,):
        raise ValueError("quaternion_shape_invalid")
    return np.asarray((q[0], -q[1], -q[2], -q[3]), dtype=np.float32)


def Quaternion_RotateVector(
    quaternion_nb: NDArray[np.floating], vector_b: NDArray[np.floating]
) -> FloatArray:
    q = Quaternion_Normalize(quaternion_nb)
    vector = np.asarray(vector_b, dtype=np.float32)
    if vector.shape != (3,):
        raise ValueError("vector_shape_invalid")
    vector_q = np.asarray((0.0, vector[0], vector[1], vector[2]), dtype=np.float32)
    rotated = Quaternion_Multiply(Quaternion_Multiply(q, vector_q), Quaternion_Conjugate(q))
    return rotated[1:4].copy()


def Quaternion_FromRotationVector(delta_theta_b: NDArray[np.floating]) -> FloatArray:
    delta = np.asarray(delta_theta_b, dtype=np.float32)
    if delta.shape != (3,):
        raise ValueError("rotation_vector_shape_invalid")
    angle_sq = np.sum(delta * delta, dtype=np.float32)
    if not np.isfinite(angle_sq):
        raise ValueError("rotation_vector_invalid")
    result = np.empty(4, dtype=np.float32)
    if angle_sq <= np.float32(1.0e-6):
        result[0] = np.float32(1.0) - angle_sq / np.float32(8.0)
        scale = np.float32(0.5) - angle_sq / np.float32(48.0)
    else:
        angle = np.float32(np.sqrt(angle_sq))
        result[0] = np.float32(np.cos(np.float32(0.5) * angle))
        scale = np.float32(np.sin(np.float32(0.5) * angle) / angle)
    result[1:4] = scale * delta
    return Quaternion_Normalize(result)


def Quaternion_PropagateBodyIncrement(
    quaternion_nb_start: NDArray[np.floating], delta_theta_b: NDArray[np.floating]
) -> FloatArray:
    start = Quaternion_Normalize(quaternion_nb_start)
    propagated = Quaternion_Normalize(
        Quaternion_Multiply(start, Quaternion_FromRotationVector(delta_theta_b))
    )
    if np.dot(start, propagated) < np.float32(0.0):
        propagated = -propagated
    return np.asarray(propagated, dtype=np.float32)


def Quaternion_ToEulerEnuDeg(quaternion_nb: NDArray[np.floating]) -> FloatArray:
    q = Quaternion_Normalize(quaternion_nb).astype(np.float64)
    w, x, y, z = q
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_argument = 2.0 * (w * y - z * x)
    pitch = math.asin(max(-1.0, min(1.0, pitch_argument)))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return np.asarray(np.degrees((roll, pitch, yaw)), dtype=np.float32)


def Quaternion_GeodesicErrorDeg(first: NDArray[np.floating], second: NDArray[np.floating]) -> float:
    a = Quaternion_Normalize(first).astype(np.float64)
    b = Quaternion_Normalize(second).astype(np.float64)
    dot = float(np.clip(abs(np.dot(a, b)), 0.0, 1.0))
    return math.degrees(2.0 * math.acos(dot))
