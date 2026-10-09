"""Measured build progress; tiny scheduler fixtures are not firmware evidence."""
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import importlib.util,os,shutil,subprocess,sys
import pytest
from silverstar_fccg.build.runner import BuildRunner
from silverstar_fccg.build.target_progress import TargetProgressPlan,TargetProgressTracker
from silverstar_fccg.core.workspace import WorkspacePolicy
from test_scg_ui_metadata_hotfix import window
from test_f103_ground_reference import _GroundF103Model_Get
from test_task_progress_busy import _Wait
import silverstar_fccg.ui.main_window as main_window_module

def test_plan_counts_unique_pending_objects_link_bin_and_size():
    lines=['gcc -c a.c -o build/a.o','gcc -c b.s -o build/b.o','gcc -c a.c -o build/a.o',
           'gcc build/a.o build/b.o -o build/app.elf','arm-none-eabi-objcopy -O binary build/app.elf build/app.bin',
           'arm-none-eabi-size build/app.elf > build/app.size']
    plan=TargetProgressPlan.FromLines_Get(lines)
    assert not plan.markers and plan.build_plan.total_steps==5 and plan.build_plan.compile_steps==2
    assert TargetProgressPlan.FromLines_Get(['make: Nothing to be done for all.']).build_plan.total_steps==0

def test_parallel_recipe_completion_does_not_credit_launch_or_intermediate_winning_child():
    plan=TargetProgressPlan.FromLines_Get(['gcc -c a.c -o build/a.o','gcc -c b.c -o build/b.o'])
    progress=[]
    tracker=TargetProgressTracker(plan,progress.append,None)
    for line in ['Putting child 0xA (build/a.o) PID 1','Putting child 0xB (build/b.o) PID 2',
                 'Reaping winning child 0xA PID 1','Live child 0xA (build/a.o) PID 3']:
        tracker.Line_Report(line)
    assert not tracker.completed
    for line in ['Reaping winning child 0xB PID 2','Removing child 0xB PID 2 from chain.',
                 'Removing child 0xB PID 2 from chain.']:
        tracker.Line_Report(line)
    assert tracker.completed=={('COMPILE','build/b.o')}
    tracker.Line_Report('Reaping losing child 0xA PID 3')
    tracker.Line_Report('Removing child 0xA PID 3 from chain.')
    assert tracker.completed=={('COMPILE','build/b.o')}
    assert max(item.completed_steps for item in progress)==1

def test_flight_done_markers_are_deduplicated_and_windows_quotes_are_supported():
    plan=TargetProgressPlan.FromLines_Get(['echo "FCCG_PROGRESS|COMPILE_DONE|a.c"']*2)
    tracker=TargetProgressTracker(plan,None,None)
    tracker.Line_Report('"FCCG_PROGRESS|COMPILE_BEGIN|a.c"')
    assert not tracker.completed
    tracker.Line_Report('"FCCG_PROGRESS|COMPILE_DONE|a.c"')
    tracker.Line_Report('FCCG_PROGRESS|COMPILE_DONE|a.c')
    assert plan.build_plan.total_steps==len(tracker.completed)==1

def test_unknown_output_reports_processed_lines_without_fabricating_completed_objects():
    progress=[]
    tracker=TargetProgressTracker(TargetProgressPlan.FromLines_Get(['custom command']),progress.append,None)
    tracker.Line_Report('working')
    assert progress[-1].stage=='UNMEASURED' and progress[-1].stage_completed==1
    assert progress[-1].total_steps==progress[-1].completed_steps==0

@pytest.mark.parametrize('outcome',['success','failure','cancelled'])
def test_gui_advances_after_each_verified_object_and_caps_until_audit(qapp,window,tmp_path,monkeypatch,outcome):
    if os.environ.get('SCG_PROGRESS_PRE191'):
        source=subprocess.check_output(['git','show','191fd39:apps/SCG/src/silverstar_fccg/ui/main_window.py'],cwd=window._service.policy.root)
        path=tmp_path/'pre191.py'
        path.write_bytes(source)
        spec=importlib.util.spec_from_file_location('scg_pre191',path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        window._TargetAction_Request=module.MainWindow._TargetAction_Request.__get__(window)
    window._model=_GroundF103Model_Get(window._service.catalog)
    window._project_root=tmp_path/'project'
    root=window._project_root/'Ground_Station'
    root.mkdir(parents=True)
    (root/'Makefile').write_text('all:\n',encoding='utf8')
    first,release=Event(),Event()
    dry=[f'echo "FCCG_PROGRESS|{stage}_DONE|{subject}"\n' for stage,subject in
         [('COMPILE','a.c'),('COMPILE','b.c'),('COMPILE','c.c'),('LINK','build/ground.elf')]]
    def process(command,root,environment,token,line_callback=None):
        if '-n' in command: return 0,dry
        lines=['FCCG_PROGRESS|COMPILE_BEGIN|a.c\n','FCCG_PROGRESS|COMPILE_DONE|a.c\n']
        for line in lines: line_callback(line)
        first.set()
        assert release.wait(30)
        if outcome!='success': return 1,lines
        for line in ['FCCG_PROGRESS|COMPILE_DONE|b.c\n','FCCG_PROGRESS|COMPILE_DONE|c.c\n',
                     'FCCG_PROGRESS|LINK_DONE|build/ground.elf\n']:
            lines.append(line);line_callback(line)
        return 0,lines
    monkeypatch.setattr(BuildRunner,'_Process_Run',staticmethod(process))
    monkeypatch.setattr(main_window_module,'BuildAudit_Run',lambda *args,**kwargs:SimpleNamespace(errors=(),regions=()))
    monkeypatch.setattr(window,'_Error_Show',lambda *args:None)
    try:
        window._TargetAction_Request('ground_build')
        _Wait(qapp,first.is_set)
        # The worker event only proves emission; Qt delivers queued GUI slots later.
        _Wait(qapp,lambda:window.progress_bar.value()==200)
        assert window.progress_bar.maximum()==1000
        assert window.progress_bar.value()==200  # one of four make units + the audit
        assert window._active_worker is not None
        if outcome=='cancelled': window._Task_Cancel()
        release.set()
        _Wait(qapp,lambda:window._active_worker is None)
        assert window.progress_bar.property('taskState')==('success' if outcome=='success' else 'error' if outcome=='failure' else 'cancelled')
        assert (window.progress_bar.value()==1000) is (outcome=='success')
    finally:
        release.set();_Wait(qapp,lambda:window._active_worker is None)

def test_native_parallel_incremental_and_no_work_recipe_trace(tmp_path,monkeypatch):
    make=shutil.which('mingw32-make') or shutil.which('make')
    if not make: pytest.skip('GNU make unavailable')
    monkeypatch.setenv('MAKEFLAGS','-j2')
    root=tmp_path/'native'
    root.mkdir()
    (root/'fake_tool.py').write_text("from pathlib import Path\nimport sys,time\ntime.sleep(.02)\np=Path(sys.argv[sys.argv.index('-o')+1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic scheduler fixture')\n",encoding='utf8')
    (root/'a.c').write_text('synthetic input a',encoding='utf8')
    (root/'b.c').write_text('synthetic input b',encoding='utf8')
    (root/'Makefile').write_text(f'CC := "{Path(sys.executable).as_posix()}" fake_tool.py\nall: build/app.elf\nbuild/app.elf: build/a.o build/b.o\n\t$(CC) $^ -o $@\nbuild/%.o: %.c\n\t@echo prep\n\t$(CC) -c $< -o $@\n\t@echo tail\n',encoding='utf8')
    from silverstar_fccg.project.reference import ReferenceProject_Create
    model=ReferenceProject_Create('NativeProgress')
    model.build=replace(model.build,make_command=make)
    runner=BuildRunner(WorkspacePolicy(root))
    events=[]
    result=runner.Target_Run(model,root,progress_callback=events.append)
    assert result.succeeded and result.plan.compile_steps==2 and result.plan.total_steps==3
    assert result.completed_steps==3
    assert [event.completed_steps for event in events if event.completed_steps] == sorted(event.completed_steps for event in events if event.completed_steps)
    nothing=runner.Target_Run(model,root)
    assert nothing.succeeded and nothing.plan.total_steps==nothing.completed_steps==0
    (root/'a.c').write_text('changed synthetic input a',encoding='utf8')
    older=(root/'a.c').stat().st_mtime-2
    os.utime(root/'build/a.o',(older,older))
    incremental=runner.Target_Run(model,root)
    assert incremental.succeeded and incremental.plan.compile_steps==1
    assert incremental.plan.total_steps==incremental.completed_steps==2
    # Creating the object is insufficient if a later command in its recipe fails.
    makefile=root/'Makefile'
    makefile.write_text(makefile.read_text(encoding='utf8')+'\t@exit 7\n',encoding='utf8')
    (root/'a.c').write_text('failing synthetic input a',encoding='utf8')
    older=(root/'a.c').stat().st_mtime-2
    os.utime(root/'build/a.o',(older,older))
    failed=runner.Target_Run(model,root)
    assert not failed.succeeded and failed.completed_steps==0


def test_dry_run_failure_stops_before_actual_compile(tmp_path,monkeypatch):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    (tmp_path/'Makefile').write_text('all:\n',encoding='utf8')
    calls=[]
    def process(command,*args,**kwargs):
        calls.append(command)
        return 2,['make: missing prerequisite\n']
    monkeypatch.setattr(BuildRunner,'_Process_Run',staticmethod(process))
    result=BuildRunner(WorkspacePolicy(tmp_path)).Target_Run(ReferenceProject_Create('PlanFailure'),tmp_path)
    assert not result.succeeded and len(calls)==1 and '-n' in calls[0]
    assert result.completed_steps==0 and 'missing prerequisite' in result.output
