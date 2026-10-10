"""Record ordinary Host commands without changing their arguments or results."""
from pathlib import Path
import subprocess,os,sys,json,datetime,hashlib,runpy,threading
original_run=subprocess.run
trace=Path(os.environ['CCDI_COMMAND_TRACE'])
lock=threading.Lock()
def hashes(args):
    result={}
    if isinstance(args,(list,tuple)):
        for value in args:
            if isinstance(value,(str,os.PathLike)):
                path=Path(value)
                try:
                    if path.is_file():result[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
                except OSError:pass
    return result
def recorded_run(*args,**kwargs):
    command=args[0] if args else kwargs.get('args')
    record={'command':[str(v) for v in command] if isinstance(command,(list,tuple)) else str(command),
        'cwd':str(kwargs.get('cwd') or Path.cwd()),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'input_argument_files':hashes(command)}
    try:
        result=original_run(*args,**kwargs)
        def decoded(value):return value.decode('utf-8','replace') if isinstance(value,bytes) else value
        record.update(exit=result.returncode,stdout=decoded(result.stdout),stderr=decoded(result.stderr),output_argument_files=hashes(command))
        return result
    except BaseException as error:
        record['exception']=repr(error)
        raise
    finally:
        record['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with lock:
            with trace.open('a',encoding='utf-8') as stream:stream.write(json.dumps(record)+'\n')
subprocess.run=recorded_run
runner=Path('apps/SCG/docs/evidence/native_classic_cdc_runtime_20261010/runners/ccdi_run.py')
sys.argv[0]=str(runner)
runpy.run_path(str(runner),run_name='__main__')
