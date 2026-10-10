from pathlib import Path
from datetime import datetime, timezone
import subprocess, os, json, sys

task = Path(__file__).parent
repo = task / 'r'
label=sys.argv[1] if len(sys.argv)>1 else 'srentry01'
python = r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe'
command = [python, '-B', '-m', 'pytest',
    'apps/SCG/tests/test_runtime_safety.py::test_runtime_sources_survive_reference_import',
    'apps/SCG/tests/test_runtime_safety.py::test_imported_documentation_replay_is_idempotent',
    '-q', '--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,
    '--junitxml=' + str(task / (label+'.xml'))]
env = os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf8', QT_QPA_PLATFORM='offscreen')
env.pop('PYTHONPATH', None)
record = {'command': command, 'cwd': str(repo),
    'source_commit': subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
    'started_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Direct monorepo python -m pytest, no custom import shim, no PYTHONPATH, original importer and documentation assertions.'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
    result = subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2))
print(record['exit'])
print((task/(label+'.log')).read_text(encoding='utf8')[-3000:])
