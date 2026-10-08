from pathlib import Path
import os,sys,json,subprocess,datetime,time,hashlib

repo=Path.cwd();out=Path(__file__).resolve().parent;project=out/'project/Flight_Controller'
make='D:/msys64/ucrt64/bin/mingw32-make.exe'
env=dict(os.environ,PATH=str(repo/'.venv/Scripts')+';D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+os.environ.get('PATH',''))
steps=[('architecture',[make,'architecture-check'],120),('power10',[make,'power10-check'],120),
       ('release',[make,'-j2','all','artifact-check','memory-report','GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin'],900),
       ('stack',[make,'-j2','stack-report','GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin'],180),
       ('analyzer',[make,'-j2','static-analysis','GCC_PATH=D:/Arm GNU Toolchain/14.3 rel1/bin'],900),
       ('host',[make,'host-tests','HOST_CC=D:/msys64/ucrt64/bin/gcc.exe'],900)]
for name,cmd,timeout in steps:
    assert not (out/(name+'_result.json')).exists(),'Preserve existing gate result'
    record={'step':name,'utc_start':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,
            'cwd':str(project),'base_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dirty_patch_sha256':hashlib.sha256((out/'source_diff.patch').read_bytes()).hexdigest(),
            'source_owner_sha256':hashlib.sha256((repo/'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c').read_bytes()).hexdigest(),
            'timeout_s':timeout,'max_make_jobs':2,'hardware':False}
    (out/'active_gate.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('START '+name,flush=True);started=time.monotonic()
    with (out/(name+'.log')).open('xb') as stream:
        try:
            process=subprocess.run(cmd,cwd=project,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            record['exit_code']=process.returncode
        except subprocess.TimeoutExpired:record.update(exit_code=None,timed_out=True)
    record.update(utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_s=time.monotonic()-started,
                  log_sha256=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest())
    (out/(name+'_result.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('END '+name+' exit='+str(record['exit_code']),flush=True)
    if name=='release' and record['exit_code']!=0:
        print('Release failed; remaining dependent checks not executed',flush=True);break
