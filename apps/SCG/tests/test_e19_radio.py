"""E19-S2 uses internal DIO4; it must not inherit E32 external switch wiring."""
import re
import subprocess
from dataclasses import replace

import pytest
from silverstar_data_contracts.objects import MissionRadioProfile_Decode
from silverstar_fccg.generator.render import MissionRadioProfileMacros_Render
from silverstar_fccg.project.radio_transaction import RadioTransaction_EndpointSet
from silverstar_fccg.project.radio_variants import RadioManifest_Resolve
from silverstar_fccg.project.sx1278 import SX1278_PLUGIN
from test_sx1278_experimental import Sx1278Host_Build, Sx1278Model_Get


def test_e19_profile_owns_pins_and_recorded_identity(builtin_catalog):
    model = Sx1278Model_Get(builtin_catalog)
    identity = model.air_link.flight_radio_instance
    model.resource_assignments.update({identity+':radio_rx_en': 'old_rx', identity+':radio_tx_en': 'old_tx'})
    updated = RadioTransaction_EndpointSet(model, builtin_catalog, 'flight', SX1278_PLUGIN, 'e19_433m20s2', 17)
    assert model.DeviceInstance_Get(identity).module_variant == 'e32_400m20s'
    assert identity+':radio_rx_en' in model.resource_assignments
    assert identity+':radio_rx_en' not in updated.resource_assignments
    instance = updated.DeviceInstance_Get(identity)
    manifest = RadioManifest_Resolve(builtin_catalog.Component_Get(SX1278_PLUGIN), instance)
    requirements = {item.name: item for item in manifest.resource_requirements}
    assert not {'radio_rx_en', 'radio_tx_en'} & requirements.keys()
    assert requirements['radio_bus'].constraints['spi']['maximum_clock_hz'] == 1_000_000
    assert manifest.physical_device.model == 'E19-433M20S2'
    assert manifest.metadata['sx1278_module_profile']['module'] == 'e19_433m20s2'
    macros = MissionRadioProfileMacros_Render(updated)
    body = bytes(int(item, 16) for item in re.findall(r'0x([0-9A-F]{2})U', macros))
    profile = MissionRadioProfile_Decode(b'SSMS\x03\x00\x06\x00' + bytes(58) + body)
    assert profile['module'] == 'e19_433m20s2' and profile['hardware_verified'] is False
    model.ground_target = replace(model.ground_target, resource_assignments={
        'radio_rx_en':'old_rx', 'radio0:radio_tx_en':'old_tx', 'unrelated:status':'keep'})
    updated = RadioTransaction_EndpointSet(model, builtin_catalog, 'ground', SX1278_PLUGIN, 'e19_433m20s2', 17)
    assert updated.ground_target.resource_assignments == {'unrelated:status':'keep'}


@pytest.fixture(scope='module')
def e19_host(tmp_path_factory, builtin_catalog):
    return Sx1278Host_Build(tmp_path_factory, builtin_catalog, 'e19_433m20s2')


def Scenario_Run(e19_host, *args):
    executable, work, _, _ = e19_host
    result = subprocess.run([str(executable), *map(str, args)], capture_output=True, text=True, timeout=10, check=False)
    (work/('-'.join(map(str, args))+'.log')).write_text(result.stdout+result.stderr, encoding='utf8')
    assert result.returncode == (90 if str(args[0]).endswith('corrupt') else 0), result.stdout+result.stderr


@pytest.mark.parametrize('scenario', ['tx', 'rx', 'timeout', 'absent', 'readback', 'boundaries',
    'adapter', 'queue_corrupt', 'state_corrupt', 'queue_expiry', 'conflicting_irq', 'ground_adapter',
    'crc_race', 'deadline_during_spi', 'stop_restart', 'stop_during_config', 'stop_receive',
    'stop_gpio_error', 'stop_status_error', 'stop_during_tx_done', 'e19_dio4', 'e19_readback', 'e19_resources',
    'transmit_only', 'receive_only', 'mode_recovery', 'mode_stop_start', 'mode_during_tx', 'chip_bounds', 'identity'])
def test_e19_actual_owner_lifecycle_and_faults(e19_host, scenario):
    Scenario_Run(e19_host, scenario)


@pytest.mark.parametrize('scenario,count', [('init_spi_fault', 68), ('spi_fault', 20),
    ('tx_spi_fault', 15), ('rx_tx_spi_fault', 23)])
def test_e19_faults_cover_every_transaction_including_internal_switch(e19_host, scenario, count):
    for nth in range(1, count+1):
        args = (scenario, nth, 0) if scenario in ('spi_fault','tx_spi_fault') else (scenario,nth)
        Scenario_Run(e19_host, *args)
        if scenario in ('spi_fault','tx_spi_fault'):
            Scenario_Run(e19_host, scenario, nth, 1)


def test_e19_real_analyzer_and_arm_compilation(e19_host):
    from test_sx1278_experimental import (
        test_sx1278_actual_gcc_analyzer_and_arm_compilation,
    )
    test_sx1278_actual_gcc_analyzer_and_arm_compilation(e19_host)


def test_e19_generated_resources_and_spi_admission(builtin_catalog, tmp_path):
    from e19_project_fixture import E19Project_Create
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import (
        TargetGeneration_Apply,
        TargetScope,
    )
    from silverstar_fccg.project.air_link import GroundTargetIssues_Get
    from silverstar_fccg.project.validation import Project_Validate
    model = E19Project_Create(builtin_catalog, tmp_path/'input')
    validation = Project_Validate(model, builtin_catalog)
    assert validation.valid, validation.issues
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    output = tmp_path/'generated'
    TargetGeneration_Apply(model, builtin_catalog, WorkspacePolicy(tmp_path/'input'), output, TargetScope.ALL)
    for target in ('Flight_Controller','Ground_Station'):
        path = output/target
        header = next(path.rglob('air_link_config.h')).read_text(encoding='utf8')
        assert 'AIR_LINK_SX1278_DIO4_FRONTEND 1U' in header
        resources = next(path.rglob('project_resources.c')).read_text(encoding='utf8')
        assert '.rx_en = (PlatformGpioId)PLATFORM_GPIO_COUNT' in resources
        assert '.tx_en = (PlatformGpioId)PLATFORM_GPIO_COUNT' in resources
        spi = next((path/'HardwareGenerated').rglob('spi.c')).read_text(encoding='utf8')
        assert 'SPI_BAUDRATEPRESCALER_128' in spi
