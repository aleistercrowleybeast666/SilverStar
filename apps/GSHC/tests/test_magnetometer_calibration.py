from __future__ import annotations

import numpy as np

from services.magnetometer_calibration import (
    MAG_CALIBRATION_MAX_SAMPLES,
    MagCalibration_Apply,
    MagCalibration_Fit,
    MagCalibrationFitStatus,
)


def _sphere_points(count: int = 600) -> np.ndarray:
    index = np.arange(count, dtype=np.float64)
    z = 1.0 - 2.0 * (index + 0.5) / count
    azimuth = index * np.pi * (3.0 - np.sqrt(5.0))
    radius = np.sqrt(1.0 - z * z)
    return np.column_stack((radius * np.cos(azimuth), radius * np.sin(azimuth), z))


def test_full_sphere_fit_removes_hard_and_soft_iron() -> None:
    reference = 48.0
    field = reference * _sphere_points()
    distortion = np.array(
        ((1.20, 0.12, 0.03), (0.12, 0.82, -0.05), (0.03, -0.05, 1.09))
    )
    offset = np.array((12.0, -19.0, 6.5))
    raw = field @ distortion.T + offset
    result = MagCalibration_Fit(raw, reference)
    assert result.status is MagCalibrationFitStatus.READY
    assert result.sample_count == 600
    assert min(result.octant_counts) > 4
    assert result.hard_iron_uT is not None
    np.testing.assert_allclose(result.hard_iron_uT, offset, atol=0.12)
    corrected = MagCalibration_Apply(raw, result)
    np.testing.assert_allclose(np.linalg.norm(corrected, axis=1), reference, atol=0.12)
    assert result.rms_residual_uT is not None
    assert result.rms_residual_uT < 0.1


def test_partial_coverage_is_rejected_even_if_ellipsoid_fits() -> None:
    sphere = _sphere_points(1200)
    hemisphere = sphere[sphere[:, 2] > 0.0] * 50.0
    result = MagCalibration_Fit(hemisphere, 50.0)
    assert result.status is MagCalibrationFitStatus.INSUFFICIENT_COVERAGE


def test_degenerate_and_invalid_collections_are_rejected() -> None:
    assert MagCalibration_Fit(np.zeros((200, 3)), 50.0).status is (
        MagCalibrationFitStatus.DEGENERATE_GEOMETRY
    )
    assert MagCalibration_Fit(_sphere_points(50), 50.0).status is (
        MagCalibrationFitStatus.INSUFFICIENT_SAMPLES
    )
    assert MagCalibration_Fit(np.zeros((MAG_CALIBRATION_MAX_SAMPLES + 1, 3)), 50.0).status is (
        MagCalibrationFitStatus.INVALID_INPUT
    )
    invalid = np.zeros((200, 3))
    invalid[5, 0] = np.nan
    assert MagCalibration_Fit(invalid, 50.0).status is MagCalibrationFitStatus.INVALID_INPUT
    assert MagCalibration_Fit(_sphere_points(), -1.0).status is (
        MagCalibrationFitStatus.INVALID_INPUT
    )
