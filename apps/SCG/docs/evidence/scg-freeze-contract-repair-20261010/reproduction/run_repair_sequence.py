from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,os
task=Path(__file__).parent
python=r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe'
system_python=r'C:\Users\chdxm\AppData\Local\Programs\Python\Python314\python.exe'
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8')
jobs=[
 ('backend',[python,'-B','run_scg_repair_group.py','backend','srb01']),
 ('gui_native',[python,'-B','run_scg_repair_group.py','gui_native','srgn01']),
 ('uart',[python,'-B','run_scg_repair_group.py','uart','sru01']),
 ('flight',[python,'-B','run_scg_repair_group.py','flight','srf01']),
 ('usb_gui',[python,'-B','run_repair_usb_gui.py','srgui01','all']),
 ('usb_async',[python,'-B','run_repair_async.py','sra01']),
 ('native_gates',[python,'-B','run_usb_candidate_gates.py','srng01','srgui01']),
 ('startup',[system_python,'-B','repair_scg_startup_check.py']),
 ('launcher',[system_python,'-B','repair_scg_launcher.py']),
 ('generate_legacy',[python,'-B','generate_scg_repair_legacy.py']),
]
for kind in ('GroundUART','Flight'):
 for target in ('power10-check','architecture-check','host-tests','all','static-analysis','artifact-check'):
  label='srlegacy-'+kind+'-'+target
  jobs.append((label,[python,'-B','run_scg_repair_legacy_gate.py',kind,target,label]))
records=[]
for name,command in jobs:
 record={'name':name,'command':command,'started_utc':datetime.now(timezone.utc).isoformat()};records.append(record)
 (task/'sr-sequence.json').write_text(json.dumps(records,indent=2));print('START',name,flush=True)
 with (task/('sr-sequence-'+name+'.log')).open('w',encoding='utf8') as log:
  try:result=subprocess.run(command,cwd=task,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1900);record['wrapper_exit']=result.returncode
  except subprocess.TimeoutExpired:record['wrapper_exit']='TIMEOUT'
 record['finished_utc']=datetime.now(timezone.utc).isoformat()
 (task/'sr-sequence.json').write_text(json.dumps(records,indent=2));print('END',name,record['wrapper_exit'],flush=True)
 # Individual command receipts/JUnit are authoritative: wrappers which log
 # ordinary failures may themselves finish successfully. Never infer PASS here.
