from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
workspace=Path(__file__).parent
shutil.copy2(workspace/'test_m0_release_gui.py',repo/'apps/GSHC/tests/test_navigation_gui.py')
p=repo/'apps/GSHC/tests/test_calibration_capability.py';s=p.read_text(encoding='utf8');s=s.replace('assert diagnostics.gsp_air_tx_requests == 3','assert diagnostics.gsp_air_tx_requests == 2');p.write_text(s,encoding='utf8')
root=repo/'.work/m0_final';out=repo/'.work/m0_final_evidence';review=repo/'.work/m0_review'
for path in (root,out,review):
 if path.exists():raise FileExistsError(path)
out.mkdir(parents=True);review.mkdir()
git=['git','-c','core.longpaths=true','-c','safe.directory='+repo.as_posix(),'-C',str(repo)]
files=['apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Modules/Src/telemetry_service.c','apps/GSHC/app.py','apps/GSHC/ui/main_window.py']
(review/'minimal_production.diff').write_text(subprocess.check_output(git+['diff','--',*files],text=True,encoding='utf8'),encoding='utf8')
for f in files:shutil.copy2(repo/f,review/Path(f).name)
(review/'README.md').write_text('Production only3 owners: telemetry_service.c removes NAV radio publishing/subscription state; app.py removes automatic/explicit live subscribe and the extra NAV invalidation/display wording; main_window.py removes two live NAV panels. Internal algorithms, health/logging, preparation/generation safety, M0 layouts, latest RF single-owner/handshake/GNSS/JY901B drivers and board START gates unchanged. state_model.py already uses authoritative M0 board readiness, so it needs no change. Decode compatibility modules retained for old logs. Old source counter checkpoint9931b397de9b7ce0d58f3a743d0d3ea5460e5b1d. No local history comparison beyond task-owned base/fix diff; parent owns GitHub history analysis.\n',encoding='utf8')
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
baseline=json.loads((repo/'.work/fs_counter_evidence/Input.ssproject').read_text(encoding='utf8'))
baseline['project']['name']='SS_M0FlightStateRepair_20261002'
inp=out/'Input.ssproject';inp.write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
TargetGeneration_Apply(service.Project_Open(inp),service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
project=root/'Flight_Controller'
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG/tests')+';'+str(repo/'apps/FCCG')+';'+str(repo/'apps/GSHC')+';'+str(repo/'apps/GSHC/tests'),QT_QPA_PLATFORM='windows',SILVERSTAR_RADIO_GENERATED_PROJECT=str(project),SILVERSTAR_RADIO_GROUND_PROJECT=str(root/'Ground_Station'))
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe';records=[]
def run(name,command,cwd):
 log=out/(name+'.log');started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with log.open('w',encoding='utf8') as file:result=subprocess.run(command,cwd=cwd,env=env,stdout=file,stderr=subprocess.STDOUT)
 record={'name':name,'command':command,'cwd':str(cwd),'exit':result.returncode,'started':started,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 records.append(record);(out/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
 print(json.dumps(record),flush=True);print(log.read_text(encoding='utf8',errors='replace')[-1400:],flush=True)
old=json.loads((repo/'.work/fs_counter_evidence/results_v4.json').read_text(encoding='utf8'))
fixture=repo/'apps/FCCG/tests/fixtures/flight_state_scheduler_host.c'
command=[str(fixture) if x.endswith('flight_state_scheduler_host_v4.c') else x for x in old[0]['command']]
command[-1]=str(out/'old_m0_counter.exe')
run('compile_old_m0_counter',command,repo/'.work/fs_counter/Flight_Controller')
if records[-1]['exit']==0:run('old_m0_counter',[command[-1],'contended'],repo/'.work/fs_counter/Flight_Controller')
command=[x.replace(str(repo/'.work/fs_counter/Flight_Controller'),str(project)) for x in command];command[-1]=str(out/'m0_counter.exe')
run('compile_m0_counter',command,project)
if records[-1]['exit']==0:
 for scenario in ['contended','no_navigation','unavailable','no_imu','recovery','outside_mission']:run('counter_'+scenario,[command[-1],scenario],project)
tests=['apps/FCCG/tests/test_flight_state_scheduler_generated_host.py','apps/FCCG/tests/test_radio_handshake_generated_host.py','apps/FCCG/tests/test_radio_duplex_generated_host.py']
run('FCCG_targeted',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/m0_fccg_pytest'),*tests],repo)
run('GSHC_all',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/m0_gshc_pytest'),'apps/GSHC/tests'],repo)
for name,targets in [('Release',['all']),('Host',['host-tests']),('architecture',['architecture-check']),('PoT',['power10-check']),('analyzer',['static-analysis']),('artifact',['artifact-check']),('resources',['stack-report','memory-report'])]:
 run(name,[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),*targets],project)
failed=[r for r in records if r['exit'] and r['name']!='old_m0_counter']
print('GATES_FAILED',json.dumps(failed),flush=True)
sys.exit(bool(failed))
