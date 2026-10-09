from dataclasses import replace
import json
from pathlib import Path

import pytest
import yaml

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import HardwareConfiguration, ProjectModel_Parse
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.main_window import MainWindow


@pytest.fixture
def private_user_ground_descriptor(tmp_path):
    source = Path('D:/stm32_project/SS_0_5_TEST_6/SilverStar.ssproject')
    if not source.is_file():
        pytest.skip('User Ground descriptor is unavailable on this machine')
    data = source.read_bytes()
    descriptor = tmp_path / 'descriptor_copy' / 'SilverStar.ssproject'
    descriptor.parent.mkdir()
    descriptor.write_bytes(data)
    yield descriptor
    assert source.read_bytes() == data


def test_saved_board_without_resources_recovers_declarative_defaults(builtin_catalog):
    model = ReferenceProject_Create('Recovery', catalog=builtin_catalog)
    model.ground_target = replace(model.ground_target, enabled=True,
        board='silverstar.board.ground_station_0_5',
        mcu='silverstar.mcu.stm32f103c8t6',
        radio_plugin='silverstar.device.telemetry.sx1281', module_variant='e28_2g4m12sx',
        pc_interface='uart', hardware=HardwareConfiguration(mode='board_plugin'))
    result = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert result.ground_target.hardware.resources
    assert result.ground_target.hardware.source_kind == 'verified_builtin'
    assert result.ground_target.hardware.cubemx_version == '6.15.0'
    assert result.ground_target.hardware.firmware_package == 'STM32Cube FW_F1 V1.8.7'
    assert result.ground_target.pc_resource == 'PLATFORM_UART_1'
    assert result.ground_target.resource_assignments['radio0:radio_nss'] == 'PLATFORM_GPIO_0'
    assert not GroundTargetIssues_Get(result, builtin_catalog)
    reopened = ProjectModel_Parse(result.Dictionary_Get())
    assert reopened.ground_target == result.ground_target
    # User-selected wrong resources still fail; defaults do not erase evidence.
    reopened.ground_target = replace(reopened.ground_target, pc_resource='MISSING')
    reopened = ProjectConfiguration_Reconcile(reopened, builtin_catalog).model
    assert 'GROUND_UART_UNBOUND' in {i.code for i in GroundTargetIssues_Get(reopened, builtin_catalog)}
    assignments = dict(reopened.ground_target.resource_assignments)
    assignments['radio0:radio_nss'] = 'PLATFORM_GPIO_1'
    assignments['radio0:radio_reset'] = 'PLATFORM_GPIO_0'
    reopened.ground_target = replace(reopened.ground_target, resource_assignments=assignments)
    assert 'GROUND_BOARD_FIXED_RESOURCE_MISMATCH' in {
        i.code for i in GroundTargetIssues_Get(reopened, builtin_catalog)}


def test_ground_selection_defaults_and_checkbox_visibility(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(workspace_root/'.work'/tmp_path.name/'settings.ini'), service=FccgService(workspace_root))
    window._GroundBoard_Change('silverstar.board.ground_station_0_5')
    window._GroundTarget_Change('enabled', True)
    window._GroundTarget_Change('radio_plugin', 'silverstar.device.telemetry.sx1281')
    window._GroundTarget_Change('module_variant', 'e28_2g4m12sx')
    window._GroundTarget_Change('pc_interface', 'uart')
    assert not GroundTargetIssues_Get(window._model, window._service.catalog)
    facts = window.ground_target_page.platform_values
    assert facts['cubemx'].text() == '6.15.0'
    assert facts['firmware_package'].text() == 'STM32Cube FW_F1 V1.8.7'
    assert 'silverstar.mcu.stm32f103c8t6' in facts['plugin'].text()
    assert window.ground_target_page.enabled.objectName() == 'standardCheckBox'
    assert window.air_link_page.crc.objectName() == 'standardCheckBox'
    window._GroundTarget_Change('enabled', False)
    assert window.ground_target_page.enabled.isHidden()
    assert window._model.ground_target.enabled
    assert window.ground_target_page.generate_button.isEnabled()
    assert window.ground_target_page.status.text() == window._translator.Text_Get('status.ground_ready')
    assert 'PLATFORM_GPIO_4' in window.ground_target_page.status.toolTip()
    window.close()


def test_explicit_radio0_recovers_fixed_board_bindings_after_open(builtin_catalog):
    model = ReferenceProject_Create('GroundRecovery', catalog=builtin_catalog)
    ground = model.ground_target
    from silverstar_fccg.project.model import GroundRadioConfiguration
    model.ground_target = replace(ground, enabled=True,
        board='silverstar.board.ground_station_0_5',
        mcu='silverstar.mcu.stm32f103c8t6',
        radio_plugin='silverstar.device.telemetry.sx1281',
        module_variant='e28_2g4m12sx', pc_interface='uart',
        hardware=HardwareConfiguration(mode='board_plugin'),
        radio_instances=(GroundRadioConfiguration('radio0',
            'silverstar.device.telemetry.sx1281', 'e28_2g4m12sx', 12),),
        resource_assignments={})
    recovered = ProjectConfiguration_Reconcile(
        ProjectModel_Parse(model.Dictionary_Get()), builtin_catalog).model
    board = builtin_catalog.Component_Get(recovered.ground_target.board)
    expected = {'radio0:' + role.key.removeprefix('telemetry:'): role.default
                for role in board.resource_roles
                if role.fixed and role.key.startswith('telemetry:')}
    assert recovered.ground_target.resource_assignments == expected
    assert not GroundTargetIssues_Get(recovered, builtin_catalog)
    assert ProjectModel_Parse(recovered.Dictionary_Get()).ground_target == recovered.ground_target

    # A user-selected wrong binding is preserved for validation rather than
    # silently replaced during migration.
    wrong = replace(recovered.ground_target,
        resource_assignments={**expected, 'radio0:radio_nss': 'PLATFORM_GPIO_1'})
    model.ground_target = wrong
    checked = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert checked.ground_target.resource_assignments['radio0:radio_nss'] == 'PLATFORM_GPIO_1'
    assert 'GROUND_BOARD_FIXED_RESOURCE_MISMATCH' in {
        issue.code for issue in GroundTargetIssues_Get(checked, builtin_catalog)}


def test_fixed_defaults_preserve_wrong_explicit_binding_and_other_instance(builtin_catalog):
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    from test_f103_ground_reference import _GroundF103Model_Get
    model = _GroundF103Model_Get(builtin_catalog)
    primary = GroundRadioConfigurations_Get(model.ground_target)[0]
    other = replace(primary, instance_id='radio1')
    assignments = {**model.ground_target.resource_assignments,
                   'radio0:radio_nss': 'PLATFORM_GPIO_1',
                   'radio1:radio_bus': 'PLATFORM_SPI_1'}
    model.ground_target = replace(model.ground_target,
        radio_instances=(primary, other), resource_assignments=assignments)
    checked = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert checked.ground_target.resource_assignments['radio0:radio_nss'] == 'PLATFORM_GPIO_1'
    assert checked.ground_target.resource_assignments['radio1:radio_bus'] == 'PLATFORM_SPI_1'
    assert 'GROUND_BOARD_FIXED_RESOURCE_MISMATCH' in {
        issue.code for issue in GroundTargetIssues_Get(checked, builtin_catalog)}


def test_fixed_defaults_do_not_claim_another_instance_gpio(builtin_catalog):
    from silverstar_fccg.project.model import GroundRadioConfigurations_Get
    from test_f103_ground_reference import _GroundF103Model_Get
    model = _GroundF103Model_Get(builtin_catalog)
    primary = GroundRadioConfigurations_Get(model.ground_target)[0]
    assignments = {'radio1:radio_nss': 'PLATFORM_GPIO_0',
                   'radio1:radio_bus': 'PLATFORM_SPI_1'}
    model.ground_target = replace(model.ground_target,
        radio_instances=(primary, replace(primary, instance_id='radio1')),
        resource_assignments=assignments)
    checked = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert 'radio0:radio_nss' not in checked.ground_target.resource_assignments
    assert checked.ground_target.resource_assignments['radio1:radio_nss'] == 'PLATFORM_GPIO_0'
    assert checked.ground_target.resource_assignments['radio1:radio_bus'] == 'PLATFORM_SPI_1'
    assert checked.ground_target.resource_assignments['radio0:radio_bus'] == 'PLATFORM_SPI_1'
    assert 'GROUND_BOARD_FIXED_RESOURCE_MISMATCH' in {
        issue.code for issue in GroundTargetIssues_Get(checked, builtin_catalog)}


def test_fixed_defaults_skip_wrong_resource_kind(builtin_catalog, monkeypatch):
    import silverstar_fccg.project.configuration as configuration
    from test_f103_ground_reference import _GroundF103Model_Get
    original = configuration.BoardResourceProvisions_Get
    monkeypatch.setattr(configuration, 'BoardResourceProvisions_Get', lambda board: tuple(
        replace(item, kind='gpio_input') if item.resource_id == 'PLATFORM_GPIO_0'
        else item for item in original(board)))
    model = _GroundF103Model_Get(builtin_catalog)
    model.ground_target = replace(model.ground_target, resource_assignments={})
    checked = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert 'radio0:radio_nss' not in checked.ground_target.resource_assignments
    assert 'GROUND_RADIO_RESOURCE_UNBOUND' in {
        issue.code for issue in GroundTargetIssues_Get(checked, builtin_catalog)}


def test_current_user_ground_descriptor_recovers_bindings_if_available(workspace_root, tmp_path, private_user_ground_descriptor):
    descriptor = private_user_ground_descriptor
    service = FccgService(workspace_root)
    loaded = service.Project_Open(descriptor)
    recovered = service.ProjectConfiguration_Reconcile(loaded).model
    assert recovered.ground_target.resource_assignments == {
        'radio0:radio_bus': 'PLATFORM_SPI_1',
        'radio0:radio_nss': 'PLATFORM_GPIO_0',
        'radio0:radio_reset': 'PLATFORM_GPIO_1',
        'radio0:radio_busy': 'PLATFORM_GPIO_2',
        'radio0:radio_dio1': 'PLATFORM_GPIO_3',
        'radio0:time': 'PLATFORM_TIME_1',
    }
    assert {issue.code for issue in GroundTargetIssues_Get(recovered, service.catalog)} == {
        'GROUND_LED_POLARITY_CONFLICT'}
    # Correct only the independently invalid LED preference in this copy.
    recovered.ground_target = replace(recovered.ground_target, rx_led_active_high=True)
    result = TargetGeneration_Apply(recovered, service.catalog,
        WorkspacePolicy(tmp_path), tmp_path / 'ground_copy', TargetScope.GROUND)
    ground_dir = result.project_root / 'Ground_Station'
    assert (ground_dir / '.eide/eide.yml').is_file()
    assert (ground_dir / 'Ground_Station.code-workspace').is_file()
    assert (ground_dir / 'Generated/ground_source_graph.json').is_file()
    graph = json.loads((ground_dir / 'Generated/ground_source_graph.json').read_text())
    eide = yaml.safe_load((ground_dir / '.eide/eide.yml').read_text())
    assert {entry['path'] for entry in eide['virtualFolder']['files']} == {
        *graph['sources'], *graph['asm_sources']}
    assert json.loads((ground_dir / 'Ground_Station.code-workspace').read_text())['folders'] == [
        {'path': '.'}]
    reopened = service.Project_Open(result.project_root)
    assert reopened.ground_target.resource_assignments == recovered.ground_target.resource_assignments


def test_current_user_gui_open_recovers_ground_bindings_if_available(qapp, workspace_root, tmp_path, private_user_ground_descriptor, monkeypatch):
    descriptor = private_user_ground_descriptor
    window = MainWindow(SettingsStore(workspace_root / '.work' / tmp_path.name / 'settings.ini'),
                        service=FccgService(workspace_root))
    window._Project_Open(descriptor)
    assert window._model.ground_target.resource_assignments['radio0:radio_bus'] == 'PLATFORM_SPI_1'
    assert window._model.ground_target.resource_assignments['radio0:time'] == 'PLATFORM_TIME_1'
    # 506aafb deliberately localized the body; stable diagnostic identity belongs
    # in the tooltip and the authoritative issue contract, not untranslated prose.
    issues = GroundTargetIssues_Get(window._model, window._service.catalog)
    assert {issue.code for issue in issues} == {'GROUND_LED_POLARITY_CONFLICT'}
    assert 'GROUND_LED_POLARITY_CONFLICT' in window.ground_target_page.status.toolTip()
    assert window.ground_target_page.status.text() == window._translator.Text_Get('ground.issue.summary', count=1)
    assert 'GROUND_' not in window.ground_target_page.status.text()
    shown = []
    monkeypatch.setattr(window, '_Error_Show', lambda *args: shown.append(args))
    monkeypatch.setattr(window._service, 'ProjectRoot_Save', lambda *args, **kwargs: pytest.fail('Invalid Ground must not be saved for generation'))
    before = descriptor.read_bytes()
    window._Targets_Generate('generate_ground')
    assert len(shown) == 1
    assert descriptor.read_bytes() == before
    assert not (descriptor.parent / 'Ground_Station' / 'Makefile').exists()
    window.close()


def test_missing_fixed_board_resource_and_extra_resource(builtin_catalog):
    from test_f103_ground_reference import _GroundF103Model_Get
    model = _GroundF103Model_Get(builtin_catalog)
    ground = model.ground_target
    extra = replace(ground.hardware.resources[0], resource_id='UNUSED_EXTRA')
    model.ground_target = replace(ground, hardware=replace(ground.hardware,
        resources=(*ground.hardware.resources, extra)))
    assert not GroundTargetIssues_Get(model, builtin_catalog)
    model.ground_target = replace(model.ground_target,
        hardware=replace(model.ground_target.hardware, resources=tuple(
            item for item in model.ground_target.hardware.resources
            if item.resource_id != 'PLATFORM_GPIO_0')))
    assert 'GROUND_RADIO_RESOURCE_UNBOUND' in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)}
    model.ground_target = replace(model.ground_target,
        hardware=replace(ground.hardware, resources=tuple(
            replace(item, kind='gpio_input') if item.resource_id == 'PLATFORM_GPIO_0'
            else item for item in ground.hardware.resources)))
    assert 'GROUND_RADIO_RESOURCE_UNBOUND' in {
        issue.code for issue in GroundTargetIssues_Get(model, builtin_catalog)}


def test_explicit_radio_module_switch_retains_fixed_bindings(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(workspace_root / '.work' / tmp_path.name / 'settings.ini'),
                        service=FccgService(workspace_root))
    window._GroundBoard_Change('silverstar.board.ground_station_0_5')
    window._GroundTarget_Change('radio_plugin', 'silverstar.device.telemetry.sx1281')
    window._GroundTarget_Change('module_variant', 'e28_2g4m12sx')
    window._GroundTarget_Change('pc_interface', 'uart')
    from silverstar_fccg.project.model import GroundRadioConfiguration
    window._GroundRadios_Change((GroundRadioConfiguration('radio0',
        'silverstar.device.telemetry.sx1281', 'e28_2g4m12sx', 12),), 'radio0')
    expected = dict(window._model.ground_target.resource_assignments)
    assert len(expected) == 6
    window._GroundTarget_Change('module_variant', 'e28_2g4m12s')
    assert window._model.ground_target.resource_assignments == expected
    assert not GroundTargetIssues_Get(window._model, window._service.catalog)
    window.close()
