"""Projection geometry and dialog lifecycle using synthetic samples only."""
import numpy as np
from PySide6.QtCore import QSettings

from services.i18n import I18n, Language
from services.magnetometer_calibration import MagCalibration_Fit, MagCalibrationFitStatus
from ui.magnetometer_preview import MagProjectionPreview
from test_magnetometer_dialog import gui, fitted_dialog, wait_for


def test_projection_preview_uses_fit_coordinates_without_mutating_samples(qtbot, tmp_path):
    angles = np.arange(512) * np.pi * (3 - np.sqrt(5))
    z = 1 - 2 * (np.arange(512) + .5) / 512
    radius = np.sqrt(1 - z * z)
    sphere = np.column_stack((radius * np.cos(angles), radius * np.sin(angles), z)) * 50
    raw = sphere @ np.diag([1.3, .8, 1.1]) + [14, -8, 5]
    original = raw.copy()
    fit = MagCalibration_Fit(raw, 50)
    assert fit.status is MagCalibrationFitStatus.READY
    i18n = I18n(QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    preview = MagProjectionPreview(i18n)
    assert 'x_s' in preview.accessibleName() and 'XY' not in preview.accessibleName()
    qtbot.addWidget(preview)
    preview.resize(720, 220)
    preview.show()
    preview.set_samples(raw.tolist(), fit, 50)
    qtbot.waitUntil(lambda: len(preview.snapshot.corrected) == 512)
    corrected = np.asarray(preview.snapshot.corrected)
    np.testing.assert_allclose(np.linalg.norm(corrected, axis=1), 50, atol=1e-8)
    np.testing.assert_array_equal(raw, original)
    assert preview.snapshot.total == 512
    assert preview.snapshot.axis_limit > np.max(np.abs(raw))
    assert all(plane in preview.accessibleName() for plane in ('x_s y_s','x_s z_s','y_s z_s'))
    assert '非设备回读' in preview.toolTip()
    assert not preview.grab().isNull()
    i18n.set_language(Language.EN_US)
    preview.retranslate()
    assert 'not device readback' in preview.toolTip()


def test_preview_bounds_display_and_clears_stale_fit(qtbot, tmp_path):
    i18n = I18n(QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    preview = MagProjectionPreview(i18n)
    qtbot.addWidget(preview)
    points = [(float(n % 7), float(n % 11), float(n % 13)) for n in range(4096)]
    preview.set_samples(points, None, 50)
    qtbot.waitUntil(lambda: preview.snapshot.total == 4096)
    assert len(preview.snapshot.raw) <= 1024
    assert len(points) == 4096
    assert preview.snapshot.corrected == ()
    preview.set_samples([], None, 50)
    assert preview.snapshot.total == 0 and preview.snapshot.raw == ()
    preview.set_samples([(1, 2, float('nan'))], None, 50)
    qtbot.waitUntil(lambda: bool(preview.snapshot.error))
    assert preview.snapshot.raw == () and preview.snapshot.corrected == ()


def test_dialog_preview_tracks_fit_reset_and_keeps_controls_reachable(gui):
    dialog = fitted_dialog(gui)
    wait_for(lambda: len(dialog.preview.snapshot.corrected) == 256)
    assert dialog.applied_generation is None and not dialog.save_device.isEnabled()
    assert dialog.width() <= 700
    dialog.resize(540, 480)
    gui[0].processEvents()
    assert dialog.body_scroll.verticalScrollBar().maximum() > 0
    assert dialog.stop_fit.isVisible() and dialog.cancel_button.isVisible()
    assert dialog.cancel_button.geometry().bottom() <= dialog.height()
    dialog.start.click()
    wait_for(lambda: dialog.collecting)
    assert dialog.fit_result is None
    wait_for(lambda: dialog.preview.snapshot.corrected == ())
