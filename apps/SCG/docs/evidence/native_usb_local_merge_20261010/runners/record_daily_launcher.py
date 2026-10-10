from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,os
task=Path(__file__).parent;repo=Path(r'D:\python_software\SilverStar')
command=[r'C:\Users\chdxm\AppData\Local\Programs\Python\Python314\python.exe','-B',str(repo/'apps/SCG/SCG.py'),'--version']
env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';r=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=30)
d={'command':command,'cwd':str(repo),'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'recorded_utc':datetime.now(timezone.utc).isoformat(),'scope':'Actual default system Python public launcher version; no writable user state or hardware'}
(task/'daily-scg-launcher.json').write_text(json.dumps(d,indent=2),encoding='utf8')
assert r.returncode==0 and r.stdout.strip()=='0.1.2',d;print(json.dumps(d,indent=2))
