from pathlib import Path
import sys,os,subprocess,json,hashlib
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
phase=sys.argv[1]
assert phase in ['pre','final','final2']
p=repo/('.work/combo_'+phase+'/Flight_Controller')
out=repo/('.work/combo_'+phase+'_evidence')
if p.parent.exists() or out.exists(): raise FileExistsError('Refuse existing output')
service=FccgService(repo/'apps/FCCG')
source_fixture=repo/'apps/FCCG/tests/fixtures/radio_handshake.ssproject'
fixture=json.loads(source_fixture.read_text(encoding='utf8'))
fixture['project']['name']='SS_RfM9n_1'
p.parent.mkdir(parents=True,exist_ok=False)
candidate_fixture=p.parent/'RfM9n.ssproject'
candidate_fixture.write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf8')
model=service.Project_Open(candidate_fixture)
service.Project_Save(model,p,confirm_dangerous=True)
print('generated '+str(p),flush=True)
out.mkdir(parents=True,exist_ok=False)
env=dict(os.environ,PATH=r'D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONPATH=str(repo/'apps/FCCG/src')+';'+str(repo/'apps/FCCG'),SILVERSTAR_RADIO_GENERATED_PROJECT=str(p))
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
plan=[('Release-build','Release',['all']),('artifact','Release',['artifact-check']),('resources','Release',['stack-report','memory-report'])]
if phase!='pre': plan=[('Release-build','Release',['all']),('Host','Release',['host-tests']),('architecture','Release',['architecture-check']),('power10','Release',['power10-check']),('analyzer','Release',['static-analysis']),('artifact','Release',['artifact-check']),('resources','Release',['stack-report','memory-report']),('Debug-build','Debug',['all']),('Debug-artifact','Debug',['artifact-check','stack-report','memory-report'])]
results=[]
def run(name,cmd,cwd):
 log=out/(name+'.log')
 with log.open('w',encoding='utf8') as f: r=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
 item={'name':name,'command':cmd,'cwd':str(cwd),'exit':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 results.append(item); (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
 print(json.dumps(item),flush=True)
 print(log.read_text(encoding='utf8',errors='replace')[-2500:],flush=True)
for name,config,targets in plan: run(name,[make,'-j2','SHELL=cmd.exe','CONFIG='+config,*targets],p)
if phase!='pre':
 run('Radio-generated-Host',[sys.executable,'-m','pytest','apps/FCCG/tests/test_radio_handshake_generated_host.py','-q'],repo)
print('complete',flush=True)
