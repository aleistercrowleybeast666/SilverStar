"""Actual completed ordinary candidates and real Qt event-loop lifecycle."""
from pathlib import Path
from threading import Event,get_ident
from copy import deepcopy
import hashlib,json,time,os
import pytest
import shiboken6
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QMessageBox,QFileDialog
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.app.usb_ground_flow import UsbGroundBound_Is


def _Wait(qapp,condition,seconds=30):
    end=time.monotonic()+seconds
    while not condition() and time.monotonic()<end:
        qapp.processEvents();time.sleep(.003)
    assert condition(),'bounded actual Qt wait expired'


def _Idle(window):
    return (window._active_worker is None and window._usb_refresh_pending is None and
            not window._usb_refresh_timer.isActive() and not window._retired_workers)


@pytest.fixture(params=['STM32F103C8T6','STM32C071FBP6'])
def completed_window(request,qapp,tmp_path_factory,builtin_catalog,monkeypatch):
    rows=[json.loads(x) for x in Path(os.environ['SILVERSTAR_USB_REFRESH_INDEX']).read_text().splitlines()]
    row=next(r for r in rows if r['part']==request.param)
    output=Path(row['output']);receipt=json.loads((output/'receipt.json').read_text())
    root=tmp_path_factory.mktemp('view')
    service=FccgService(root);service.catalog=builtin_catalog;service.assembler.catalog=builtin_catalog
    cache=Path(receipt['snapshot_root']).parent.parent
    service.hardware_importer.cache_root=cache;service.hardware_importer.policy=WorkspacePolicy(cache.parent)
    current=MainWindow(SettingsStore(root/'settings.ini'),service=service)
    current._model=ProjectModel_Load(Path(row['project_root'])/'SilverStar.ssproject')
    current._project_root=Path(row['project_root'])
    current._MessageBox_Exec=lambda *a,**k:QMessageBox.StandardButton.Yes
    errors=[];monkeypatch.setattr(current,'_Error_Show',lambda *a:errors.append(a))
    before={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ['receipt.json','backend-receipt.json','build/native.elf','build/analysis/native.elf']}
    try:yield current,output,errors,request.param
    finally:
        if shiboken6.isValid(current):
            current._Task_Cancel()
            _Wait(qapp,lambda:current._active_worker is None)
            current.close();qapp.processEvents()
        assert before=={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in before}


def test_complete_refresh_shares_one_plan_and_keeps_qt_responsive(completed_window,qapp,monkeypatch,tmp_path):
    current,output,errors,part=completed_window
    plans=[];owner=get_ident();original=current._service.UsbGroundCandidate_Plan
    def plan(*a,**k):
        plans.append(get_ident());return original(*a,**k)
    monkeypatch.setattr(current._service,'UsbGroundCandidate_Plan',plan)
    ticks=[];timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:ticks.append(time.monotonic()))
    timer.start();start=time.monotonic()
    try:
        current._Project_Refresh()
        immediate=time.monotonic()-start
        assert immediate<.75,immediate
        # Record view rendering separately from the async audit interval.
        # The unchanged legacy view population has its own measured cost.
        worker_start=time.monotonic();ticks.clear()
        _Wait(qapp,lambda:_Idle(current))
    finally:timer.stop()
    gaps=[b-a for a,b in zip([worker_start]+ticks,ticks+[time.monotonic()])]
    assert len(ticks)>=10,len(ticks)
    assert max(gaps)<.5,max(gaps)
    assert len(plans)==1 and all(p!=owner for p in plans),plans
    assert not errors,errors
    assert current.build_page._target_generated['ground']
    assert len(current.build_page._target_quality_records['ground'])==2
    assert current.build_page._target_quality_states['ground']=={}
    (tmp_path/'refresh-response.json').write_text(json.dumps({'part':part,'synchronous_refresh_seconds':immediate,
        'total_validation_seconds':time.monotonic()-start,'ticks':len(ticks),'max_tick_gap_seconds':max(gaps),
        'plan_calls':len(plans),'plan_ran_off_gui_thread':True,'quality_records':2},indent=2),encoding='utf8')


def test_pending_refresh_coalesces_and_project_switch_drops_old_result(completed_window,qapp,monkeypatch):
    current,output,errors,part=completed_window
    entered=Event();release=Event();original=current._service.UsbGroundCandidate_Plan;calls=[]
    def plan(*a,**k):
        calls.append(1);entered.set();assert release.wait(10);return original(*a,**k)
    monkeypatch.setattr(current._service,'UsbGroundCandidate_Plan',plan)
    try:
        current._Project_Refresh();current._Project_Refresh()
        _Wait(qapp,entered.is_set)
        assert len(calls)==1
        current._model=current._service.ProjectDraft_Create('replacement project')
        current._project_root=None;current._Project_Refresh()
        release.set();_Wait(qapp,lambda:_Idle(current))
        assert current._model.identity.name=='replacement project'
        assert not UsbGroundBound_Is(current._model)
        assert not current.build_page._target_generated['ground']
        assert current.build_page._target_quality_records['ground']==()
        assert not errors,errors
    finally:release.set()


@pytest.mark.parametrize('operation',['cancel','close'])
def test_refresh_cancel_or_close_uses_owned_worker(completed_window,qapp,monkeypatch,operation):
    current,output,errors,part=completed_window
    entered=Event();release=Event();original=current._service.UsbGroundCandidate_Plan
    def plan(*a,**k):
        entered.set();assert release.wait(10);return original(*a,**k)
    monkeypatch.setattr(current._service,'UsbGroundCandidate_Plan',plan)
    try:
        current.show();current._Project_Refresh();_Wait(qapp,entered.is_set)
        if operation=='cancel':current.cancel_button.click()
        else:
            current.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            current.close()
            assert shiboken6.isValid(current) and current._close_after_worker
        release.set()
        if operation=='close':_Wait(qapp,lambda:not shiboken6.isValid(current))
        else:
            _Wait(qapp,lambda:_Idle(current))
            assert current.progress_bar.property('taskState')=='cancelled'
            assert not current.build_page._target_generated['ground']
        assert not errors,errors
    finally:release.set()


def test_queued_refresh_close_never_starts_after_destruction(completed_window,qapp,monkeypatch):
    current,output,errors,part=completed_window;calls=[]
    monkeypatch.setattr(current._service,'UsbGroundCandidate_Plan',lambda *a,**k:calls.append(1))
    current.show();current.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    current._Project_Refresh()
    assert current._usb_refresh_pending is not None
    current.close();_Wait(qapp,lambda:not shiboken6.isValid(current))
    assert not calls


def test_actual_artifact_action_validation_runs_off_gui_thread(completed_window,qapp,monkeypatch):
    current,output,errors,part=completed_window
    owner=get_ident();calls=[];original=current._service.UsbGroundCandidate_Plan
    def plan(*a,**k):
        calls.append(get_ident());return original(*a,**k)
    monkeypatch.setattr(current._service,'UsbGroundCandidate_Plan',plan)
    start=time.monotonic();current._TargetAction_Request('ground_artifact_check')
    assert time.monotonic()-start<.25
    _Wait(qapp,lambda:_Idle(current))
    assert calls and all(c!=owner for c in calls)
    assert not errors,errors
    assert 'verified' in current.status_label.text()


@pytest.mark.parametrize('outcome',['success','error'])
def test_late_import_cannot_overwrite_switched_project(completed_window,qapp,monkeypatch,outcome):
    current,output,errors,part=completed_window
    current._model=current._service.ProjectDraft_Create('original import request')
    current._model.ground_target=__import__('dataclasses').replace(current._model.ground_target,pc_interface='usb_cdc')
    entered=Event();release=Event();original=current._service.UsbGroundProject_Import
    def import_project(*a,**k):
        entered.set();assert release.wait(10)
        if outcome=='error':raise ValueError('ordinary import failure after project switch')
        return original(*a,**k)
    monkeypatch.setattr(current._service,'UsbGroundProject_Import',import_project)
    source=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-08\task\usb-validation\cube-f103-usb' if part=='STM32F103C8T6' else
                r'C:\Users\chdxm\Documents\Codex\2026-10-08\task\c071-cubemx-input\full-native-clean\C071FBP6_PCD_TEST')
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a:str(source))
    try:
        current._GroundCubeMxImport_Request(True);_Wait(qapp,entered.is_set)
        current._model=current._service.ProjectDraft_Create('switched during import')
        current._project_root=None;current._Project_Refresh()
        release.set();_Wait(qapp,lambda:_Idle(current))
        assert current._model.identity.name=='switched during import'
        assert not UsbGroundBound_Is(current._model)
        assert not errors,errors
    finally:release.set()
