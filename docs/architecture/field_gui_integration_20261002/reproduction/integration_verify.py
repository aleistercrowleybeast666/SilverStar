from pathlib import Path
import os, sys, json, subprocess, hashlib, datetime, traceback
from dataclasses import replace

repo = Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out = repo / 'docs/architecture/field_gui_integration_20261002'
if len(sys.argv)>2: out=out/sys.argv[2]
out.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True
env = dict(os.environ, PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;' + os.environ['PATH'], PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8', QT_QPA_PLATFORM='windows')
results = []
def run(name, command, cwd=repo, extra=None):
    command=list(command)
    for index,argument in enumerate(command):
        if argument.startswith('--basetemp='):
            requested=Path(argument.split('=',1)[1])
            if not requested.is_absolute(): requested=cwd/requested
            requested.parent.mkdir(parents=True,exist_ok=True)
            command[index]='--basetemp='+str(requested)
    command=[argument for argument in command if argument not in ('-p','no:cacheprovider')]
    active = dict(env)
    if extra: active.update(extra)
    log = out / (name + '.log')
    print('START ' + name, flush=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with log.open('w', encoding='utf-8') as stream:
        p = subprocess.run(command, cwd=cwd, env=active, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
    record = dict(name=name, command=command, cwd=str(cwd), exit=p.returncode, started=started, finished=datetime.datetime.now(datetime.timezone.utc).isoformat(), log=log.name, sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    results.append(record)
    (out / ('results_' + sys.argv[1] + '.json')).write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print('END ' + name + ' exit=' + str(p.returncode), flush=True)
    print(log.read_text(encoding='utf-8', errors='replace')[-600:], flush=True)
    return p.returncode

if sys.argv[1] in ('tests','scg'):
    fccg = ['test_field_blockers.py','test_ground_board_recovery.py','test_release_011_gui.py','test_gui_workflow_20260930.py','test_f103_ground_reference.py','test_ground_pc_uart_dma.py','test_ground_bridge_bounds.py','test_ground_generated_gates.py']
    run('SCG_regression', [sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp=apps/FCCG/.work/qall',*[f'apps/FCCG/tests/{p}' for p in fccg], 'tests/integration/test_monorepo_baseline.py'], extra={'PYTHONPATH':str(repo/'apps/FCCG/src')})
    if sys.argv[1]=='scg':sys.exit(results[-1]['exit'])
    run('Auto_memory_policy', [sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp=apps/FCCG/.work/integration_memory_pytest','apps/FCCG/tests/test_auto_memory_layout.py','-k','old_configuration or saved_layout_eide or gui_selection or f413_alias or generated_audit_loader'], extra={'PYTHONPATH':str(repo/'apps/FCCG/src')})
    run('FLP_header_regression',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp=.work/integration_pytest','tests/test_header_field_blockers.py','tests/test_gui_release_identity.py'], cwd=repo/'apps/FLP',extra={'PYTHONPATH':str(repo/'apps/FLP/src')})
    run('GSHC_optional_start_and_layout',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp=.work/integration_pytest','tests/test_navigation_readiness.py','tests/test_start_ack_state.py','tests/test_navigation_gui.py','tests/test_sensor_snapshot.py','tests/test_calibration_capability.py','tests/test_release_layout.py'],cwd=repo/'apps/GSHC',extra={'PYTHONPATH':str(repo/'apps/GSHC')})
elif sys.argv[1] == 'build':
    sys.path.insert(0, str(repo/'apps/FCCG/src'))
    os.environ['QT_QPA_PLATFORM']='windows'
    from PySide6.QtWidgets import QApplication
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.ui.main_window import MainWindow
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    app=QApplication([])
    w=MainWindow(SettingsStore(repo/'apps/FCCG/.work/integration_build/settings.ini'),service=FccgService(repo/'apps/FCCG'))
    errors=[];w._Error_Show=lambda e:errors.append(str(e))
    projects={}
    summary={'source_commit':subprocess.check_output(['git','-c',f'safe.directory={repo.as_posix()}','rev-parse','HEAD'],cwd=repo,text=True).strip(),'projects':{},'gui_errors':errors}
    field_input=repo/'docs/FCCG/FIELD_INTEGRATION_20261002/field_candidate_SilverStar.ssproject'
    w._Project_Open(field_input)
    assert not errors, errors
    existing=w._model
    assert existing.build.memory_layout=='legacy',existing.build.memory_layout
    legacy_root=repo/'.work/field_gui_existing_legacy'
    assert not legacy_root.exists()
    w._service.ProjectRoot_Save(existing,legacy_root,create_new=True)
    w._Project_Open(legacy_root)
    assert w._model.Dictionary_Get()==existing.Dictionary_Get()
    generation=TargetGeneration_Apply(w._model,w._service.catalog,WorkspacePolicy(legacy_root),legacy_root,TargetScope.ALL,confirm_dangerous=True)
    projects['existing_legacy']=legacy_root
    summary['projects']['existing_legacy']={'memory_layout':w._model.build.memory_layout,'save_reopen_equal':True,'ground_target_equal':w._model.ground_target==existing.ground_target,'targets':generation.targets,'project_root':str(legacy_root),'input_sha256':hashlib.sha256(field_input.read_bytes()).hexdigest()}
    w._model=w._service.ProjectDraft_Create('FieldGui_NewAuto')
    w._Project_Refresh()
    assert w._model.build.memory_layout=='auto'
    w._BoardSelection_Change('silverstar.board.silverstar_0_5')
    w._GroundBoard_Change('silverstar.board.ground_station_0_5')
    w._GroundTarget_Change('enabled',True)
    w._GroundTarget_Change('radio_plugin','silverstar.device.telemetry.sx1281')
    w._GroundTarget_Change('pc_interface','uart')
    new=w._model
    auto_root=repo/'.work/field_gui_new_auto'
    assert not auto_root.exists()
    w._service.ProjectRoot_Save(new,auto_root,create_new=True)
    w._Project_Open(auto_root)
    assert w._model.Dictionary_Get()==new.Dictionary_Get()
    generation=TargetGeneration_Apply(w._model,w._service.catalog,WorkspacePolicy(auto_root),auto_root,TargetScope.ALL,confirm_dangerous=True)
    projects['new_auto']=auto_root
    summary['projects']['new_auto']={'memory_layout':w._model.build.memory_layout,'save_reopen_equal':True,'targets':generation.targets,'project_root':str(auto_root),'module':new.ground_target.module_variant,'pc_resource':new.ground_target.pc_resource}
    assert not errors,errors
    w.close()
    (out/'generation_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    frozen=Path(r'D:\python_software\SilverStar\.work\FieldIntegration_20261002\.work\FieldFreeze_20261002')
    selected=lambda p:p.suffix.lower() in ('.c','.h','.s','.ld','.mk','.py','.ps1') or p.name in ('Makefile','makefile')
    def source_map(root):
        return {str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and selected(p) and not any(part in ('Build','build','__pycache__') for part in p.relative_to(root).parts)}
    comparisons={}
    from zipfile import ZipFile
    archive=frozen/'SS_FieldIntegration_20261002_SourceFirmware.zip'
    freeze_manifest=json.loads((frozen/'freeze_manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==freeze_manifest['zip_sha256']
    archive_file=ZipFile(archive)
    for name,project in projects.items():
        comparisons[name]={}
        for target in ('Flight_Controller','Ground_Station'):
            prefix='Generated/'+target+'/'
            before={n[len(prefix):]:hashlib.sha256(archive_file.read(n)).hexdigest() for n in archive_file.namelist() if n.startswith(prefix) and selected(Path(n)) and not any(part in ('Build','build','__pycache__') for part in Path(n[len(prefix):]).parts)}
            assert before,'Frozen archive has no generated sources'
            after=source_map(project/target)
            changes=[{'path':p,'frozen_sha256':before.get(p),'new_sha256':after.get(p),'change':'added' if p not in before else 'removed' if p not in after else 'changed'} for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
            comparisons[name][target]={'frozen_source_count':len(before),'new_source_count':len(after),'equal_count':sum(before.get(p)==h for p,h in after.items()),'differences':changes}
    (out/'source_vs_frozen.json').write_text(json.dumps(comparisons,indent=2)+'\n',encoding='utf-8')
    make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
    for name,project in projects.items():
        for target in ('Ground_Station','Flight_Controller'):
            gates=[('Release','all'),('Host','host-tests'),('architecture','architecture-check'),('PoT','power10-check'),('analyzer','static-analysis'),('artifact','artifact-check')]
            for label,gate in gates:
                run(name+'_'+target+'_'+label,[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),gate],cwd=project/target)
            if target=='Flight_Controller':
                run(name+'_'+target+'_resources',[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),'stack-report','memory-report'],cwd=project/target)
        summary['projects'][name]['artifacts']={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*.elf')}
        (out/'generation_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    paired_env={'PYTHONPATH':str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG/tests')+';'+str(repo/'apps/FCCG'),'SILVERSTAR_RADIO_GENERATED_PROJECT':str(legacy_root/'Flight_Controller'),'SILVERSTAR_RADIO_GROUND_PROJECT':str(legacy_root/'Ground_Station')}
    run('existing_legacy_paired_RF',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp=apps/FCCG/.work/integration_radio_pytest','apps/FCCG/tests/test_radio_handshake_generated_host.py','apps/FCCG/tests/test_radio_duplex_generated_host.py','apps/FCCG/tests/test_sx1281_contract_host.py'],extra=paired_env)
else:
    raise ValueError(sys.argv[1])
if any(r['exit'] for r in results):sys.exit(1)
