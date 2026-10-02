from pathlib import Path
import sys,os,subprocess,json,hashlib
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'apps/FCCG/tools'))
from validate_joint_navigation import Project_Generate
if len(sys.argv)!=2: raise SystemExit("Supply one fresh candidate suffix")
variant=sys.argv[1]
if not variant or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in variant): raise ValueError("Invalid suffix")
p=repo/('apps/FCCG/tests/artifacts/m9_candidate_'+variant)
if p.exists(): raise FileExistsError(p)
Project_Generate('kf6_flight',p)
print('candidate generated',flush=True)
out=repo/('.work/m9_candidate_evidence' + ('_'+variant if variant!='v1' else ''))
out.mkdir(parents=True,exist_ok=False)
env=dict(os.environ,PATH=r'D:\Arm GNU Toolchain\14.3 rel1\bin;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
make=r'D:\msys64\ucrt64\bin\mingw32-make.exe'
plan=[('Release-build','Release',['all']),('Host','Release',['host-tests']),('architecture','Release',['architecture-check']),('power10','Release',['power10-check']),('analyzer','Release',['static-analysis']),('artifact','Release',['artifact-check']),('resources','Release',['stack-report','memory-report']),('Debug-build','Debug',['all']),('Debug-artifact','Debug',['artifact-check','stack-report','memory-report'])]
results=[]
for name,config,targets in plan:
    cmd=[make,'-j2','SHELL=cmd.exe','CONFIG='+config,*targets]
    log=out/(name+'.log')
    with log.open('w',encoding='utf-8') as f: r=subprocess.run(cmd,cwd=p,env=env,stdout=f,stderr=subprocess.STDOUT)
    result={'name':name,'command':cmd,'exit':r.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    results.append(result)
    (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    if r.returncode: print(log.read_text(encoding='utf-8',errors='replace')[-4500:],flush=True)
print('gates complete',flush=True)
raise SystemExit(int(any(r['exit'] for r in results)))
