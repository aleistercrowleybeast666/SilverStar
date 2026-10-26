"""H743 candidate admission, separate from hardware or flight qualification."""
from dataclasses import replace

import pytest

from silverstar_fccg.hardware.inventory import _FatFsInventory_Get
from silverstar_fccg.hardware.platform import DetectedMcuFacts, PlatformMatch_Resolve
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfileUnsupportedError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.generator.render import _DeviceBuildCapabilitiesHeader_Render, _FlightConfigHeader_Render


def test_h743_candidate_is_exact_and_clock_memory_contracts_are_distinct(builtin_catalog):
    facts = DetectedMcuFacts(vendor='STM32', part='STM32H743ZIT6', family='STM32H7',
                            package='LQFP144', core='Cortex-M7', provider='stm32_cubemx')
    match = PlatformMatch_Resolve(facts, builtin_catalog)
    assert match.selected.component_id == 'silverstar.mcu.stm32h743zit6'
    mcu = builtin_catalog.Component_Get(match.selected.component_id)
    assert mcu.metadata['max_hclk_hz'] == 240000000
    assert mcu.metadata['cpu_max_clock_hz'] == 480000000
    regions = {row['name']: row for row in mcu.metadata['memory_regions']}
    assert regions['FLASH']['bytes'] == 2097152
    assert regions['RAM'] == {'name': 'RAM', 'origin': 0x24000000, 'bytes': 524288}
    assert regions['DTCMRAM']['origin'] == 0x20000000
    assert not builtin_catalog.Component_Get(mcu.metadata['platform_family_id']).metadata['reference']['hardware_tested']
    with pytest.raises(ValueError):
        PlatformMatch_Resolve(replace(facts, part='STM32H743ZGT6'), builtin_catalog)


def test_required_raw_sensor_support_is_not_restricted_to_compact_tier(builtin_catalog):
    model = ReferenceProject_Create('RawStandard', catalog=builtin_catalog)
    model.device_instances[0] = replace(model.device_instances[0], plugin='silverstar.device.imu.bmi088')
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert not model.build.compact_mode
    assert 'silverstar.sensor.register_bus' in model.base_components
    assert not any(issue.code == 'component_type' and 'register_bus' in issue.message
                   for issue in Project_Validate(model, builtin_catalog).issues)
    model.base_components.append('silverstar.core.ground.0_1_0')
    assert any(issue.code == 'component_type' and 'core.ground' in issue.message
               for issue in Project_Validate(model, builtin_catalog).issues)


@pytest.mark.parametrize('instance,peripherals,valid', [
    ('SDMMC1', ('FATFS','SDMMC1'), True),
    ('SDMMC2', ('FATFS','SDMMC1'), False),
    ('SDMMC1', ('FATFS','SDIO','SDMMC1'), False)])
def test_sdmmc_fatfs_matches_one_actual_controller(instance, peripherals, valid):
    files = {
        'FATFS/App/fatfs.c': 'FATFS SDFatFS; char SDPath[4]; void Init(void) { FATFS_LinkDriver(&SD_Driver, SDPath); }',
        'FATFS/App/fatfs.h': 'extern FATFS SDFatFS; extern char SDPath[4];',
        'Core/Src/sdmmc.c': 'SD_HandleTypeDef hsd1; void Init(void) { hsd1.Instance = '+instance+'; }',
        'FATFS/Target/sd_diskio.c': 'const Diskio_drvTypeDef SD_Driver = {0};',
    }
    result = _FatFsInventory_Get({}, peripherals, files)
    assert result.enabled
    assert (not result.errors) is valid
    assert result.sd_instance == instance


def test_augmented_noise_contract_and_absent_power_follow_actual_selection(builtin_catalog):
    model = ReferenceProject_Create('AugmentedNoPower', catalog=builtin_catalog)
    model.strategies['estimator'] = 'silverstar.algorithm.estimator.eskf20'
    model.device_instances = [row for row in model.device_instances if row.instance_id != 'voltage_monitor0']
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    capabilities = _DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog)
    assert '#define SYSTEM_BUILD_ESTIMATOR_NOISE_CONTRACT_ENABLED 0U' in capabilities
    assert '#define SYSTEM_USER_POWER_ENABLE' in _FlightConfigHeader_Render(model, builtin_catalog)
    assert '#define SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE' in _FlightConfigHeader_Render(model, builtin_catalog)


def test_custom_hardware_without_board_identity_refuses_optional_mission_snapshot(builtin_catalog):
    model = ReferenceProject_Create('CustomBoardIdentity', catalog=builtin_catalog)
    model.board = ''
    with pytest.raises(MissionProfileUnsupportedError, match='without_board_identity'):
        MissionProfile_Build(model, builtin_catalog)


def test_h743_eide_uses_real_cpu_fpu_and_explicit_make_source_set(builtin_catalog):
    import yaml
    from silverstar_fccg.generator.render import _Eide_Render
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve

    model = ReferenceProject_Create('EditorCpuContract', catalog=builtin_catalog)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    h7 = builtin_catalog.Component_Get('silverstar.mcu.stm32h743zit6')
    graph = replace(graph, mcu_flags=h7.build.mcu_flags, linker_script=h7.build.linker_script)
    model.mcu_family = 'silverstar.mcu_family.stm32h7'
    model.build = replace(model.build, target_profile='SilverStar_H743ZI')
    environment = builtin_catalog.Component_Get('silverstar.environment.vscode_eide_gcc')
    document = yaml.safe_load(_Eide_Render(model, graph, environment))
    assert document['srcDirs'] == []
    assert {item['path'] for item in document['virtualFolder']['files']} == set(graph.sources + graph.asm_sources)
    for target in document['targets'].values():
        config = target['toolchainConfigMap']['GCC']
        assert config['cpuType'] == 'Cortex-M7'
        assert config['floatingPointHardware'] == 'double'
        assert config['options']['global']['$float-abi-type'] == 'hard'
        assert '-mfpu=fpv5-d16' in config['options']['global']['misc-control']
    with pytest.raises(ValueError, match='explicit supported Cortex-M CPU'):
        _Eide_Render(model, replace(graph, mcu_flags=()), environment)
