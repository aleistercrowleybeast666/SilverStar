from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib,json,os,subprocess
ROOT=Path('D:/python_software/SilverStar')
OUT=ROOT/'.work/scg_ground_integration_20261009'
TARGETS=Path('C:/Users/chdxm/AppData/Local/Temp/ssgroundint9e')
cases=[(name,TARGETS/name/'Ground_Station') for name in ('f103-usb','f103-uart','f407-usb')]
cases += [('c071-usb',TARGETS/'c071-usb'),('c071-uart',TARGETS/'c071-uart')]
head=subprocess.check_output(['git','-C',str(ROOT/'.work/qint'),'rev-parse','HEAD'],text=True).strip()
environment=os.environ.copy()
environment['PYTHONDONTWRITEBYTECODE']='1'
environment['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+environment['PATH']
def run(case):
 name,directory=case
 command=['D:/msys64/ucrt64/bin/mingw32-make.exe','architecture-check','host-tests','power10-check',
          'PYTHON='+str(ROOT/'apps/FLP/.venv/Scripts/python.exe'),'HOST_CC=D:/msys64/ucrt64/bin/gcc.exe']
 start=datetime.now(timezone.utc).isoformat()
 log=OUT/(name+'-emitted-gates.log')
 with log.open('w',encoding='utf-8') as stream:
  result=subprocess.run(command,cwd=directory,env=environment,stdout=stream,stderr=subprocess.STDOUT)
 text=log.read_text(encoding='utf-8',errors='replace')
 item=dict(case=name,command=command,cwd=str(directory),started_utc=start,
           finished_utc=datetime.now(timezone.utc).isoformat(),exit=result.returncode,
           log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
           critical_contract_not_proven='POWER10_CONTRACT_REVIEW|NOT_PROVEN|' in text)
 print(name,'emitted architecture/Host/PoT exit',result.returncode,'NOT_PROVEN',item['critical_contract_not_proven'],flush=True)
 return item
with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,cases))
(OUT/'emitted-gates.json').write_text(json.dumps(dict(source_commit=head,results=results),indent=2),encoding='utf-8')
raise SystemExit(0 if all(r['exit']==0 and r['critical_contract_not_proven'] for r in results) else 1)
