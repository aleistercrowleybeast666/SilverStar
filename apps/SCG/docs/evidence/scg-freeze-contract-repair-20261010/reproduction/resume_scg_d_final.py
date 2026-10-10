from pathlib import Path
from datetime import datetime, timezone
import os, sys, json, subprocess, shutil, hashlib, time

TASK=Path(__file__).parent
REPO=TASK/'r'
TEMP=Path('D:/Codex_Work/task-temp/scg-final-819eec9')
CODE='819eec98347e96aa6548012be159e6a6c58bd435'
PYTHON=r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe'
MAKE='D:/msys64/ucrt64/bin/mingw32-make.exe'
MIN_FREE=8*1024**3

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a): return subprocess.check_output(['git','-C',str(REPO),*a],text=True).strip()
def now(): return datetime.now(timezone.utc).isoformat()
def room():
 free=shutil.disk_usage('D:/').free
 if free<MIN_FREE: raise RuntimeError('D_DISK_BELOW_8_GIB: '+str(free))
 return free

def environment():
 env=os.environ.copy()
 env.update(TEMP=str(TEMP),TMP=str(TEMP),TMPDIR=str(TEMP),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',GIT_OPTIONAL_LOCKS='0',
  SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='D:/Codex_Work/2026-10-08/task/usb-validation',
  SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
  SILVERSTAR_C071_NATIVE='D:/Codex_Work/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST',
  SILVERSTAR_C071_COMPANION=str(REPO/'apps/SCG/plugins/builtin/silverstar_usb_cdc_stm32c071_mini'),
  SILVERSTAR_C071_SDK_HEADER='C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1/Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h',
  SILVERSTAR_USB_REFRESH_INDEX=str(TASK/'ds-migrated-build-index.jsonl'))
 env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
 return env

FLIGHT=['test_physical_device_platform_identity.py','test_project_catalog_cache.py','test_plugin_security.py','test_internal_platform_refactor.py','test_generator_integration.py','test_round2_targets.py','test_flight_state_scheduler_generated_host.py','test_firmware_identity_gate.py','test_firmware_artifact_protocols.py','test_runtime_safety.py','test_stack_budget.py','test_power_of_ten_checker_paths.py','test_quality_manual_acceptance.py','test_target_quality_checks.py']
ENTRY=['test_physical_device_platform_identity.py','test_internal_platform_refactor.py::test_platform_matching_reports_zero_and_tied_candidates','test_runtime_safety.py::test_runtime_sources_survive_reference_import','test_runtime_safety.py::test_imported_documentation_replay_is_idempotent']

def run(kind,label):
 free=room();assert git('rev-parse','HEAD')==CODE
 assert not git('diff','--name-only'),'Source edits must be reviewed before reuse'
 TEMP.mkdir(parents=True,exist_ok=True)
 env=environment();cwd=REPO
 record={'kind':kind,'label':label,'source_commit':CODE,'scg_tree':git('rev-parse','HEAD:apps/SCG'),'source_status':git('status','--porcelain'),
  'started_utc':now(),'disk_free_before':free,'process_TEMP':str(TEMP),
  'scope':'Migrated final software verification, serial jobs, D outputs only; no hardware, gate relaxation, safety-review retry or cleanup.'}
 if kind in ('entry','async','flight'):
  paths=ENTRY if kind=='entry' else ['test_usb_gui_async.py'] if kind=='async' else FLIGHT
  command=[PYTHON,'-B',str(TASK/'repair_backend_pytest.py'),*['apps/SCG/tests/'+p for p in paths],'-q','-p','no:cacheprovider','--basetemp='+str(TEMP/label),'--junitxml='+str(TASK/(label+'.xml'))]
  if kind=='entry':command=[PYTHON,'-B','-m','pytest',*['apps/SCG/tests/'+p for p in paths],'-q','-p','no:cacheprovider','--basetemp='+str(TEMP/label),'--junitxml='+str(TASK/(label+'.xml'))]
  record['complete_modules']=['apps/SCG/tests/'+p for p in paths]
  record['test_sha256']={p:sha(REPO/p.split('::')[0]) for p in record['complete_modules']}
  if kind=='async':record['run_context']='Serial after terminated old queues; no other owned compile process active. Original timing thresholds and test body unchanged; verified physical D output locators, immutable model/receipt/ELF hashes preserved in ds-locator-migration.json.'
 else:
  cwd=Path('D:/Codex_Work/task-temp/scg-repair-legacy-a5joy2gh/Flight_Controller')
  assert cwd.is_dir()
  assert sha(cwd/'Makefile')==next(p['makefile_sha256'] for p in json.loads((TASK/'sr-legacy-generated.json').read_text())['projects'] if p['kind']=='Flight')
  record['makefile_sha256']=sha(cwd/'Makefile')
  target='static-analysis' if kind=='analyzer' else 'artifact-check'
  command=[MAKE,'-j1',*(['-B'] if kind=='analyzer' else []),target,'PYTHON='+PYTHON.replace('\\','/')]
  record['target']=target
  record['scope']+=' Existing exact generated project reused; analyzer -B forces real complete recompile without copying vendor or cleaning. Artifact gate is the original emitted target.'
  record['normal_elf_before']={p.relative_to(cwd).as_posix():sha(p) for p in cwd.glob('build/FCCG/SilverStar_F407/Release/*.elf')}
 record.update(command=command,cwd=str(cwd))
 metadata=TASK/(label+'-command.json');metadata.write_text(json.dumps(record,indent=2))
 print('START',kind,label,free,flush=True)
 with (TASK/(label+'.log')).open('w',encoding='utf8') as log:
  child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
  record['owned_pid']=child.pid;metadata.write_text(json.dumps(record,indent=2))
  deadline=time.monotonic()+1900
  while child.poll() is None:
   if shutil.disk_usage('D:/').free<MIN_FREE or time.monotonic()>deadline:
    reason='D_DISK_BELOW_8_GIB' if shutil.disk_usage('D:/').free<MIN_FREE else 'TIMEOUT'
    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True)
    record['exit']=reason;break
   time.sleep(2)
  else:record['exit']=child.returncode
 record.update(finished_utc=now(),ending_head=git('rev-parse','HEAD'),disk_free_after=shutil.disk_usage('D:/').free,log_sha256=sha(TASK/(label+'.log')))
 if kind in ('analyzer','artifact'):record['elf_after']={p.relative_to(cwd).as_posix():sha(p) for p in cwd.rglob('*.elf')}
 metadata.write_text(json.dumps(record,indent=2))
 print('END',kind,label,record['exit'],record['disk_free_after'],flush=True)
 print((TASK/(label+'.log')).read_text(encoding='utf8')[-4500:],flush=True)
 return record

if __name__ == '__main__':
 jobs=[('entry','ds-entry01'),('async','ds-async01'),('analyzer','ds-Flight-static-analysis'),('artifact','ds-Flight-artifact-check'),('flight','ds-flight01')]
 if len(sys.argv)>1:jobs=[(sys.argv[1],sys.argv[2])]
 records=[]
 for kind,label in jobs:
  record=run(kind,label);records.append(record)
  (TASK/('ds-resume-'+label+'-sequence.json')).write_text(json.dumps(records,indent=2))
  if record['exit']!=0:raise SystemExit(1)
 