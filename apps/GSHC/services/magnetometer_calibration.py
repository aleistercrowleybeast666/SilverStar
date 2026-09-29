"""Bounded PC-side hard/soft iron fit for one physical magnetometer instance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

MAG_CALIBRATION_MAX_SAMPLES = 4096
MAG_CALIBRATION_MIN_SAMPLES = 128
MAG_CALIBRATION_MIN_OCTANT_SAMPLES = 4
MAG_CALIBRATION_MAX_AXIS_CONDITION = 25.0
MAG_CALIBRATION_MAX_RELATIVE_RMS = 0.15
MAG_CALIBRATION_MAX_RELATIVE_RESIDUAL = 0.50


class MagCalibrationFitStatus(Enum):
    READY = auto()
    INVALID_INPUT = auto()
    INSUFFICIENT_SAMPLES = auto()
    DEGENERATE_GEOMETRY = auto()
    INSUFFICIENT_COVERAGE = auto()
    EXCESSIVE_RESIDUAL = auto()


@dataclass(frozen=True)
class MagCalibrationFitResult:
    status: MagCalibrationFitStatus
    sample_count: int
    octant_counts: tuple[int, ...] = ()
    hard_iron_uT: tuple[float, float, float] | None = None
    soft_iron: tuple[tuple[float, float, float], ...] | None = None
    reference_field_uT: float | None = None
    rms_residual_uT: float | None = None
    max_residual_uT: float | None = None
    axis_condition: float | None = None


def MagCalibration_Fit(
    raw_field_uT: np.ndarray,
    reference_field_uT: float,
) -> MagCalibrationFitResult:
    """Fit an ellipsoid and check 3D coverage before accepting its correction."""
    try:
        points = np.asarray(raw_field_uT, dtype=np.float64)
        reference = float(reference_field_uT)
    except (TypeError, ValueError, OverflowError):
        return MagCalibrationFitResult(MagCalibrationFitStatus.INVALID_INPUT, 0)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or points.shape[0] > MAG_CALIBRATION_MAX_SAMPLES
        or not np.isfinite(points).all()
        or not np.isfinite(reference)
        or not 10.0 <= reference <= 100.0
    ):
        return MagCalibrationFitResult(
            MagCalibrationFitStatus.INVALID_INPUT,
            int(points.shape[0]) if points.ndim > 0 else 0,
        )
    count = int(points.shape[0])
    if count < MAG_CALIBRATION_MIN_SAMPLES:
        return MagCalibrationFitResult(MagCalibrationFitStatus.INSUFFICIENT_SAMPLES, count)

    origin = points.mean(axis=0)
    scale = float(np.max(points.std(axis=0)))
    if not np.isfinite(scale) or scale <= 1e-9:
        return MagCalibrationFitResult(MagCalibrationFitStatus.DEGENERATE_GEOMETRY, count)
    xyz = (points - origin) / scale
    x, y, z = xyz.T
    design = np.column_stack(
        (x * x, y * y, z * z, 2.0 * x * y, 2.0 * x * z, 2.0 * y * z, x, y, z)
    )
    try:
        coefficients, _, rank, _ = np.linalg.lstsq(design, np.ones(count), rcond=None)
        if rank != 9:
            raise np.linalg.LinAlgError("ellipsoid fit is rank deficient")
        quadratic = np.array(
            (
                (coefficients[0], coefficients[3], coefficients[4]),
                (coefficients[3], coefficients[1], coefficients[5]),
                (coefficients[4], coefficients[5], coefficients[2]),
            )
        )
        center = -0.5 * np.linalg.solve(quadratic, coefficients[6:9])
        radius_squared = 1.0 + float(center @ quadratic @ center)
        if radius_squared <= 0.0:
            raise np.linalg.LinAlgError("ellipsoid radius is invalid")
        eigenvalues, eigenvectors = np.linalg.eigh(quadratic / radius_squared)
        if eigenvalues[0] <= 0.0:
            raise np.linalg.LinAlgError("ellipsoid is not positive definite")
    except np.linalg.LinAlgError:
        return MagCalibrationFitResult(MagCalibrationFitStatus.DEGENERATE_GEOMETRY, count)

    axis_condition = float(np.sqrt(eigenvalues[-1] / eigenvalues[0]))
    if axis_condition > MAG_CALIBRATION_MAX_AXIS_CONDITION:
        return MagCalibrationFitResult(
            MagCalibrationFitStatus.DEGENERATE_GEOMETRY,
            count,
            axis_condition=axis_condition,
        )
    hard_iron = origin + scale * center
    soft_iron = (
        reference / scale
        * (eigenvectors * np.sqrt(eigenvalues)) @ eigenvectors.T
    )
    calibrated = (points - hard_iron) @ soft_iron.T
    magnitudes = np.linalg.norm(calibrated, axis=1)
    if not np.isfinite(calibrated).all() or np.any(magnitudes <= 0.0):
        return MagCalibrationFitResult(MagCalibrationFitStatus.DEGENERATE_GEOMETRY, count)
    octants = (
        (calibrated[:, 0] >= 0.0).astype(np.intp) * 4
        + (calibrated[:, 1] >= 0.0).astype(np.intp) * 2
        + (calibrated[:, 2] >= 0.0).astype(np.intp)
    )
    octant_counts = tuple(int(value) for value in np.bincount(octants, minlength=8))
    residual = magnitudes - reference
    rms = float(np.sqrt(np.mean(residual * residual)))
    maximum = float(np.max(np.abs(residual)))
    status = MagCalibrationFitStatus.READY
    if min(octant_counts) < MAG_CALIBRATION_MIN_OCTANT_SAMPLES:
        status = MagCalibrationFitStatus.INSUFFICIENT_COVERAGE
    elif (
        rms > reference * MAG_CALIBRATION_MAX_RELATIVE_RMS
        or maximum > reference * MAG_CALIBRATION_MAX_RELATIVE_RESIDUAL
    ):
        status = MagCalibrationFitStatus.EXCESSIVE_RESIDUAL
    return MagCalibrationFitResult(
        status=status,
        sample_count=count,
        octant_counts=octant_counts,
        hard_iron_uT=tuple(float(value) for value in hard_iron),
        soft_iron=tuple(tuple(float(value) for value in row) for row in soft_iron),
        reference_field_uT=reference,
        rms_residual_uT=rms,
        max_residual_uT=maximum,
        axis_condition=axis_condition,
    )


def MagCalibration_Apply(
    raw_field_uT: np.ndarray,
    result: MagCalibrationFitResult,
) -> np.ndarray:
    if (
        result.status is not MagCalibrationFitStatus.READY
        or result.hard_iron_uT is None
        or result.soft_iron is None
    ):
        raise ValueError("A ready magnetometer calibration is required")
    points = np.asarray(raw_field_uT, dtype=np.float64)
    if points.ndim < 1 or points.shape[-1] != 3 or not np.isfinite(points).all():
        raise ValueError("Magnetometer vectors must be finite XYZ samples")
    return (points - np.asarray(result.hard_iron_uT)) @ np.asarray(result.soft_iron).T
