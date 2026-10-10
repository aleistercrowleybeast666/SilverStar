from pathlib import Path
from datetime import datetime,timezone
import os,sys,subprocess,json,hashlib
task=Path(__file__).parent;root=Path(r'D:\python_software\SilverStar\.work\ccdi')
label=sys.argv[1]
env=os.environ.copy()
env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
    SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
    SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
    SILVERSTAR_NATIVE_BACKEND_ARM='1',SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX=str(task/(label+'-build-index.jsonl')))
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B',str(task/'backend_pytest.py'),*sys.argv[2:],
    '-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,'-q']
changed=subprocess.check_output(['git','-C',str(root),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
record={'command':command,'cwd':str(root),'source_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
    'changed_files_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in changed},
    'started_utc':datetime.now(timezone.utc).isoformat(),
    'scope':'Ordinary valid control, model, clock, no-heap, radio, CPU/IRQ and build regression only; no malformed USB or blocked independent safety review'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
    result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,result.returncode)
print((task/(label+'.log')).read_text(encoding='utf8')[-14000:])
