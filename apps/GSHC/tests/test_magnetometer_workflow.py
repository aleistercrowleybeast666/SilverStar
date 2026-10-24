import numpy as np
import pytest

from services.magnetometer_calibration import MagCalibrationFitStatus
from services.magnetometer_maintenance import MagMaintenanceSample
from services.magnetometer_workflow import (
    MagCalibrationDevice, MagDevices_Parse, MagSampleCollection, MagStatus_Parse,
)


DEVICE = MagCalibrationDevice(3, 42, "test")


def test_sparse_devices_keep_exact_physical_identity_and_reject_truncation():
    wire = "OK MAG LIST count=2 DATA instance=3 physical_device_id=42 device=external model=LIS3MDL DATA instance=8 physical_device_id=99 device=module model=JY901B"
    devices = MagDevices_Parse(wire)
    assert [(d.instance, d.physical_device_id) for d in devices] == [(3, 42), (8, 99)]
    with pytest.raises(ValueError, match="Incomplete"):
        MagDevices_Parse(wire.split(" DATA instance=8")[0])
    with pytest.raises(ValueError, match="duplicate"):
        MagDevices_Parse(wire.replace("instance=8", "instance=3"))


def test_status_empty_identity_remains_unknown_and_applied_identity_is_strict():
    base = "OK MAG 3 CAL state=EMPTY generation=0 physical_device_id=0 instance=0 saved=0 pending=0 failed=0 load_error=OK"
    status = MagStatus_Parse(base, DEVICE)
    assert status.physical_device_id == 0 and status.instance == 0
    active = base.replace("EMPTY", "APPLIED").replace("physical_device_id=0", "physical_device_id=42").replace("instance=0", "instance=3")
    assert MagStatus_Parse(active, DEVICE).physical_device_id == 42
    for invalid in (active.replace("42", "99"), active.replace("saved=0", "saved=2"), active + " generation=2"):
        with pytest.raises(ValueError):
            MagStatus_Parse(invalid, DEVICE)


def test_collection_rejects_mixed_identity_duplicate_and_reordered_samples_but_allows_wrap():
    collection = MagSampleCollection(DEVICE)
    sample = lambda seq, stamp, physical=42: MagMaintenanceSample(3, physical, seq, stamp, (1.0, 2.0, 3.0))
    assert collection.add(sample(0xFFFFFFFF, 0xFFFFFFF0))
    assert collection.add(sample(0, 10))
    assert not collection.add(sample(0, 10))
    assert not collection.add(sample(0xFFFFFFFF, 5))
    assert len(collection.points) == 2 and collection.discarded == 2
    with pytest.raises(ValueError, match="identity"):
        collection.add(sample(1, 20, 99))
    assert len(collection.points) == 2


def test_collection_bounds_storage_and_reuses_existing_solver_quality():
    collection = MagSampleCollection(DEVICE)
    for i in range(4100):
        collection.add(MagMaintenanceSample(3, 42, i, i + 1, (1., 2., 3.)))
    assert len(collection.points) == 4096 and collection.discarded == 4
    assert collection.fit(50).status is MagCalibrationFitStatus.DEGENERATE_GEOMETRY
    sphere = MagSampleCollection(DEVICE)
    for i in range(600):
        z = 1 - 2 * (i + .5) / 600
        a = i * np.pi * (3 - np.sqrt(5))
        radius = np.sqrt(1 - z * z)
        vector = (50 * radius * np.cos(a) + 12, 50 * radius * np.sin(a) - 8, 50 * z + 3)
        sphere.add(MagMaintenanceSample(3, 42, i, i + 1, vector))
    fit = sphere.fit(50)
    assert fit.status is MagCalibrationFitStatus.READY and min(fit.octant_counts) >= 4
    np.testing.assert_allclose(fit.hard_iron_uT, (12, -8, 3), atol=.01)
