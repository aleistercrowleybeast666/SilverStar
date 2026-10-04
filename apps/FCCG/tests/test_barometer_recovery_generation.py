"""Generator routing for standalone and IMU-companion pressure sources."""

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.render import (
    _DeviceDescriptorEntries_Get,
    _DeviceInstancesSource_Render,
    _FlightConfigHeader_Render,
)
from silverstar_fccg.project.model import DeviceInstance


def test_standalone_and_companion_barometer_routing(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("BarometerRecoveryRouting")
    jy_only = _FlightConfigHeader_Render(model, service.catalog)
    assert "#define SYSTEM_BUILD_BAROMETER_COLD_ENABLED              0U" in jy_only

    model.device_instances = [
        instance for instance in model.device_instances
        if instance.instance_id != "imu0"
    ]
    model.device_instances.append(DeviceInstance(
        "barometer0", "silverstar.device.barometer.bmp280",
        "spi", "forced_20_hz"))
    descriptors = [entry for entry in _DeviceDescriptorEntries_Get(model, service.catalog)
                   if entry["class"] == "SYSTEM_DEVICE_CLASS_BAROMETER"]
    assert len(descriptors) == 1
    single = _FlightConfigHeader_Render(model, service.catalog)
    assert "#define SYSTEM_BUILD_BAROMETER_COLD_ENABLED              1U" in single
    dispatch = _DeviceInstancesSource_Render(model, service.catalog.ProjectView_Get(model))
    assert "case 0U: return Bmp280SpiBarometerInstance_Init(0U);" in dispatch

    model.device_instances.insert(0, DeviceInstance("imu0", "silverstar.device.imu.jy901b"))
    descriptors = [entry for entry in _DeviceDescriptorEntries_Get(model, service.catalog)
                   if entry["class"] == "SYSTEM_DEVICE_CLASS_BAROMETER"]
    assert len(descriptors) == 2
    mixed = _FlightConfigHeader_Render(model, service.catalog)
    assert "#define SYSTEM_BUILD_BAROMETER_COLD_ENABLED              1U" in mixed
    dispatch = _DeviceInstancesSource_Render(model, service.catalog.ProjectView_Get(model))
    assert "Bmp280SpiBarometerInstance_Init(0U)" in dispatch
    assert "Jy901bBarometerInstance_Init(0U)" in dispatch


def test_gnss_recovery_busy_route_is_optional(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("GnssRecoveryBusyRouting")
    source = _DeviceInstancesSource_Render(model, service.catalog.ProjectView_Get(model))
    assert "NeoM9nGnssInstance_RecoveryBusyGet(0U, busy)" in source
    model.device_instances = [
        DeviceInstance("gnss0", "silverstar.device.gnss.generic_nmea")
        if instance.instance_id == "gnss0" else instance
        for instance in model.device_instances
    ]
    source = _DeviceInstancesSource_Render(model, service.catalog.ProjectView_Get(model))
    operation = source.split("ProjectGnssInstance_RecoveryBusyGet(", 1)[1].split(
        "ProjectGnssInstance_LatestSampleGet(", 1)[0]
    assert "case 0U: return SYSTEM_DEVICE_UNSUPPORTED;" in operation
