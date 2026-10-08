from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve


@pytest.mark.parametrize('tier', ['compact', 'minimal'])
def test_explicit_switch_keeps_first_instance_and_clears_removed_bindings(builtin_catalog, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    first = model.DeviceInstance_Get('imu0')
    model.device_instances.append(replace(first, instance_id='imu_extra'))
    model.capability_source_overrides['imu.corrected'] = 'imu_extra'
    model.resource_assignments['imu_extra:sample_input'] = 'PLATFORM_UART_1'
    FeatureTier_Apply(model, tier, builtin_catalog)
    assert model.DeviceInstance_Get('imu0') == first
    assert model.DeviceInstance_Get('imu_extra') is None
    assert 'imu_extra' not in model.capability_source_overrides.values()
    assert not any(key.startswith('imu_extra:') for key in model.resource_assignments)
    assert sum(builtin_catalog.InstanceComponent_Get(item).component_class == 'gnss'
               for item in model.device_instances) == (0 if tier == 'minimal' else 1)
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(loaded, builtin_catalog)
    assert reconciled.edit_validation.valid
    SourceGraph_Resolve(reconciled.model, builtin_catalog)
    active = deepcopy(reconciled.model.device_instances)
    FeatureTier_Apply(reconciled.model, 'full', builtin_catalog)
    assert reconciled.model.device_instances == active
    assert reconciled.model.DeviceInstance_Get('imu_extra') is None


@pytest.mark.parametrize('plugin', [
    'silverstar.device.imu.mpu6050', 'silverstar.device.gnss.neo_m9n',
    'silverstar.device.barometer.bmp280', 'silverstar.device.magnetometer.mmc5983ma',
    'silverstar.device.sensor.input_voltage', 'silverstar.device.telemetry.sx1281',
])
@pytest.mark.parametrize('tier', ['compact', 'minimal'])
def test_explicit_switch_bounds_each_sensor_class_in_list_order(builtin_catalog, plugin, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    kind = builtin_catalog.Component_Get(plugin).component_class
    model.device_instances = [item for item in model.device_instances
                             if builtin_catalog.InstanceComponent_Get(item).component_class != kind]
    first = DeviceInstance('first', plugin)
    model.device_instances += [first, DeviceInstance('later', plugin)]
    FeatureTier_Apply(model, tier, builtin_catalog)
    assert model.DeviceInstance_Get('later') is None
    assert model.DeviceInstance_Get('first') == (None if tier == 'minimal' and kind == 'gnss' else first)


def test_switch_does_not_hide_unrelated_invalid_source_binding(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.capability_source_overrides['imu.corrected'] = 'missing_imu'
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    assert model.capability_source_overrides['imu.corrected'] == 'missing_imu'
    assert not ProjectConfiguration_Reconcile(model, builtin_catalog).edit_validation.valid
