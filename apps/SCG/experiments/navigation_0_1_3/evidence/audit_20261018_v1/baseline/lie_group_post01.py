"""Independent float64 SE_2(3) reference; no firmware/plugin entry point.

Coordinates are [phi(3), nu(3), rho(3)], with X = [R v p; 0 1 0; 0 0 1].
See README.md for conventions, derivations, provenance and numerical domains.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import expm
from scipy.spatial.transform import Rotation


def Array_Validate(value, shape):
    try:
        raw = np.asarray(value)
        if np.iscomplexobj(raw):
            raise ValueError("complex_input")
        with np.errstate(over="raise", invalid="raise"):
            array = np.array(raw, dtype=np.float64, copy=True)
    except (TypeError, OverflowError, FloatingPointError) as error:
        raise ValueError("not_representable_float64") from error
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError("shape_or_nonfinite")
    return array


def Scalar_Validate(value):
    """A finite real numeric scalar, copied into an immutable Python float."""
    raw = np.asarray(value)
    if raw.shape != () or raw.dtype.kind not in "iuf":
        raise ValueError("not_real_numeric_scalar")
    return float(Array_Validate(raw, ()))


def Vector_Skew(value):
    x, y, z = Array_Validate(value, (3,))
    return np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])


def Group_Validate(value):
    group = Array_Validate(value, (5, 5))
    rotation = group[:3, :3]
    if (not np.array_equal(group[3:], np.eye(5)[3:]) or
            not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10, rtol=0) or
            not np.isclose(np.linalg.det(rotation), 1., atol=1e-10, rtol=0)):
        raise ValueError("not_se23")
    return group


def Group_Inverse(value):
    group = Group_Validate(value)
    inverse = np.eye(5)
    inverse[:3, :3] = group[:3, :3].T
    inverse[:3, 3:] = -group[:3, :3].T @ group[:3, 3:]
    return inverse


def Lie_Hat(value):
    vector = Array_Validate(value, (9,))
    matrix = np.zeros((5, 5))
    matrix[:3, :3] = Vector_Skew(vector[:3])
    matrix[:3, 3] = vector[3:6]
    matrix[:3, 4] = vector[6:9]
    return matrix


def Lie_Exp(value):
    vector = Array_Validate(value, (9,))
    skew = Vector_Skew(vector[:3])
    # Assemble the known block structure instead of asking a dense 5x5 expm
    # to reproduce its constant bottom rows bit-for-bit. Input validation stays
    # strict; this is the SE_2(3) exponential formula, not projection/repair.
    group = np.eye(5)
    group[:3, :3] = expm(skew)
    jacobian = Matrix_IntegralExp(skew)
    group[:3, 3] = jacobian @ vector[3:6]
    group[:3, 4] = jacobian @ vector[6:9]
    return Group_Validate(group)


def Matrix_IntegralExp(matrix):
    """Integral_0^1 exp(s M) ds, without inversion of possibly singular M."""
    raw = np.asarray(matrix)
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1] or raw.shape[0] not in (3, 9):
        raise ValueError("unsupported_integral_dimension")
    matrix = Array_Validate(matrix, raw.shape)
    size = matrix.shape[0]
    block = np.zeros((2 * size, 2 * size))
    block[:size, :size] = matrix
    block[:size, size:] = np.eye(size)
    return expm(block)[:size, size:]


def Lie_Log(value):
    group = Group_Validate(value)
    phi = Rotation.from_matrix(group[:3, :3]).as_rotvec()
    # Principal chart only; never silently pick a branch at the pi cut.
    if np.linalg.norm(phi) >= np.pi - 1e-7:
        raise ValueError("rotation_log_cut_locus")
    jacobian = Matrix_IntegralExp(Vector_Skew(phi))
    vectors = np.linalg.solve(jacobian, group[:3, 3:])
    return np.r_[phi, vectors[:, 0], vectors[:, 1]]


def Lie_Adjoint(value):
    group = Group_Validate(value)
    rotation = group[:3, :3]
    adjoint = np.kron(np.eye(3), rotation)
    adjoint[3:6, :3] = Vector_Skew(group[:3, 3]) @ rotation
    adjoint[6:9, :3] = Vector_Skew(group[:3, 4]) @ rotation
    return adjoint


def Lie_AlgebraAdjoint(value):
    vector = Array_Validate(value, (9,))
    adjoint = np.kron(np.eye(3), Vector_Skew(vector[:3]))
    adjoint[3:6, :3] = Vector_Skew(vector[3:6])
    adjoint[6:9, :3] = Vector_Skew(vector[6:9])
    return adjoint


def Lie_LeftJacobian(value):
    return Matrix_IntegralExp(Lie_AlgebraAdjoint(value))


def Covariance_Validate(value, size):
    covariance = Array_Validate(value, (size, size))
    if not np.allclose(covariance, covariance.T, atol=0, rtol=1e-12):
        raise ValueError("asymmetric_covariance")
    # Average floating-point roundoff only; no eigenvalue clipping or jitter.
    covariance = 0.5 * covariance + 0.5 * covariance.T
    try:
        np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as error:
        raise ValueError("non_positive_covariance") from error
    return covariance
