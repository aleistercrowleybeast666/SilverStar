from pathlib import Path
import sys, os, subprocess, json, hashlib, shutil, datetime
sys.dont_write_bytecode=True

repo=Path(r'D:\python_software\SilverStar\.work\FieldIntegration_20261002')
root=repo/'.work/field_candidate'
out=repo/'.work/field_evidence'
if root.exists() or out.exists(): raise FileExistsError('Refuse existing generation/evidence')
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
service=FccgService(repo/'apps/FCCG')
root.mkdir(parents=True);out.mkdir()
config=json.loads((repo/'apps/FCCG/tests/fixtures/radio_handshake.ssproject').read_text(encoding='utf8'))
assert config['mode_parameters']['deployment']['Delay']['delay']==10.0
assert config['components']['strategies']['estimator']=='silverstar.algorithm.estimator.kf6'
assert config['ground_target']['mcu']=='silverstar.mcu.stm32f103c8t6'
assert config['ground_target']['module_variant']=='e28_2g4m12sx'
config['project']['name']='SS_FieldIntegration_20261002'
input_file=out/'FieldInput.ssproject'
input_file.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
model=service.Project_Open(input_file)
generated=TargetGeneration_Apply(model,service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
assert set(generated.targets)=={'Flight_Controller','Ground_Station'}
shutil.copy2(Path(__file__).with_name('field_rf_precondition.json'),out/'rf_precondition.json')
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG/tests')+';'+str(repo/'apps/FCCG'))
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
results=[]
def run(name,command,cwd,environment=env):
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    log=out/(name+'.log')
    with log.open('w',encoding='utf8') as f:
        result=subprocess.run(command,cwd=cwd,env=environment,stdout=f,stderr=subprocess.STDOUT)
    item={'name':name,'command':command,'cwd':str(cwd),'exit':result.returncode,'log':str(log),'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    results.append(item);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
    print(json.dumps(item),flush=True)
    print(log.read_text(encoding='utf8',errors='replace')[-1100:],flush=True)

print('fresh paired generation '+str(root),flush=True)
for target in ['Ground_Station','Flight_Controller']:
    plan=[('Release',['all']),('Host',['host-tests']),('architecture',['architecture-check']),('PoT',['power10-check']),('analyzer',['static-analysis']),('artifact',['artifact-check'])]
    if target=='Flight_Controller':plan.append(('resources',['stack-report','memory-report']))
    for name,targets in plan:
        run(target+'_'+name,[make,'-j2','SHELL=cmd.exe','CONFIG=Release','PYTHON='+sys.executable.replace('\\','/'),*targets],root/target)

radio_env=dict(env,SILVERSTAR_RADIO_GENERATED_PROJECT=str(root/'Flight_Controller'),SILVERSTAR_RADIO_GROUND_PROJECT=str(root/'Ground_Station'))
run('paired_radio_tests',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/field_radio_pytest'),
    'apps/FCCG/tests/test_radio_handshake_generated_host.py','apps/FCCG/tests/test_radio_duplex_generated_host.py',
    'apps/FCCG/tests/test_sx1281_contract_host.py','apps/FCCG/tests/test_ground_generated_gates.py',
    'apps/FCCG/tests/test_f103_ground_reference.py','apps/FCCG/tests/test_ground_bridge_bounds.py'],repo,radio_env)
gui_env=dict(env,QT_QPA_PLATFORM='offscreen',PYTHONPATH=str(repo/'apps/GSHC'))
run('GSHC',[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work/field_gui_pytest'),
    'tests/test_navigation_readiness.py','tests/test_start_ack_state.py','tests/test_navigation_gui.py',
    'tests/test_sensor_snapshot.py','tests/test_calibration_capability.py'],repo/'apps/GSHC',gui_env)
if any(item['exit'] for item in results):sys.exit(1)
