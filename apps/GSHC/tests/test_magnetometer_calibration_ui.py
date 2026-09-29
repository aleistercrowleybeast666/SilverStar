from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from services.magnetometer_calibration import MagCalibrationFitStatus
from services.magnetometer_maintenance import MagMaintenanceSample
from ui.magnetometer_calibration_page import MagnetometerCalibrationPage


def _field(index: int, count: int) -> tuple[float, float, float]:
    z = 1.0 - 2.0 * (index + 0.5) / count
    azimuth = index * np.pi * (3.0 - np.sqrt(5.0))
    radius = np.sqrt(1.0 - z * z)
    return (12.0 + 50.0 * radius * np.cos(azimuth),
            -8.0 + 50.0 * radius * np.sin(azimuth),
            3.0 + 50.0 * z)


def test_page_collects_one_physical_instance_and_fits(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = MagnetometerCalibrationPage(I18n())
    commands: list[str] = []
    monkeypatch.setattr(page.session, "send", lambda command: commands.append(command) or True)
    page.start_collection()
    for index in range(600):
        page._on_sample(MagMaintenanceSample(0, 42, index, index * 50000, _field(index, 600)))
    page.stop_collection()
    assert commands == ["MAG 0 STREAM START", "MAG 0 STREAM STOP"]
    assert page.physical_device_id == 42
    assert len(page.samples) == 600
    assert page.fit_result is not None
    assert page.fit_result.status is MagCalibrationFitStatus.READY
    assert page.apply_button.isEnabled()
    page.apply_calibration()
    assert commands[-1].startswith("MAG 0 CAL APPLY ")
    assert not page.save_button.isEnabled()
    page._on_response("OK MAG 0 CAL action=APPLY accepted=1")
    assert page.save_button.isEnabled()
    page.save_calibration()
    assert commands[-1] == "MAG 0 CAL SAVE"
    page._on_response(
        "OK MAG 0 CAL state=APPLIED generation=7 "
        "physical_device_id=42 instance=0 saved=1 pending=0 failed=0"
    )
    assert page.saved_generation == 7
    assert not page._save_poll_timer.isActive()
    page.close_session()
    page.close()
    del app


def test_page_rejects_physical_device_change(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = MagnetometerCalibrationPage(I18n())
    monkeypatch.setattr(page.session, "send", lambda _command: True)
    page.start_collection()
    page._on_sample(MagMaintenanceSample(0, 42, 1, 50000, (20.0, 30.0, 40.0)))
    page._on_sample(MagMaintenanceSample(0, 43, 2, 100000, (20.0, 30.0, 40.0)))
    assert not page.collecting
    assert not page.fit_ready
    assert page.physical_device_id == 42
    page.close_session()
    page.close()
    del app


def test_page_reports_rejected_stored_calibration() -> None:
    app = QApplication.instance() or QApplication([])
    page = MagnetometerCalibrationPage(I18n())
    page._save_poll_timer.start()
    page._on_response(
        "OK MAG 0 CAL state=EMPTY generation=2 "
        "physical_device_id=0 instance=0 saved=0 pending=0 failed=0 "
        "load_error=WRONG_DEVICE"
    )
    assert not page._save_poll_timer.isActive()
    assert "WRONG_DEVICE" in page.status_text
    assert page.saved_generation is None
    page.close_session()
    page.close()
    del app
