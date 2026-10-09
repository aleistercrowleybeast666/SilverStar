"""Isolated GUI contracts; no target build or hardware validation."""
from dataclasses import replace
from types import SimpleNamespace
from threading import Event
import pytest
from PySide6.QtWidgets import QFileDialog,QMessageBox
from test_scg_ui_metadata_hotfix import window
from test_f103_ground_reference import _GroundF103Model_Get
from test_task_progress_busy import _Wait
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.build.runner import BuildAction, BuildResult, BuildRunner
import silverstar_fccg.ui.main_window as main_window_module

def test_enabled_led_before_board_selection_adopts_unique_declared_binding(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._GroundBoard_Change('')
    window._GroundActivityLed_Toggle(True)
    window._GroundBoard_Change('silverstar.board.ground_station_0_5')
    ground = window._model.ground_target
    assert ground.tx_led_resource == ground.rx_led_resource == 'PLATFORM_GPIO_6'
    assert not ground.tx_led_active_high and not ground.rx_led_active_high
    assert not GroundTargetIssues_Get(window._model, window._service.catalog)

def test_enabled_led_missing_binding_is_visible_beside_radio_only_table(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._model.ground_target = replace(window._model.ground_target, activity_led_enabled=True)
    window._Project_Refresh()
    page = window.ground_target_page
    assert [i.code for i in GroundTargetIssues_Get(window._model, window._service.catalog)] == ['GROUND_LED_OUTPUT_UNBOUND']
    assert all(not view.validation_error for view in page._resources)
    assert page.resource_scope_notice.property('statusLevel') == 'warning'
    assert window._translator.Text_Get('ground.issue.led') in page.resource_scope_notice.text()
    assert not page.activity_led_notice.isHidden()
    assert page.activity_led_notice.property('statusLevel') == 'error'

def test_unbound_ground_radio_row_is_red_and_refresh_recovers(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    ground = window._model.ground_target
    window._model.ground_target = replace(ground, resource_assignments={
        key:value for key,value in ground.resource_assignments.items() if key != 'radio0:radio_bus'})
    window._Project_Refresh()
    page = window.ground_target_page
    row = next(i for i,view in enumerate(page._resources) if view.name.endswith('radio_bus'))
    assert page._resources[row].validation_error
    assert page.resource_table.item(row,5).foreground().color().name() == '#d32f2f'
    window._model.ground_target = ground
    window._Project_Refresh()
    assert not page._resources[row].validation_error
    assert page.resource_table.item(row,5).foreground().color().name() != '#d32f2f'

def test_board_selection_preserves_explicit_invalid_led_binding_and_blocks(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._model.ground_target = replace(window._model.ground_target,
        activity_led_enabled=True, tx_led_resource='MISSING')
    window._GroundBoard_Change('silverstar.board.ground_station_0_5')
    assert window._model.ground_target.tx_led_resource == 'MISSING'
    assert any(issue.code == 'GROUND_LED_OUTPUT_UNBOUND'
               for issue in GroundTargetIssues_Get(window._model,window._service.catalog))

def test_ground_constraint_errors_are_mapped_to_the_affected_radio_row(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    ground=window._model.ground_target
    resources=tuple(replace(resource,metadata={**resource.metadata,'clock_hz':20_000_000})
        if resource.resource_id=='PLATFORM_SPI_1' else resource for resource in ground.hardware.resources)
    window._model.ground_target=replace(ground,hardware=replace(ground.hardware,resources=resources))
    window._Project_Refresh()
    views=window.ground_target_page._resources
    bus=next(view for view in views if view.name.endswith('radio_bus'))
    assert bus.validation_error
    assert all(not view.validation_error for view in views if not view.name.endswith('radio_bus'))

@pytest.mark.parametrize('passed', [True,False])
def test_power10_automatic_result_and_unproven_contract_review_are_separate(window,passed):
    record=SimpleNamespace(task='power10_check',result='passed' if passed else 'failed',
                           summary='POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending',timestamp='',duration=0)
    window.build_page.QualityResults_Set((record,))
    assert window.build_page.quality_result_labels['power10_check'].property('statusLevel') == ('success' if passed else 'error')
    review=window.build_page.power10_review_label
    assert not review.isHidden() and review.property('statusLevel') == 'warning'
    assert 'NOT_PROVEN' in review.text()
    window.build_page.QualityResults_Set(())
    assert review.isHidden()

def test_persisted_passed_record_with_explicit_critical_fail_never_turns_green(window):
    record=SimpleNamespace(task='power10_check',result='passed',
        summary='POWER10_CONTRACT_REVIEW|FAIL|unchecked_recovery',timestamp='',duration=0)
    window.build_page.QualityResults_Set((record,))
    assert window.build_page.quality_result_labels['power10_check'].property('statusLevel')=='error'
    assert window.build_page.power10_review_label.property('statusLevel')=='error'
    assert 'FAIL' in window.build_page.power10_review_label.text()

def test_power10_dialog_opens_after_terminal_progress(qapp,window,monkeypatch):
    shown=[]
    monkeypatch.setattr(window,'_MessageBox_Exec',lambda *args,**kwargs:shown.append(
        (window.progress_bar.maximum(),window.progress_bar.property('taskState'))))
    monkeypatch.setattr(window,'_Project_Refresh',lambda:None)
    window._project_root=None
    output='POWER10_RULE5|Flight|functions=2|eligible_assertions=1|\nPOWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending\n'
    result=BuildResult(BuildAction.POWER10_CHECK,(),0,output)
    window.progress_bar.setRange(0,0)
    window._worker_outcome=('result',result,'')
    window._worker_result_callback=window._Build_Complete
    window._Task_Finish()
    assert window.progress_bar.maximum()==1000 and window.progress_bar.value()==1000
    assert shown==[]
    qapp.processEvents()
    assert shown==[(1000,'success')]

@pytest.mark.parametrize('case',['success','make_failure','audit_failure'])
def test_target_build_has_real_compile_audit_phases_and_terminal_outcome(qapp,window,tmp_path,monkeypatch,case):
    window._model=_GroundF103Model_Get(window._service.catalog)
    window._project_root=tmp_path/'project'
    target=window._project_root/'Ground_Station'
    target.mkdir(parents=True)
    (target/'Makefile').write_text('all:\n',encoding='utf8')
    release,started=Event(),Event()
    errors=[]
    monkeypatch.setattr(window,'_Error_Show',lambda *args:errors.append(args))
    def process(self,*args):
        started.set()
        assert release.wait(10)
        return (1 if case=='make_failure' else 0),['mock compile/link completed\n']
    monkeypatch.setattr(BuildRunner,'_Process_Run',process)
    monkeypatch.setattr(main_window_module,'BuildAudit_Run',lambda *args,**kwargs:
        SimpleNamespace(errors=('injected audit failure',) if case=='audit_failure' else (),regions=()))
    try:
        window._TargetAction_Request('ground_build')
        _Wait(qapp,lambda:started.is_set() and window.progress_bar.maximum()==1000)
        assert window._active_worker is not None and window.progress_bar.value()==0
        release.set()
        _Wait(qapp,lambda:window._active_worker is None)
        passed=case=='success'
        assert window.progress_bar.maximum()==1000
        assert window.progress_bar.property('taskState')==('success' if passed else 'error')
        assert (window.progress_bar.value()==1000) is passed
        assert bool(errors) is not passed
    finally:
        release.set()
        _Wait(qapp,lambda:window._active_worker is None)

@pytest.mark.parametrize('target',['flight','ground'])
def test_one_visible_directory_import_entry_retains_legacy_api(window,tmp_path,monkeypatch,target):
    page=window.board_hardware_page if target=='flight' else window.ground_target_page
    assert page.import_ioc_button.isHidden()
    assert not page.import_directory_button.isHidden()
    assert page.import_directory_button.text()==window._translator.Text_Get('action.import_cubemx_project')
    selected=tmp_path/'selected_project'
    selected.mkdir()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(selected))
    monkeypatch.setattr(window,'_MessageBox_Exec',lambda *args,**kwargs:QMessageBox.StandardButton.Ok)
    tasks=[]
    monkeypatch.setattr(window,'Task_Run',lambda run,callback,*args,**kwargs:tasks.append((run,callback)))
    page.import_directory_button.click()
    assert len(tasks)==1
    assert tasks[0][1]==(window._CubeMxImport_Complete if target=='flight' else window._GroundCubeMxImport_Complete)
