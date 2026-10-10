from pathlib import Path
from datetime import datetime,timezone
import os,json,subprocess,hashlib

task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
env=os.environ.copy()
for key in tuple(env):
    if key.startswith('SILVERSTAR_NATIVE_') or key.startswith('SILVERSTAR_C071_') or key.startswith('SILVERSTAR_USB_'):
        env.pop(key)
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',
           PYTHONPATH=str(repo/'apps/SCG/src')+';'+str(repo/'apps/SCG/tests'))
command=[r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe','-B',str(task/'backend_pytest.py'),
         str(task/'test_existing_usb_user_entry.py'),'-p','no:cacheprovider',
         '--basetemp=C:/Users/chdxm/AppData/Local/Temp/ue01','-q']
record={'command':command,'cwd':str(repo),'started_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        'dirty':subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True),
        'test_sha256':hashlib.sha256((task/'test_existing_usb_user_entry.py').read_bytes()).hexdigest(),
        'scope':'Ordinary new project default plus existing USB combo/import directory/save/reload/generate; no private model or admission environment'}
with (task/'ue01.log').open('w',encoding='utf8') as log:
    run=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
record.update(exit=run.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/'ue01-command.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(record,indent=2));print((task/'ue01.log').read_text())
