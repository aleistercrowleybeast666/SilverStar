from dataclasses import replace

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import HardwareConfiguration, ProjectModel_Parse
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.main_window import MainWindow


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
    assert not window.ground_target_page.generate_button.isEnabled()
    assert window.ground_target_page.status.text() != window._translator.Text_Get('status.ground_ready')
    window.close()
