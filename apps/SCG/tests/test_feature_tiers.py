from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.model import BuildOptions, DeviceInstance, ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply, FeatureTier_StrategyAllowed, FeatureTier_DescriptorActive
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _DeviceDescriptorEntries_Get, _MetadataSource_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError

PREFIX = 'silverstar.algorithm.estimator.'


@pytest.mark.parametrize('tier,allowed', [('full', ('sf6', 'kf6', 'eskf15')), ('standard', ('sf6', 'kf6')),
                                       ('compact', ('sf6',)), ('minimal', ('sf6',))])
def test_tier_algorithm_matrix_and_pure_ins(builtin_catalog, tier, allowed):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, feature_tier=tier)
    assert FeatureTier_StrategyAllowed(model, None)
    for algorithm in ('sf6', 'kf6', 'eskf15'):
        assert FeatureTier_StrategyAllowed(model, PREFIX + algorithm) == (algorithm in allowed)


def test_legacy_roundtrip_and_single_authority(builtin_catalog):
    original = ReferenceProject_Create(catalog=builtin_catalog).Dictionary_Get()
    assert ProjectModel_Parse(original).Dictionary_Get() == original
    legacy = deepcopy(original)
    legacy['build']['compact_mode'] = True
    loaded = ProjectModel_Parse(legacy)
    assert loaded.build.feature_tier == 'compact'
    assert loaded.strategies == original['components']['strategies']
    assert loaded.algorithm_parameters == ProjectModel_Parse(original).algorithm_parameters
    result = ProjectConfiguration_Reconcile(loaded, builtin_catalog)
    assert result.model.strategies['estimator'] == loaded.strategies['estimator']
    canonical = loaded.Dictionary_Get()
    assert canonical['format_version'] == 17
    assert 'compact_mode' not in canonical['build']
    assert ProjectModel_Parse(canonical).Dictionary_Get() == canonical
    canonical['build']['compact_mode'] = True
    with pytest.raises(ProjectModelError, match='authoritative'):
        ProjectModel_Parse(canonical)


def test_switch_preserves_algorithms_parameters_devices_and_current_mcu(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = PREFIX + 'eskf15'
    model.device_instances.append(DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050'))
    initial_parameters = deepcopy(model.algorithm_parameters)
    original_devices = deepcopy(model.device_instances)
    FeatureTier_Apply(model, 'standard', builtin_catalog)
    assert model.strategies['estimator'] == PREFIX + 'kf6'
    notes = FeatureTier_Apply(model, 'compact', builtin_catalog)
    assert any(note.startswith('suspended:') for note in notes)
    assert model.strategies['estimator'] == PREFIX + 'sf6'
    assert len(model.device_instances) < len(original_devices)
    model.mcu = 'silverstar.mcu.stm32f103rft6'
    FeatureTier_Apply(model, 'full', builtin_catalog)
    assert model.strategies['estimator'] == PREFIX + 'eskf15'
    assert model.algorithm_parameters == initial_parameters
    assert model.device_instances == original_devices
    assert model.mcu == 'silverstar.mcu.stm32f103rft6'
    assert ProjectModel_Parse(model.Dictionary_Get()).Dictionary_Get() == model.Dictionary_Get()


def test_compact_keeps_gnss_maintenance_and_reviewed_log_geometry(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    original_protocols = deepcopy(model.protocols)
    original_devices = deepcopy(model.device_instances)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    assert model.protocols == original_protocols
    assert model.device_instances == original_devices
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    import re
    assert re.search(r'SYSTEM_LOG_RECORD_QUEUE_DEPTH\s+56U', header)
    assert re.search(r'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH\s+16U', header)
    assert 'SYSTEM_LOG_RECORD_SLOT_SIZE' not in header
    assert 'SYSTEM_LOG_ESTIMATOR_SLOT_SIZE' not in header
    assert 'SYSTEM_LOG_AGGREGATION_BUFFER_SIZE' not in header
    assert len(model.logging_streams) == 40
    descriptors = _DeviceDescriptorEntries_Get(model, builtin_catalog)
    algorithm_count = sum(len(builtin_catalog.Component_Get(component).metadata.get(
        'algorithm_descriptors', [])) for component in model.ComponentIds_Get())
    # The independent snapshot must retain records beyond ordinary queue depth.
    assert 1 + len(descriptors) + algorithm_count + len(model.logging_streams) > 56
    profile_source = _MetadataSource_Render(model, builtin_catalog)
    assert 'SSLOG_RECORD_COUNT + 4U + PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) <= 65535U' in profile_source
    assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH' not in profile_source
    assert model.build.logging_profile == 'all_streams'
    assert 'AIR_LINK_HAL_BUFFER_SIZE=260' in SourceGraph_Resolve(model, builtin_catalog).defines
    for tier in ('standard', 'full'):
        FeatureTier_Apply(model, tier, builtin_catalog)
        restored = _FlightConfigHeader_Render(model, builtin_catalog)
        assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH' not in restored
        assert 'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH' not in restored


def test_minimal_changes_are_reversible_and_keep_pure_ins(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = None
    original = deepcopy(model.device_instances)
    protocols = deepcopy(model.protocols)
    FeatureTier_Apply(model, 'minimal', builtin_catalog)
    assert model.strategies['estimator'] is None
    assert model.protocols['maintenance'] is None
    assert model.protocols['logging'] is not None
    assert all(item.plugin != 'silverstar.device.gnss.neo_m9n' for item in model.device_instances)
    assert model.build.logging_profile == 'sf6_minimal'
    assert 'SYSTEM_LOG_RECORD_SLOT_SIZE' in _FlightConfigHeader_Render(model, builtin_catalog)
    FeatureTier_Apply(model, 'full', builtin_catalog)
    assert model.device_instances == original
    assert model.protocols == protocols


@pytest.mark.parametrize('estimator', (None, PREFIX + 'sf6'))
def test_minimal_owned_snapshot_keeps_all_descriptors_with_small_queues(builtin_catalog, estimator):
    import re
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = estimator
    FeatureTier_Apply(model, 'minimal', builtin_catalog)
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    assert re.search(r'SYSTEM_LOG_RECORD_QUEUE_DEPTH\s+24U', header)
    assert re.search(r'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH\s+16U', header)
    snapshot = int(re.search(r'PROJECT_SYSTEM_CONFIG_SNAPSHOT_SLOTS\s+(\d+)U', header)[1])
    assert snapshot > 24
    assert len(model.logging_streams) == 40
    assert re.search(r'SYSTEM_IMU_SAMPLE_BUS_DEPTH\s+16U', header)
    assert re.search(r'ESTIMATOR_BUS_DEPTH\s+16U', header)
    FeatureTier_Apply(model, 'full', builtin_catalog)
    restored = _FlightConfigHeader_Render(model, builtin_catalog)
    assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH' not in restored
    assert 'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH' not in restored


def test_malformed_compact_algorithm_blocks_generation(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, feature_tier='compact')
    assert model.strategies['estimator'] == PREFIX + 'kf6'
    with pytest.raises(SourceGraphError, match='prohibited'):
        SourceGraph_Resolve(model, builtin_catalog)


def test_compact_power_contract_matches_selected_implementation(builtin_catalog):
    import re
    model = ReferenceProject_Create(catalog=builtin_catalog)
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    model.device_instances = [item for item in model.device_instances if not any(
        entry.get('class') == 'SYSTEM_DEVICE_CLASS_POWER'
        for entry in builtin_catalog.InstanceComponent_Get(item).metadata.get('device_descriptors', ()))]
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    assert re.search(r'SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE\s+0U', header)
    assert re.search(r'SYSTEM_USER_POWER_ENABLE\s+0U', header)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert 'System/Src/system_power.c' not in graph.sources
    model.build = replace(model.build, feature_tier='full')
    assert 'SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE' not in _FlightConfigHeader_Render(model, builtin_catalog)


def test_preset_recursion_rejected(builtin_catalog):
    data = ReferenceProject_Create(catalog=builtin_catalog).Dictionary_Get()
    data['feature_tier_presets'] = {'full': deepcopy(data)}
    data['feature_tier_presets']['full']['feature_tier_presets'] = {}
    with pytest.raises(ProjectModelError, match='nonrecursive'):
        ProjectModel_Parse(data)


def test_dedicated_barometer_precedes_embedded_endpoint_without_hiding_imu(builtin_catalog):
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances = [DeviceInstance('imu0', 'silverstar.device.imu.jy901b'),
                              DeviceInstance('barometer0', 'silverstar.device.barometer.bmp280')]
    full_entries = _DeviceDescriptorEntries_Get(model, builtin_catalog)
    assert sum(entry['class'] == 'SYSTEM_DEVICE_CLASS_BAROMETER' for entry in full_entries) == 2
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    entries = _DeviceDescriptorEntries_Get(model, builtin_catalog)
    barometers = [entry for entry in entries if entry['class'] == 'SYSTEM_DEVICE_CLASS_BAROMETER']
    assert len(barometers) == 1 and barometers[0]['_source_instance_id'] == 'barometer0'
    assert any(entry['class'] == 'SYSTEM_DEVICE_CLASS_IMU' for entry in entries)
    assert not any(entry['class'] == 'SYSTEM_DEVICE_CLASS_MAGNETOMETER' for entry in entries)
    resolution = CapabilityResolution_Resolve(model, builtin_catalog)
    assert all(route.provider.instance_id == 'barometer0' for route in resolution.routes
               if route.requirement.capability.startswith('barometer.'))


def test_dedicated_priority_reconciles_retained_embedded_source_override(builtin_catalog, monkeypatch):
    from silverstar_fccg.project.capabilities import CapabilitySourceOverrides_Reconcile
    # Exercise a declarative multifunction provider that advertises altitude.
    # Current JY901B has the endpoint descriptor but does not advertise this
    # capability; it cannot alone exercise a competing-provider override.
    original = builtin_catalog.InstanceComponent_Get
    def instance_manifest(instance):
        manifest = original(instance)
        if instance.plugin == 'silverstar.device.imu.jy901b':
            return replace(manifest, provides=(*manifest.provides, 'barometer.altitude'))
        return manifest
    monkeypatch.setattr(builtin_catalog, 'InstanceComponent_Get', instance_manifest)
    monkeypatch.setattr(builtin_catalog, 'ProjectView_Get', lambda model: builtin_catalog)
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances = [DeviceInstance('barometer0', 'silverstar.device.barometer.bmp280'),
                              DeviceInstance('imu0', 'silverstar.device.imu.jy901b')]
    model.capability_source_overrides['barometer.altitude'] = 'imu0'
    assert 'barometer.altitude' in instance_manifest(model.device_instances[1]).provides
    FeatureTier_Apply(model, 'compact', builtin_catalog)
    resolution = CapabilitySourceOverrides_Reconcile(model, builtin_catalog)
    assert 'barometer.altitude' not in resolution.invalid_overrides
    assert 'barometer.altitude' not in model.capability_source_overrides
    assert not any(capability.startswith('barometer.') for capability in
                   resolution.EnabledCapabilitiesForInstance_Get('imu0'))


def test_first_page_control_and_log_states(qapp):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.core.view_models import LoggingStreamView
    from silverstar_fccg.ui.pages.components import DevicesPage, FlightConfigurationPage
    from silverstar_fccg.ui.widgets import StandardCheckBox, LockedCheckBox
    page = DevicesPage(Translator('zh_CN'))
    assert [page.feature_tier_combo.itemData(i) for i in range(4)] == ['full', 'standard', 'compact', 'minimal']
    assert [page.feature_tier_combo.itemText(i) for i in range(4)] == ['完整', '标准', '轻量', '最简']
    logs = FlightConfigurationPage(Translator('en_US'))
    logs.Streams_Set([LoggingStreamView('same', 'Selected', True, 'replay', editable=False)])
    check = logs.logging_table.cellWidget(0, 0).findChild(StandardCheckBox)
    assert check.isChecked() and not check.isEnabled()
    logs.Streams_Set([LoggingStreamView('same', 'Required', True, 'replay', required=True)])
    check = logs.logging_table.cellWidget(0, 0).findChild(StandardCheckBox)
    assert isinstance(check, LockedCheckBox) and check.isChecked() and check.isEnabled()
    logs.Streams_Set([LoggingStreamView('same', 'Unavailable', False, 'replay', required=True, available=False)])
    check = logs.logging_table.cellWidget(0, 0).findChild(StandardCheckBox)
    assert isinstance(check, LockedCheckBox) and not check.isChecked() and not check.isEnabled()
