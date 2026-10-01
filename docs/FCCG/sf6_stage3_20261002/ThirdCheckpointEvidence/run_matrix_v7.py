from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess, hashlib, json, time, threading
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
results=[]
lock=threading.Lock()

def run(name,project,arguments,timeout=900):
    command=['mingw32-make',*arguments]
    log=OUT/(name+'.log')
    started=time.monotonic()
    print('BEGIN '+name,flush=True)
    with log.open('wb') as output:
        try: code=subprocess.run(command,cwd=project,stdout=output,stderr=subprocess.STDOUT,timeout=timeout).returncode
        except subprocess.TimeoutExpired: code='TIMEOUT'
    with lock:
        results.append(dict(name=name,command=command,cwd=str(project),exit_code=code,
            seconds=time.monotonic()-started,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        (OUT/'matrix_v7_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('END '+name+' '+str(code),flush=True)

def matrix(algorithm):
    project=OUT/(algorithm+'_v7')/'Flight_Controller'
    for gate,args in [('arm',['-j6','CONFIG=Release','artifact-check']),
                      ('architecture',['architecture-check']),('power10',['power10-check']),
                      ('host',['host-tests']),('analyzer',['-j6','CONFIG=Release','static-analysis']),
                      ('resources',['CONFIG=Release','memory-report','stack-report'])]:
        run(algorithm.lower()+'_v7_'+gate,project,args)

with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(matrix,['SF6','KF6','PureINS','ESKF15']))
print('COMPLETE',flush=True)
