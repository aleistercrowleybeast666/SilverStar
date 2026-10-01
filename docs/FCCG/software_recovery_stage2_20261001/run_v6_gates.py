from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,hashlib,json,time,threading
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
stages=[]
lock=threading.Lock()
def run(name,cwd,command,timeout=600):
    print('BEGIN '+name,flush=True)
    start=time.monotonic()
    log=OUT/('v6_'+name+'.log')
    with log.open('wb') as stream:
        try:
            code=subprocess.run(command,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout).returncode
        except subprocess.TimeoutExpired: code='TIMEOUT'
    with lock:
        stages.append(dict(name=name,cwd=str(cwd),command=command,exit_code=code,
                           seconds=time.monotonic()-start,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
        (OUT/'gate_results_v6.json').write_text(json.dumps(stages,indent=2),encoding='utf-8')
    print('END '+name+' '+str(code),flush=True)
    return code
def flight():
    project=OUT/'candidate_a_v6/Flight_Controller'
    source=project/'Modules/Src/telemetry_service.c'
    fixed=source.read_bytes()
    for gate in ['host-tests','architecture-check','power10-check']:
        run('flight_'+gate,project,['mingw32-make',gate])
    run('flight_arm',project,['mingw32-make','-j6','CONFIG=Release','artifact-check'])
    run('flight_static_analysis',project,['mingw32-make','-j6','CONFIG=Release','static-analysis'])
    run('flight_stack',project,['mingw32-make','CONFIG=Release','stack-report'])
def ground():
    for candidate in ['candidate_a_v6','candidate_b_v6']:
        project=OUT/candidate/'Ground_Station'
        run(candidate+'_ground_arm',project,['mingw32-make','-j4','CONFIG=Release','all'])
        for gate in ['architecture-check','power10-check','host-tests','artifact-check','static-analysis']:
            run(candidate+'_ground_'+gate,project,['mingw32-make','CONFIG=Release',gate])
for name in ['gcc','arm-none-eabi-gcc','mingw32-make']:
    run('version_'+name,ROOT,[name,'--version'],30)
with ThreadPoolExecutor(max_workers=2) as pool:
    jobs=[pool.submit(flight),pool.submit(ground)]
    for job in jobs: job.result()
artifacts={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in OUT.rglob('*') if p.is_file() and p.suffix in ['.elf','.bin','.hex','.map','.ssproject','.ssdecoder']}
(OUT/'artifacts_v6.json').write_text(json.dumps(artifacts,indent=2),encoding='utf-8')
print('COMPLETE',flush=True)


