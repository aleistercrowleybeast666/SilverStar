from pathlib import Path
from datetime import datetime,timezone
import os,sys,json,subprocess,hashlib
task=Path(__file__).parent;repo=Path(__file__).parent/'r';label=sys.argv[1]
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen',SILVERSTAR_USB_REFRESH_INDEX=str(task/'srgui01-build-index.jsonl'))
command=[r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe','-B',str(task/'repair_backend_pytest.py'),
         'apps/SCG/tests/test_usb_gui_async.py','-q','-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label]
command+=['--junitxml='+str(task/(label+'.xml'))]
record={'command':command,'cwd':str(repo),'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        'dirty_diff':subprocess.check_output(['git','-C',str(repo),'diff','--binary'],text=True),
        'test_sha256':hashlib.sha256((repo/'apps/SCG/tests/test_usb_gui_async.py').read_bytes()).hexdigest(),
        'started_utc':datetime.now(timezone.utc).isoformat(),
        'run_context':sys.argv[2] if len(sys.argv)>2 else 'Original sequence; another owned backend compile sequence active',
        'scope':'Actual completed F103/C071 candidate full audit on worker, one Plan per refresh, live Qt timers, pending/superseded requests, cancellation, owned close/destruction and ordinary late import; original artifacts remain unchanged'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
    run=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
record.update(exit=run.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2),encoding='utf8')
print(label,run.returncode);print((task/(label+'.log')).read_text()[-14000:])
