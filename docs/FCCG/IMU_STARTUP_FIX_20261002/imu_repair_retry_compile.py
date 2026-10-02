from pathlib import Path
import json,subprocess,sys,hashlib
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
out=repo/'.work/imu_repair_evidence'
old=json.loads((out/'stream_results.json').read_text(encoding='utf8'))
cmd=[x for x in old[0]['command'] if Path(x).name!='host_platform_mock.c']
cmd[-1]=str(out/'stream_v2.exe')
results=[]
for name,command in [('compile_stream_v2',cmd),('fixed_stream_v2',[cmd[-1]])]:
    log=out/(name+'.log')
    if log.exists():raise FileExistsError(log)
    result=subprocess.run(command,cwd=repo/'.work/imu_repair/Flight_Controller',capture_output=True,text=True,encoding='utf8',errors='replace')
    log.write_text(result.stdout+result.stderr,encoding='utf8')
    results.append({'name':name,'command':command,'exit':result.returncode,'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name,result.returncode,(result.stdout+result.stderr)[-5000:],flush=True)
    if name=='compile_stream_v2' and result.returncode:break
(out/'stream_results_v2.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
