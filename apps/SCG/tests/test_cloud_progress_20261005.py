import threading
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.build.runner import BuildAction, BuildResult, BuildRunner, BuildPlan
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import GenerationPlan, ApplyResult
from silverstar_fccg.project.validation import ProjectValidationResult
from silverstar_fccg.ui.main_window import MainWindow
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def window(qtbot,tmp_path):
    w=MainWindow(SettingsStore(tmp_path/'settings.ini'),service=FccgService(ROOT))
    qtbot.addWidget(w)
    w._MessageBox_Exec=lambda *a,**kw: QMessageBox.StandardButton.Ok
    yield w
    if w._active_worker:
        w._active_worker.Worker_Cancel()
        qtbot.waitUntil(lambda:w._active_worker is None,timeout=5000)
    w.close()

def test_invalid_power10_through_real_worker_stays_error(window,qtbot):
    result=BuildResult(BuildAction.POWER10_CHECK,('make',),0,'')
    def work(ctx):
        ctx.Progress_Report(.37,'status.build_running'); return result
    assert window.Task_Run(work,window._Build_Complete,indeterminate=False)
    qtbot.waitUntil(lambda:window._active_worker is None)
    assert window.progress_bar.value()==370
    assert window.progress_bar.property('taskState')=='error'
    assert window._project_state.value=='error'

def test_old_finish_does_not_hide_or_complete_new_task(window,qtbot):
    entered,release=threading.Event(),threading.Event()
    result=[]
    def next_task(ctx):
        ctx.Progress_Report(.25,'status.task_running');entered.set();assert release.wait(5);return 'second'
    def first_done(_): assert window.Task_Run(next_task,result.append,indeterminate=False)
    try:
        window.Task_Run(lambda ctx:'first',first_done,indeterminate=False)
        qtbot.waitUntil(entered.is_set)
        qtbot.waitUntil(lambda:window.progress_bar.value()==250)
        qtbot.wait(450)
        assert window._active_worker is not None
        assert window.progress_bar.value()==250
        assert not window.progress_bar.isHidden()
        assert not window.cancel_button.isHidden()
        assert not window.new_action.isEnabled()
    finally:
        release.set();qtbot.waitUntil(lambda:window._active_worker is None)
    assert result==['second']

# Deliberately assert desired corrected semantics; red means remaining defect.
def test_plan_apply_keeps_one_operation_progress_monotone(window,qtbot,monkeypatch,tmp_path):
    entered,release=threading.Event(),threading.Event()
    window._model=window._service.ReferenceProject_Create('ProgressChain')
    window._project_root=tmp_path/'project'
    window._Project_Refresh()
    monkeypatch.setattr(window._service,'GenerationPlan_Create',lambda model,root:GenerationPlan(Path(root),(),ProjectValidationResult(()),new_project=True))
    monkeypatch.setattr(window,'_GenerationPlan_ApplyAllowed',lambda plan:True)
    def prepare(model,root,**kwargs):
        entered.set();assert release.wait(5)
        return ApplyResult(Path(root),1,0,0)
    monkeypatch.setattr(window._service,'Project_HardwarePrepare',prepare)
    monkeypatch.setattr(window,'_HardwarePrepareApply_Complete',lambda result:None)
    values=[];window.progress_bar.valueChanged.connect(values.append)
    try:
        window._HardwarePrepare_Request()
        qtbot.waitUntil(entered.is_set)
        qtbot.wait(20)
        print('PLAN_APPLY_VALUES',values)
        assert values==sorted(values),f'one action regressed: {values}'
    finally:
        release.set();qtbot.waitUntil(lambda:window._active_worker is None)

def test_callback_failure_does_not_leave_success_terminal(window,qtbot,monkeypatch):
    errors=[];monkeypatch.setattr(window,'_Error_Show',lambda error,*a:errors.append(error))
    def callback(_): raise RuntimeError('completion callback failure')
    def task(ctx):ctx.Progress_Report(.37,'status.task_running');return 'read-only-result'
    window.Task_Run(task,callback,indeterminate=False)
    qtbot.waitUntil(lambda:window._active_worker is None)
    assert errors
    assert window.progress_bar.property('taskState')=='error'
    assert window.progress_bar.value()<1000

def test_cancel_queued_plan_does_not_start_apply(window,qtbot,monkeypatch,tmp_path):
    plan_finished,release=threading.Event(),threading.Event()
    applied=[]
    window._model=window._service.ReferenceProject_Create('CancelPlan')
    window._project_root=tmp_path/'project'
    window._Project_Refresh()
    monkeypatch.setattr(window._service,'GenerationPlan_Create',lambda model,root:GenerationPlan(Path(root),(),ProjectValidationResult(()),new_project=True))
    monkeypatch.setattr(window,'_GenerationPlan_ApplyAllowed',lambda plan:True)
    def prepare(model,root,**kwargs):
        applied.append(True)
        return ApplyResult(Path(root),1,0,0)
    monkeypatch.setattr(window._service,'Project_HardwarePrepare',prepare)
    monkeypatch.setattr(window,'_HardwarePrepareApply_Complete',lambda result:None)
    window._HardwarePrepare_Request()
    worker=window._active_worker
    # finished is queued to window; observe worker emission without pumping GUI.
    worker.signals.finished.connect(plan_finished.set,Qt.ConnectionType.DirectConnection)
    assert plan_finished.wait(5)
    window._Task_Cancel()
    qtbot.waitUntil(lambda:window._active_worker is None)
    assert applied==[], 'cancelled queued plan started generation'
