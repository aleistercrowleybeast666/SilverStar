from dataclasses import replace
import shutil

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.ui.main_window import MainWindow


def window_create(workspace_root, tmp_path):
    return MainWindow(SettingsStore(workspace_root/'.work'/tmp_path.name/'field.ini'),
                      service=FccgService(workspace_root))


def test_new_defaults_and_old_memory_policies(workspace_root):
    service=FccgService(workspace_root)
    new=service.ProjectDraft_Create('Field')
    assert new.build.memory_layout == 'auto'
    assert new.hardware.mode == new.ground_target.hardware.mode == 'custom'
    assert new.hardware.provider == new.ground_target.hardware.provider
    for policy in ('legacy','eskf_window_sram','auto'):
        old=new.Dictionary_Get();old['build']['memory_layout']=policy
        assert ProjectModel_Parse(old).build.memory_layout == policy
    old=new.Dictionary_Get();del old['build']['memory_layout']
    old['ground_target']['hardware']['mode']='unselected'
    old['ground_target']['hardware']['source_kind']='unselected'
    old['ground_target']['hardware']['provider']=''
    reopened=ProjectModel_Parse(old)
    assert reopened.build.memory_layout == 'legacy'
    assert reopened.ground_target.hardware.mode == 'unselected'


def test_ground_controls_save_reopen_keep_actual_uart(qapp,workspace_root,tmp_path):
    w=window_create(workspace_root,tmp_path);w.show()
    p=w.ground_target_page
    assert p.board.currentData()=='__custom__'
    assert p.import_ioc.isEnabled() and p.import_directory.isEnabled()
    assert not p.save_instance.isEnabled()
    p.board.setCurrentIndex(p.board.findData('silverstar.board.ground_station_0_5'))
    p.enabled.setChecked(True)
    p.radio.setCurrentIndex(p.radio.findData('silverstar.device.telemetry.sx1281'))
    p.pc_interface.setCurrentIndex(p.pc_interface.findData('uart'))
    qapp.processEvents()
    assert w._model.ground_target.module_variant=='e28_2g4m12sx'
    assert p.pc_resource.currentData()=='PLATFORM_UART_1'
    assert 'USART1' in p.pc_resource.currentText()
    assert not GroundTargetIssues_Get(w._model,w._service.catalog)
    before=w._model.ground_target
    destination=tmp_path/'saved'
    w._service.ProjectRoot_Save(w._model,destination,create_new=True)
    w._Project_Open(destination)
    assert w._model.ground_target==before
    assert p.pc_resource.currentData()=='PLATFORM_UART_1'
    assert p.generate_button.isEnabled()
    # Selecting the current radio must retain its saved module and wiring.
    w._GroundTarget_Change('radio_plugin',before.radio_plugin)
    assert w._model.ground_target==before
    p.board.setCurrentIndex(p.board.findData('__custom__'))
    assert w._model.ground_target.hardware.mode=='custom'
    assert p.import_ioc.isEnabled() and not p.save_instance.isEnabled()
    w.close()


def test_empty_and_stale_uart_are_explained(qapp,workspace_root,tmp_path):
    w=window_create(workspace_root,tmp_path);w.show()
    w._GroundTarget_Change('enabled',True)
    w._GroundTarget_Change('pc_interface','uart')
    p=w.ground_target_page
    assert p.pc_resource_notice.text()
    assert not p.pc_resource.isEnabled()
    w._GroundBoard_Change('silverstar.board.ground_station_0_5')
    ground=w._model.ground_target
    stale=replace(ground,pc_resource='USART_DOES_NOT_EXIST')
    w._model.ground_target=stale;w._Project_Refresh()
    assert p.pc_resource.currentData()=='USART_DOES_NOT_EXIST'
    assert not p.pc_resource.model().item(p.pc_resource.currentIndex()).isEnabled()
    assert p.pc_resource_notice.text()
    assert 'GROUND_UART_UNBOUND' in {x.code for x in GroundTargetIssues_Get(w._model,w._service.catalog)}
    w._model.ground_target=replace(ground,hardware=replace(ground.hardware,mode='custom',
        resources=tuple(r for r in ground.hardware.resources if r.kind!='uart')),pc_resource='')
    w._TargetPages_Refresh(w._model)
    assert not p.pc_resource.isEnabled()
    assert p.pc_resource_notice.text()
    assert p.pc_resource.count()==1
    w.close()


def test_ground_ioc_import_updates_actual_resources(qapp,workspace_root,tmp_path):
    w=window_create(workspace_root,tmp_path)
    # A saved test PCB must not alter later windows' real catalog choices.
    w._service.catalog.installed_root=tmp_path/'installed'
    w._service.installer.installed_root=tmp_path/'installed'
    w._service.catalog.Scan()
    from test_f103_ground_reference import _GroundF103Model_Get
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.core.workspace import WorkspacePolicy
    output=tmp_path/'generated'
    TargetGeneration_Apply(_GroundF103Model_Get(w._service.catalog),w._service.catalog,
                           WorkspacePolicy(tmp_path),output,TargetScope.GROUND)
    source=tmp_path/'CubeMX_inputs'
    shutil.copytree(workspace_root/'plugins/builtin/silverstar_board_ground_station_0_5/payload',source)
    shutil.copytree(output/'Ground_Station/Drivers',source/'Drivers')
    for pattern in ('*.s','*.ld'):
        for file in (output/'Ground_Station').glob(pattern):shutil.copy2(file,source/file.name)
    result=w._service.CubeMxProject_Import(source,w._model,risk_acknowledged=True)
    w._GroundCubeMxImport_Complete(result)
    w._GroundTarget_Change('enabled',True)
    w._GroundTarget_Change('pc_interface','uart')
    p=w.ground_target_page
    ids={p.pc_resource.itemData(i) for i in range(1,p.pc_resource.count())}
    assert ids=={'USART1'}
    assert w._model.ground_target.hardware.mode=='custom'
    assert w._model.ground_target.mcu=='silverstar.mcu.stm32f103c8t6'
    assert p.import_directory.isEnabled()
    assert p.save_instance.isEnabled()
    saved=w._service.CustomBoardPlugin_SaveLocal(w._model,component_id='local.board.ground.field',
                                              name='Field Ground',target_role='ground')
    assert saved.component_id=='local.board.ground.field'
    w._Project_Refresh()
    assert p.board.findData(saved.component_id)>=0
    w.close()


def test_enabled_ground_without_inventory_does_not_claim_ready(qapp,workspace_root,tmp_path):
    w=window_create(workspace_root,tmp_path)
    p=w.ground_target_page
    w._GroundTarget_Change('enabled',True)
    assert not w._model.ground_target.hardware.inventory
    assert GroundTargetIssues_Get(w._model,w._service.catalog)
    assert p.generate_button.isEnabled()
    for language in ('zh_CN','en_US'):
        w.Language_Apply(language)
        tooltip=p.generate_button.toolTip()
        assert tooltip==w._translator.Text_Get('status.ground_configuration_required')
        assert tooltip!='status.ground_configuration_required'
        assert 'READY' not in tooltip
    w._GroundBoard_Change('silverstar.board.ground_station_0_5')
    w._GroundTarget_Change('radio_plugin','silverstar.device.telemetry.sx1281')
    w._GroundTarget_Change('pc_interface','uart')
    assert not GroundTargetIssues_Get(w._model,w._service.catalog)
    for language in ('zh_CN','en_US'):
        w.Language_Apply(language)
        assert p.generate_button.toolTip()==w._translator.Text_Get('status.ground_ready')
    w._GroundTarget_Change('enabled',False)
    assert not p.generate_button.isEnabled()
    assert p.generate_button.toolTip()==w._translator.Text_Get('status.ground_disabled')
    w.close()
