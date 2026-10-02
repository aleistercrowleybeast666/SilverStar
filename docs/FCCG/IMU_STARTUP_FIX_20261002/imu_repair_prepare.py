from pathlib import Path
import sys,json,subprocess,os,hashlib,shutil
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
out=repo/'.work/imu_repair_evidence'
root=repo/'.work/imu_repair'
if root.exists() or out.exists():raise FileExistsError('Preserve previous output')
out.mkdir(parents=True)
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
config=json.loads((repo/'.work/imu_counter_evidence2/Input.ssproject').read_text(encoding='utf8'))
config['project']['name']='SS_ImuStartupRepair_20261002'
inp=out/'Input.ssproject';inp.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
gen=TargetGeneration_Apply(service.Project_Open(inp),service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
project=root/'Flight_Controller'
prior=json.loads((repo/'.work/imu_counter_evidence2/results_v2.json').read_text(encoding='utf8'))
command=prior[0]['command']
command=[x.replace(str(repo/'.work/imu_counter/Flight_Controller'),str(project)) for x in command]
fixture=repo/'apps/FCCG/tests/fixtures/jy901b_register_stream_host.c'
shutil.copy2(Path(__file__).with_name('test_imu_read_stream_repaired.c'),fixture)
command=[x for x in command if not x.endswith('Tests/Host/host_platform_mock.c')]
command=[str(fixture) if x.endswith('test_imu_read_stream.c') else x for x in command]
command[-1]=str(out/'stream.exe')
results=[]
for name,cmd in [('compile_stream',command),('fixed_stream',[command[-1]])]:
    result=subprocess.run(cmd,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace')
    log=out/(name+'.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
    results.append({'name':name,'command':cmd,'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name,result.returncode,result.stdout+result.stderr,flush=True)
    if name=='compile_stream' and result.returncode:break
(out/'stream_results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
