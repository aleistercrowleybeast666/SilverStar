from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

task = Path(__file__).resolve().parent
root = Path('D:/python_software/SilverStar/.work/ccdi')
label, selection = sys.argv[1:3]
env = os.environ.copy()
env['PATH'] = 'D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;' + env.get('PATH', '')
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', QT_QPA_PLATFORM='offscreen',
    SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation',
    SILVERSTAR_NATIVE_BACKEND_CONFIG='C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject',
    SILVERSTAR_NATIVE_BACKEND_ARM='1' if selection in {'real_backend', 'all'} else '0',
    SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX=str(task / (label + '-build-index.jsonl')))
command = ['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe', '-B', str(task / 'backend_pytest.py'),
    'apps/SCG/tests/test_native_ground_backend.py',
    '-p', 'no:cacheprovider', '--basetemp=C:/Users/chdxm/AppData/Local/Temp/' + label, '-q']
if selection != 'all':
    command += ['-k', selection]
paths = ['apps/SCG/src/silverstar_fccg/' + p for p in
         ['app/native_ground.py', 'app/service.py', 'build/native_compile.py', 'project/model.py']]
paths += ['apps/SCG/tools/validation/native_classic_cdc_compile.py', 'apps/SCG/tests/test_native_ground_backend.py']
record = {'command': command, 'cwd': str(root), 'started_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Ordinary backend import/model/render/build flow; no malformed USB, owner expressions, blocked review or hardware',
    'source_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
    'source_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    'auditable_dirty_diff': subprocess.check_output(['git', '-C', str(root), 'diff', '--binary'], text=True)}
manifest = task / (label + '-command.json')
manifest.write_text(json.dumps(record, indent=2), encoding='utf-8')
with (task / (label + '.log')).open('w', encoding='utf-8') as log:
    completed = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
record.update(exit=completed.returncode, finished_utc=datetime.now(timezone.utc).isoformat())
manifest.write_text(json.dumps(record, indent=2), encoding='utf-8')
print(label, completed.returncode)
print((task / (label + '.log')).read_text(encoding='utf-8', errors='replace')[-18000:])
