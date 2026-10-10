from pathlib import Path
from datetime import datetime, timezone
import subprocess, os, json, hashlib, sys

task=Path(__file__).parent; repo=task/'r'
label=sys.argv[1] if len(sys.argv)>1 else 'srnorm01'
python=r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe'
command=[python,'-B','-m','pytest',
 'apps/SCG/tests/test_physical_device_platform_identity.py',
 'apps/SCG/tests/test_internal_platform_refactor.py::test_platform_matching_reports_zero_and_tied_candidates',
 '-q','-p','no:cacheprovider','--basetemp=C:/Users/chdxm/AppData/Local/Temp/'+label,
 '--junitxml='+str(task/(label+'.xml'))]
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',QT_QPA_PLATFORM='offscreen')
files=['apps/SCG/src/silverstar_fccg/hardware/platform.py',
 'apps/SCG/src/silverstar_fccg/core/platform_tokens.py',
 'apps/SCG/src/silverstar_fccg/plugins/catalog.py',
 'apps/SCG/tests/test_physical_device_platform_identity.py']
record={'command':command,'cwd':str(repo),
 'head':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'dirty_diff':subprocess.check_output(['git','-C',str(repo),'diff','--binary'],text=True),
 'source_sha256':{f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in files},
 'started_utc':datetime.now(timezone.utc).isoformat(),
 'scope':'Precommit ordinary P2 contract test, actual matcher equivalence plus three spelling collisions, empty token and distinct target positive; no malformed USB/owner-expression review.'}
with (task/(label+'.log')).open('w',encoding='utf8') as log:
 result=subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
(task/(label+'-command.json')).write_text(json.dumps(record,indent=2))
print(result.returncode);print((task/(label+'.log')).read_text(encoding='utf8')[-5000:])
