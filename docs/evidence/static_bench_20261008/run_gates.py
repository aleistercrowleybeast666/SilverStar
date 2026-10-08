from pathlib import Path
import os,sys,json,subprocess,datetime,time,hashlib
out=Path(__file__).resolve().parent
repo=out.parents[1]
project=repo/'.work/bench08b_f407/Flight_Controller'
arm=Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
host=Path('D:/msys64/ucrt64/bin')
env=dict(os.environ)
env['PATH']=os.pathsep.join([str(arm),str(host),str(Path(sys.executable).parent),env.get('PATH','')])
env['PYTHONPATH']=str(repo/'apps/SCG/src')
env['PYTHONDONTWRITEBYTECODE']='1'
env['PYTHONIOENCODING']='utf-8'
make=str(host/'mingw32-make.exe')
commands={'architecture':[make,'architecture-check'],'power10':[make,'power10-check'],'release':[make,'-j2','all','artifact-check','stack-report','memory-report','GCC_PATH='+arm.as_posix()],'analyzer':[make,'-j2','static-analysis','GCC_PATH='+arm.as_posix()],'host':[make,'host-tests','HOST_CC='+str(host/'gcc.exe').replace('\\','/')],'versions':[str(arm/'arm-none-eabi-gcc.exe'),'--version']}
for name in sys.argv[1:]:
    log=out/(name+'.log');result=out/(name+'_result.json')
    if log.exists() or result.exists():raise SystemExit('Refuse overwrite gate evidence: '+name)
    args=commands[name]
    rec={'step':name,'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':args,'cwd':str(project),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo).decode().strip(),'tracked_status':subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo).decode(),'compiler_jobs_max':2,'timeout_s':900}
    assert not rec['tracked_status'],'Compile only a committed source snapshot'
    print('START',name,rec['utc_start'],flush=True)
    t=time.monotonic()
    with log.open('xb') as stream:
        try:
            r=subprocess.run(args,cwd=project,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
            rec['exit_code']=r.returncode
        except subprocess.TimeoutExpired:
            rec.update(exit_code=None,error='TIMEOUT; completion NOT PROVEN')
    rec.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=round(time.monotonic()-t,3),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    result.write_text(json.dumps(rec,indent=2),encoding='utf-8')
    print('END',name,rec['exit_code'],rec['elapsed_s'],flush=True)
    print(log.read_text(encoding='utf-8',errors='replace')[-1600:],flush=True)
    if rec['exit_code']!=0:raise SystemExit(rec['exit_code'] or 124)
