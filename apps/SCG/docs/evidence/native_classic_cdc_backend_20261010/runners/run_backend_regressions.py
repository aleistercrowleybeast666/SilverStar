from pathlib import Path
from datetime import datetime, timezone
import os, json, subprocess
task = Path(__file__).resolve().parent
root = Path('D:/python_software/SilverStar/.work/ccdi')
label = 'nbr01'
env = os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', QT_QPA_PLATFORM='offscreen',
    SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT='C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation')
command = ['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe', '-B', str(task / 'backend_pytest.py'),
    'apps/SCG/tests/test_native_classic_cdc.py::test_import_preservation_and_reload',
    'apps/SCG/tests/test_build_progress.py', 'apps/SCG/tests/test_build_audit.py',
    '-p', 'no:cacheprovider', '--basetemp=C:/Users/chdxm/AppData/Local/Temp/' + label, '-q']
record = {'command': command, 'cwd': str(root), 'started_utc': datetime.now(timezone.utc).isoformat(),
          'scope': 'Preserved static native import/model roundtrip and ordinary build tooling unit tests only'}
with (task / (label + '.log')).open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=360)
record.update(exit=result.returncode, finished_utc=datetime.now(timezone.utc).isoformat())
(task / (label + '-command.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
print(label, result.returncode)
print((task / (label + '.log')).read_text(encoding='utf-8')[-10000:])
