from pathlib import Path
import json,subprocess,sys,hashlib
sys.dont_write_bytecode=True
out=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002\.work\imu_counter_evidence2')
prior=json.loads((out/'results.json').read_text(encoding='utf8'))
cmd=prior[0]['command']
project=out.parent/'imu_counter/Flight_Controller'
cmd[-1]=str(out/'counter_v2.exe')
results=[]
for name,command in [('compile_v2',cmd),('old_counter_v2',[cmd[-1]])]:
    log=out/(name+'.log')
    if log.exists():raise FileExistsError(log)
    result=subprocess.run(command,cwd=project,capture_output=True,text=True,encoding='utf8',errors='replace')
    log.write_text(result.stdout+result.stderr,encoding='utf8')
    results.append({'name':name,'command':command,'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name,result.returncode,result.stdout+result.stderr,flush=True)
    if name=='compile_v2' and result.returncode:break
(out/'results_v2.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
