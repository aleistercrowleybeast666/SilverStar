from pathlib import Path
import sys, os, subprocess, json, hashlib
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
out=repo/'.work/imu_counter_evidence2'
root=repo/'.work/imu_counter'
if out.exists() or root.exists(): raise FileExistsError('Preserve previous evidence')
out.mkdir(parents=True)
source=Path(r'D:\python_software\SilverStar\.work\RadioRuntimeFaultHotfix_20261002\.work\post\Flight_Controller\SilverStar.ssproject')
if not source.exists():
    found=list(source.parent.rglob('*.ssproject'))
    raise FileNotFoundError(str(source)+' candidates '+str(found))
config=json.loads(source.read_text(encoding='utf8'))
config['project']['name']='SS_ImuStartupCounter_20261002'
inp=out/'Input.ssproject';inp.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
service=FccgService(repo/'apps/FCCG')
model=service.Project_Open(inp)
gen=TargetGeneration_Apply(model,service.catalog,WorkspacePolicy(repo/'apps/FCCG'),root,TargetScope.ALL,confirm_dangerous=True)
project=root/'Flight_Controller'
gcc=r'D:\msys64\ucrt64\bin\gcc.exe'
command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-include',str(project/'Generated/Inc/project_flight_config.h')]
for path in project.rglob('Inc'):
    if 'build' not in path.relative_to(project).parts:command+=['-I',str(path)]
command+=['-I',str(project/'Tests/Host'),'-I',str(project/'System/User'),'-I',str(project)]
sources=['Tests/Host/host_platform_mock.c','Common/Src/common_ringbuf.c','Common/Src/silverstar_assert.c','Generated/Src/project_resources.c']
command += [str(project/x) for x in sources]+[str(Path(__file__).with_name('test_imu_read_stream.c')),'-lm','-o',str(out/'counter.exe')]
results=[]
for name,cmd in [('compile',command),('old_counter',[str(out/'counter.exe')])]:
    result=subprocess.run(cmd,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace')
    log=out/(name+'.log');log.write_text(result.stdout+result.stderr,encoding='utf8')
    results.append({'name':name,'command':cmd,'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name,result.returncode,result.stdout+result.stderr,flush=True)
    if name=='compile' and result.returncode:break
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
