from __future__ import annotations

from services.magnetometer_calibration import (
    MagCalibrationFitResult,
    MagCalibrationFitStatus,
)
from services.magnetometer_maintenance import (
    MAG_CALIBRATION_PACKET,
    MAG_MAINTENANCE_MAX_LINE_BYTES,
    MagMaintenance_CalibrationCommandBuild,
    MagMaintenance_CalibrationPacketBuild,
    MagMaintenance_ParseSample,
    MagMaintenanceDecoder,
)

SAMPLE = (
    b"EVENT MAG SAMPLE instance=0 physical_device_id=42 seq=17 "
    b"sample_us=123456 x_uT=25.5000 y_uT=-18.2500 z_uT=42.0000"
)


def test_split_maintenance_sample_and_reject_duplicate_field() -> None:
    decoder = MagMaintenanceDecoder()
    assert decoder.feed(SAMPLE[:31]) == []
    samples = decoder.feed(SAMPLE[31:] + b"\r\n")
    assert len(samples) == 1
    assert samples[0].physical_device_id == 42
    assert samples[0].field_uT == (25.5, -18.25, 42.0)
    assert MagMaintenance_ParseSample(SAMPLE + b" seq=18") is None


def test_oversize_nonfinite_and_non_ascii_are_rejected() -> None:
    decoder = MagMaintenanceDecoder()
    assert decoder.feed(b"A" * (MAG_MAINTENANCE_MAX_LINE_BYTES + 10) + b"\n") == []
    assert decoder.discarded_lines == 1
    assert MagMaintenance_ParseSample(SAMPLE.replace(b"25.5000", b"nan")) is None
    assert MagMaintenance_ParseSample(SAMPLE + b"\xff") is None
    assert decoder.feed(SAMPLE + b"\n")[0].sequence == 17


def test_maintenance_stream_ignores_unrelated_gsp_or_console_lines() -> None:
    decoder = MagMaintenanceDecoder()
    samples, responses = decoder.feed_records(
        b"OK MAG 0 STREAM state=STARTED rate_hz=20\n"
    )
    assert samples == []
    assert responses == ["OK MAG 0 STREAM state=STARTED rate_hz=20"]
    assert decoder.feed(b"\xa5\x5a\x00\n") == []
    assert decoder.feed(SAMPLE + b"\n")[0].instance == 0


def test_calibration_object_fits_one_bounded_maintenance_line() -> None:
    fit = MagCalibrationFitResult(
        status=MagCalibrationFitStatus.READY,
        sample_count=600,
        octant_counts=(75,) * 8,
        hard_iron_uT=(12.0, -8.0, 3.0),
        soft_iron=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        reference_field_uT=50.0,
        rms_residual_uT=0.2,
        max_residual_uT=0.8,
        axis_condition=1.2,
    )
    packet = MagMaintenance_CalibrationPacketBuild(0, 42, fit)
    assert len(packet) == MAG_CALIBRATION_PACKET.size + 4 == 84
    assert packet[:6] == bytes((1, 1, 42, 0, 0, 0))
    command = MagMaintenance_CalibrationCommandBuild(0, 42, fit)
    assert command.startswith("MAG 0 CAL APPLY 01012A000000")
    assert len(command) <= MAG_MAINTENANCE_MAX_LINE_BYTES - 2
