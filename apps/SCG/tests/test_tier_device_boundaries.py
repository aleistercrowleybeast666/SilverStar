from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError


@pytest.mark.parametrize('tier', ['compact', 'minimal'])
def test_switch_import_and_service_keep_normalized_devices(builtin_catalog, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances.append(DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050'))
    FeatureTier_Apply(model, tier, builtin_catalog)
    expected = deepcopy(model.device_instances)
    assert model.DeviceInstance_Get('imu_extra') is None
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(loaded, builtin_catalog)
    assert [item for item in reconciled.model.device_instances if item.instance_id != 'maintenance0'] == [
        item for item in expected if item.instance_id != 'maintenance0']
    assert reconciled.edit_validation.valid
    SourceGraph_Resolve(reconciled.model, builtin_catalog)


def test_each_sensor_class_is_bounded_even_without_endpoint_descriptors(builtin_catalog):
    from silverstar_fccg.project.compact import CompactErrors_Get
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, feature_tier='compact')
    model.device_instances += [DeviceInstance('mag0', 'silverstar.device.magnetometer.mmc5983ma'),
                               DeviceInstance('mag1', 'silverstar.device.magnetometer.mmc5983ma')]
    assert any('magnetometer' in error for error in CompactErrors_Get(model, builtin_catalog))


def test_return_to_saved_bounded_tier_normalizes_new_full_devices(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    FeatureTier_Apply(model, 'full', builtin_catalog)
    extra = DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050')
    model.device_instances.append(extra)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    assert extra not in model.device_instances
    SourceGraph_Resolve(model, builtin_catalog)


@pytest.mark.parametrize('tier', ['compact', 'minimal'])
@pytest.mark.parametrize('plugin', [
    'silverstar.device.imu.mpu6050',
    'silverstar.device.gnss.neo_m9n',
    'silverstar.device.barometer.bmp280',
    'silverstar.device.magnetometer.mmc5983ma',
    'silverstar.device.sensor.input_voltage',
    'silverstar.device.telemetry.sx1281',
])
def test_every_sensor_and_radio_switch_normalizes_roundtrip(
        builtin_catalog, tier, plugin):
    from silverstar_fccg.project.compact import CompactErrors_Get
    model = ReferenceProject_Create(catalog=builtin_catalog)
    component_class = builtin_catalog.Component_Get(plugin).component_class
    model.device_instances = [item for item in model.device_instances
        if builtin_catalog.InstanceComponent_Get(item).component_class != component_class]
    model.device_instances.extend([DeviceInstance('review0', plugin), DeviceInstance('review1', plugin)])
    FeatureTier_Apply(model, tier, builtin_catalog)
    before = deepcopy(model.device_instances)
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(loaded, builtin_catalog)
    assert model.device_instances == before
    assert loaded.device_instances == before
    assert reconciled.model.DeviceInstance_Get('review1') is None
    allowed = component_class != 'magnetometer' and (tier != 'minimal' or component_class != 'gnss')
    assert (reconciled.model.DeviceInstance_Get('review0') is not None) == allowed
    if component_class == 'magnetometer':
        assert not reconciled.model.build.magnetometer_enabled
        assert not reconciled.model.build.maintenance_log_export_enabled
    assert not any('at most one' in error for error in CompactErrors_Get(reconciled.model, builtin_catalog))


@pytest.mark.parametrize('tier', ['full', 'standard', 'compact', 'minimal'])
def test_single_gnss_rule_is_shared_by_reconcile_and_graph(builtin_catalog, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    FeatureTier_Apply(model, tier, builtin_catalog)
    # Compact retains one; Minimal removes it at the explicit switch.
    assert sum(builtin_catalog.InstanceComponent_Get(item).component_class == 'gnss'
               for item in model.device_instances) == (0 if tier == 'minimal' else 1)
    reconciled = ProjectConfiguration_Reconcile(ProjectModel_Parse(model.Dictionary_Get()), builtin_catalog)
    assert reconciled.edit_validation.valid
    SourceGraph_Resolve(reconciled.model, builtin_catalog)
