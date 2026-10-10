from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,os,sys
task=Path(__file__).parent;kind=sys.argv[1];target=sys.argv[2];label=sys.argv[3]
d=json.loads((task/'sr-legacy-generated.json').read_text());row=next(r for r in d['projects'] if r['kind']==kind);assert target in row['targets'],(target,row['targets'])
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','');env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
command=['D:/msys64/ucrt64/bin/mingw32-make.exe','-j2',target,'PYTHON=D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe']
record={'command':command,'cwd':row['root'],'target':target,'kind':kind,'source_commit':d['source_commit'],'makefile_sha256':row['makefile_sha256'],
 'started_utc':datetime.now(timezone.utc).isoformat(),'scope':'Exactly emitted Make target on fresh normal reference output, no patched gate/firmware or hardware'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 try:r=subprocess.run(command,cwd=row['root'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900);record['exit']=r.returncode
 except subprocess.TimeoutExpired:record['exit']='TIMEOUT';raise
 finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,record['exit']);print((task/(label+'.log')).read_text(encoding='utf8')[-2200:])
