from pathlib import Path
from datetime import datetime,timezone
import sys,os,json,subprocess,hashlib
task=Path(__file__).parent;label=sys.argv[1];indexlabel=sys.argv[2]
rows=[json.loads(line) for line in (task/(indexlabel+'-build-index.jsonl')).read_text().splitlines()]
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
python='D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe';records=[]
for row in rows:
    if row.get('result','CompiledCandidate')!='CompiledCandidate':continue
    root=Path(row['output']);family=row['part'];checker='check_c071_candidate.py' if family=='STM32C071FBP6' else 'check_native_ground.py'
    compilation=json.loads((root/'receipt.json').read_text())
    assert compilation['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert compilation['facts']['part']==family
    for mode,command in (
        ('architecture',[python,'Tools/'+checker]),
        ('host',[python,'Tools/'+checker,'host','--host-cc','gcc']),
        ('artifact',[python,'Tools/'+checker,'artifact','--prefix','arm-none-eabi-']),
        ('power10',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','Tools/check_power_of_ten.ps1','-TargetKind','Ground'])):
        record={'part':family,'mode':mode,'cwd':str(root),'command':command,
                'compile_source_commit':compilation['source_commit'],
                'compile_receipt_sha256':hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest(),
                'started_utc':datetime.now(timezone.utc).isoformat()}
        logfile=task/(label+'-'+family+'-'+mode+'.log')
        with logfile.open('w',encoding='utf8') as log:
            result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
        record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),log_sha256=hashlib.sha256(logfile.read_bytes()).hexdigest())
        records.append(record);(task/(label+'-gates.json')).write_text(json.dumps(records,indent=2),encoding='utf8')
        print(family,mode,result.returncode,flush=True)
        if result.returncode:
            print(logfile.read_text(encoding='utf8')[-11000:]);raise SystemExit(result.returncode)
