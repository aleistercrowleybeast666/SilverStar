from pathlib import Path
from datetime import datetime, timezone
import subprocess, json, os

task=Path(__file__).parent
python=r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe'
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
jobs=[('backend','srb02'),('gui_native','srgn03'),('uart','sru02'),('flight','srf02')]
records=[]
for group,label in jobs:
 command=[python,'-B','run_scg_repair_group.py',group,label]
 record={'group':group,'label':label,'command':command,'started_utc':datetime.now(timezone.utc).isoformat()}
 records.append(record)
 (task/'sr-final-groups-sequence.json').write_text(json.dumps(records,indent=2))
 print('START',group,label,flush=True)
 with (task/('sr-final-sequence-'+label+'.log')).open('w',encoding='utf8') as log:
  try:result=subprocess.run(command,cwd=task,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1900);record['wrapper_exit']=result.returncode
  except subprocess.TimeoutExpired:record['wrapper_exit']='TIMEOUT'
 record['finished_utc']=datetime.now(timezone.utc).isoformat()
 (task/'sr-final-groups-sequence.json').write_text(json.dumps(records,indent=2))
 print('END',group,label,record['wrapper_exit'],flush=True)
 if group=='backend':
  # The original two successful private build cases write their exact index.
  source=task/(label+'-private-build-index.jsonl')
  if source.exists():
   (task/'srprivate02-build-index.jsonl').write_bytes(source.read_bytes())
   gate=[python,'-B','run_usb_candidate_gates.py','srpg02','srprivate02']
   with (task/'sr-final-sequence-private-gates.log').open('w',encoding='utf8') as log:
    result=subprocess.run(gate,cwd=task,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
   print('PRIVATE GATES',result.returncode,flush=True)
