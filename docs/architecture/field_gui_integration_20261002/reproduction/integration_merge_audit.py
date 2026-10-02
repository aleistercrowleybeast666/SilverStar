from pathlib import Path
import subprocess, json, hashlib
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out=repo/'docs/architecture/field_gui_integration_20261002'
def git(*args):
    return subprocess.check_output(['git','-c',f'safe.directory={repo.as_posix()}','-c','core.longpaths=true',*args],cwd=repo)
gui='d4aa83aae760dfcbf332890a3c9a4c98bdfaa2ee'
field='160cebbd103ade8f6e7a7989cbc32bcbd3d5cd41'
head=git('rev-parse','HEAD').decode().strip()
def production_diff(a,b):return git('diff',a,b,'--','apps','tools','SCG.py','GSHC.py','FLP.py','FCCG.py','silverstar_version.py','freeze_memory_final.py','pyproject.toml')
(out/'field_increment_into_gui.patch').write_bytes(production_diff(gui,head))
(out/'gui_auto_increment_over_field.patch').write_bytes(production_diff(field,head))
prefixes=['apps/FCCG/plugins/builtin/silverstar_device_telemetry_sx1281','apps/FCCG/plugins/builtin/silverstar_device_gnss_neo_m9n','apps/FCCG/plugins/builtin/silverstar_core_ground_0_1_0']
identical={p:not bool(git('diff',field,head,'--',p)) for p in prefixes}
assert all(identical.values()),identical
forbidden={}
for branch in ['feature/barometer-backup-20261002','feature/barometer-integration-20261002','feature/ground-multi-radio-20261002']:
    result=subprocess.run(['git','-c',f'safe.directory={repo.as_posix()}','merge-base','--is-ancestor',branch,head],cwd=repo)
    forbidden[branch]=result.returncode==0
assert not any(forbidden.values()),forbidden
checks={}
for worktree in ['D:/python_software/SilverStar','D:/python_software/SilverStar/.work/FieldIntegration_20261002','D:/python_software/SilverStar/.work/GuiFieldBlockers_20261002']:
    command=['git','-c',f'safe.directory={worktree}','-C',worktree]
    checks[worktree]={'head':subprocess.check_output(command+['rev-parse','HEAD']).decode().strip(),'status_short':subprocess.check_output(command+['status','--short']).decode()}
record={'combined_production_commit':head,'merge_parents':git('show','-s','--format=%P','HEAD').decode().strip().split(),'common_ancestor':git('merge-base',gui,field).decode().strip(),'text_conflicts':[],'automatic_merge_files':['navigation_eskf_backend.c','estimator_task.c','test_estimator_preparation.c','check_firmware_artifact.ps1','generator/render.py','GSHC/ui/main_window.py'],'rf_m9n_ground_payloads_identical_to_frozen_field':identical,'excluded_branch_tip_is_ancestor':forbidden,'protected_worktrees':checks,'version':(repo/'VERSION').read_text().strip()}
(out/'merge_audit.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,indent=2))
