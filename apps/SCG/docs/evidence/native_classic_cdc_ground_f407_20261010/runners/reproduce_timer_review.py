from pathlib import Path
import shutil,subprocess,json,hashlib,sys
root=Path('D:/python_software/SilverStar/.work/ccdi')
sys.path.insert(0,str(root/'apps/SCG/src'))
from silverstar_fccg.generator.native_clock_tim import NativeClockTimPort_Render
origin=Path('C:/Users/chdxm/Documents/Codex/2026-10-09/task-2/runtime-179-533-review/timer-normal-model')
dest=Path(__file__).resolve().parent/(sys.argv[1] if len(sys.argv)>1 else 'timer-review-replay')
dest.mkdir(exist_ok=True)
results=[]
for label in ('original','fixed'):
    folder=dest/label;folder.mkdir(exist_ok=True)
    for p in origin.iterdir():
        if p.suffix in ('.h','.c'):shutil.copyfile(p,folder/p.name)
    if label=='fixed':
        (folder/'native_clock_port.c').write_bytes(NativeClockTimPort_Render())
        p=folder/'normal_phase.c';s=p.read_text().replace('assert(first==NativeClockResult_UnstableSnapshot);','assert(first==NativeClockResult_Ok);').replace('assert(later==NativeClockResult_UnstableSnapshot);','assert(later==NativeClockResult_Ok);')
        p.write_text(s)
    command=['D:/msys64/ucrt64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wundef','-fanalyzer','-I'+str(folder),
        str(folder/'native_clock.c'),str(folder/'native_clock_port.c'),str(folder/'normal_phase.c'),'-o',str(folder/'normal_phase.exe')]
    env=__import__('os').environ.copy();env['PATH']='D:/msys64/ucrt64/bin;'+env.get('PATH','')
    compiled=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
    record={'label':label,'compile':command,'compile_exit':compiled.returncode,'compile_stdout':compiled.stdout,'compile_stderr':compiled.stderr}
    if compiled.returncode==0:
        run=subprocess.run([str(folder/'normal_phase.exe')],env=env,capture_output=True,text=True,timeout=20)
        record.update(run=[str(folder/'normal_phase.exe')],run_exit=run.returncode,stdout=run.stdout,stderr=run.stderr)
    record['sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    results.append(record)
(dest/'evidence.json').write_text(json.dumps({'scope':'Replay provided independent ordinary phase model. Only post-fix port and expected success assertions differ. No measured MCU timing or USB execution.', 'results':results},indent=2))
for record in results:print(record['label'],record['compile_exit'],record.get('run_exit'),record.get('stdout',''))
assert all(r['compile_exit']==0 and r.get('run_exit')==0 for r in results)
