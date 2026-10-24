"""Explicit magnetic recording metadata; no board or firmware project is created."""
from dataclasses import replace
import json

import pytest

from silverstar_fccg.generator.render import (
    LogDecoderProfile_Render,
    _DeviceDescriptorEntries_Get,
    _LogCapabilityEndpoints_Get,
    _LogPhysicalDevices_Get,
    _PhysicalDeviceDefinitions_Get,
)
from silverstar_fccg.project.logging import (
    LogAvailability_Get,
    LoggingProfile_AvailabilityTransitionApply,
    LoggingProfile_Reconcile,
    ProjectRecordableOutputs_Get,
)
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create

JY = "silverstar.device.imu.jy901b"
MAG = "FLIGHT_LOG_RECORD_MAG_NATIVE"


def _CaptureModel_Create(catalog, chip, interface):
    previous = ReferenceProject_Create("MagRecording", catalog=catalog)
    model = ReferenceProject_Create("MagRecording", catalog=catalog)
    if chip == "jy901b":
        model.device_instances = [replace(item, profile="jy901b_mag_capture")
                                  if item.plugin == JY else item
                                  for item in model.device_instances]
    else:
        profile = {"lis3mdl": "uhp_20_hz_4g", "mmc5983ma": "oneshot_20_hz_8g"}[chip]
        model.device_instances.append(DeviceInstance(
            "mag0", "silverstar.device.magnetometer." + chip, interface, profile))
    return previous, model


def test_default_mag_recording_remains_unavailable(builtin_catalog):
    model = ReferenceProject_Create("DefaultMagDisabled", catalog=builtin_catalog)
    definitions = LoggingProfile_Reconcile(model, builtin_catalog)
    definition = next(item for item in definitions if item.record == MAG)
    assert not LogAvailability_Get(definition, model, builtin_catalog).available
    assert not next(item for item in model.logging_streams if item.record == MAG).enabled
    assert "magnetometer.field" not in ProjectRecordableOutputs_Get(model, builtin_catalog)[0]


@pytest.mark.parametrize("chip,interface", [("jy901b", "uart"),
    ("lis3mdl", "i2c"), ("lis3mdl", "spi"),
    ("mmc5983ma", "i2c"), ("mmc5983ma", "spi")])
def test_explicit_capture_enables_recording_and_preserves_source_identity(
        builtin_catalog, chip, interface):
    previous, model = _CaptureModel_Create(builtin_catalog, chip, interface)
    definitions = LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    definition = next(item for item in definitions if item.record == MAG)
    assert LogAvailability_Get(definition, model, builtin_catalog).available
    assert next(item for item in model.logging_streams if item.record == MAG).enabled
    assert model.strategies == previous.strategies and model.alignment == previous.alignment

    view = builtin_catalog.ProjectView_Get(model)
    entries = _DeviceDescriptorEntries_Get(model, view)
    ids = dict(_PhysicalDeviceDefinitions_Get(view, entries))
    endpoints = [item for item in _LogCapabilityEndpoints_Get(view, entries, ids)
                 if item["device_class"] == "SYSTEM_DEVICE_CLASS_MAGNETOMETER"]
    assert len(endpoints) == 1
    endpoint = endpoints[0]
    if chip == "jy901b":
        assert endpoint["descriptor_id"] == 13  # Existing JY descriptor order is preserved.
    else:
        assert endpoint["descriptor_id"] != 13
    assert endpoint["instance_id"] == 0 and endpoint["physical_device_id"] > 0
    assert endpoint["physical_device_instance"] == ("imu0" if chip == "jy901b" else "mag0")
    assert "magnetometer.field" in endpoint["capabilities"]
    assert "magnetometer.absolute_vector_qualified" not in endpoint["capabilities"]
    devices = _LogPhysicalDevices_Get(model, view, entries, ids)
    source = next(item for item in devices
                  if endpoint["descriptor_id"] in item["descriptor_ids"])
    assert source["recordable_outputs"]["magnetometer.field"]["enabled"] is True

    # Once available, an explicit user stream disable survives reconciliation.
    model.logging_streams = [replace(item, enabled=False) if item.record == MAG else item
                             for item in model.logging_streams]
    LoggingProfile_Reconcile(model, builtin_catalog)
    assert not next(item for item in model.logging_streams if item.record == MAG).enabled


def test_multiple_magnetic_endpoints_keep_separate_package_identities(builtin_catalog):
    _, model = _CaptureModel_Create(builtin_catalog, "lis3mdl", "i2c")
    model.device_instances.append(DeviceInstance(
        "mag1", "silverstar.device.magnetometer.mmc5983ma", "spi", "oneshot_20_hz_8g"))
    view = builtin_catalog.ProjectView_Get(model)
    entries = _DeviceDescriptorEntries_Get(model, view)
    ids = dict(_PhysicalDeviceDefinitions_Get(view, entries))
    endpoints = [item for item in _LogCapabilityEndpoints_Get(view, entries, ids)
                 if item["device_class"] == "SYSTEM_DEVICE_CLASS_MAGNETOMETER"]
    assert len(endpoints) == 2
    assert {item["instance_id"] for item in endpoints} == {0, 1}
    assert len({item["descriptor_id"] for item in endpoints}) == 2
    assert len({item["physical_device_id"] for item in endpoints}) == 2
    assert {item["physical_device_instance"] for item in endpoints} == {"mag0", "mag1"}


def test_actual_decoder_package_exposes_enabled_jy_source_without_layout_change(builtin_catalog):
    previous, model = _CaptureModel_Create(builtin_catalog, "jy901b", "uart")
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    result = LogDecoderProfile_Render(model, builtin_catalog.ProjectView_Get(model))
    semantics = json.loads(result.project_semantics_content)
    view = next(item for item in semantics["record_views"] if item["record"] == MAG)
    assert view["logging"]["enabled"] is True
    assert view["partition_by"] == ["source_descriptor_id", "instance_id"]
    assert view["record_version"] == 0 and view["payload_size"] == 60
    endpoint = next(item for item in semantics["capability_endpoints"]
                    if item["device_class"] == "SYSTEM_DEVICE_CLASS_MAGNETOMETER")
    assert endpoint["descriptor_id"] == 13 and endpoint["physical_device_instance"] == "imu0"
