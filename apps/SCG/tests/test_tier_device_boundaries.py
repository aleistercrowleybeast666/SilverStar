from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError


@pytest.mark.parametrize('tier', ['compact', 'minimal'])
def test_switch_import_and_service_preserve_invalid_devices_and_block_generation(builtin_catalog, tier):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances.append(DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050'))
    original = deepcopy(model.device_instances)
    FeatureTier_Apply(model, tier, builtin_catalog)
    assert model.device_instances == original, 'Tier switch must not remove user devices'
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(loaded, builtin_catalog)
    # Maintenance is an auto-managed transport for the deliberately disabled
    # Minimal protocol; every user sensor/radio remains visible for review.
    assert [item for item in reconciled.model.device_instances if item.instance_id != 'maintenance0'] == [
        item for item in original if item.instance_id != 'maintenance0']
    assert not reconciled.edit_validation.valid
    with pytest.raises(SourceGraphError, match='at most one|GNSS'):
        SourceGraph_Resolve(reconciled.model, builtin_catalog)


def test_each_sensor_class_is_bounded_even_without_endpoint_descriptors(builtin_catalog):
    from silverstar_fccg.project.compact import CompactErrors_Get
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, feature_tier='compact')
    model.device_instances += [DeviceInstance('mag0', 'silverstar.device.magnetometer.mmc5983ma'),
                               DeviceInstance('mag1', 'silverstar.device.magnetometer.mmc5983ma')]
    assert any('magnetometer' in error for error in CompactErrors_Get(model, builtin_catalog))


def test_return_to_saved_tier_does_not_hide_new_full_devices(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    FeatureTier_Apply(model, 'full', builtin_catalog)
    extra = DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050')
    model.device_instances.append(extra)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    assert extra in model.device_instances
    with pytest.raises(SourceGraphError, match='at most one'):
        SourceGraph_Resolve(model, builtin_catalog)
