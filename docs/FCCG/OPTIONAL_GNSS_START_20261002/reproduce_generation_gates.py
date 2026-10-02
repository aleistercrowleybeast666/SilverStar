from pathlib import Path
import sys,os,subprocess,json,hashlib
repo=Path(r'D:\python_software\SilverStar\.work\OptionalGnssStartFix_20261002')
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
phase=sys.argv[1]
assert phase in ['counter','final','final2','sf6','eskf15','ins']
p=repo/('.work/'+phase+'/Flight_Controller'); out=repo/('.work/'+phase+'_evidence')
if p.parent.exists() or out.exists():raise FileExistsError('Refuse existing output')
service=FccgService(repo/'apps/FCCG')
fixture=json.loads((repo/'apps/FCCG/tests/fixtures/radio_handshake.ssproject').read_text(encoding='utf8'))
fixture['project']['name']='SS_OptionalGnss_'+phase
if phase in ['sf6','eskf15','ins']:
 fixture['components']['strategies']['estimator']='' if phase=='ins' else 'silverstar.algorithm.estimator.'+phase
p.parent.mkdir(parents=True,exist_ok=False)
cf=p.parent/'OptionalGnss.ssproject'; cf.write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf8')
model=service.Project_Open(cf);service.Project_Save(model,p,confirm_dangerous=True)
print('generated '+str(p),flush=True);out.mkdir()
env=dict(os.environ,PATH=r'D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG'))
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
plan=[('Host',['host-tests'])] if phase=='counter' else [('Release-build',['all']),('Host',['host-tests']),('architecture',['architecture-check']),('power10',['power10-check']),('analyzer',['static-analysis']),('artifact',['artifact-check']),('resources',['stack-report','memory-report'])]
if phase in ['sf6','eskf15','ins']:plan=[('Release-build',['all']),('Host',['host-tests']),('artifact',['artifact-check']),('resources',['stack-report','memory-report'])]
results=[]
for name,targets in plan:
 cmd=[make,'-j2','SHELL=cmd.exe','CONFIG=Release',*targets]
 log=out/(name+'.log')
 with log.open('w',encoding='utf8') as f:r=subprocess.run(cmd,cwd=p,env=env,stdout=f,stderr=subprocess.STDOUT)
 item={'name':name,'command':cmd,'cwd':str(p),'exit':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()};results.append(item)
 (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
 print(json.dumps(item),flush=True);print(log.read_text(encoding='utf8',errors='replace')[-2300:],flush=True)
