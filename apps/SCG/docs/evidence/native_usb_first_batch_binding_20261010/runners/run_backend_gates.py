from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

task = Path(__file__).resolve().parent
label = sys.argv[1]
rows = [json.loads(line) for line in (task / (label + '-build-index.jsonl')).read_text(encoding='utf-8').splitlines()]
assert len(rows) == 2
assert {row['part'] for row in rows} == {'STM32F103C8T6', 'STM32F407VET6'}
env = os.environ.copy()
env['PATH'] = 'D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;' + env.get('PATH', '')
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
python = 'D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe'
records = []
for row in rows:
    family = 'f103' if row['part'] == 'STM32F103C8T6' else 'f407'
    root = Path(row['output'])
    emitted = (root / 'Makefile').read_text(encoding='utf-8')
    assert '$(PYTHON) Tools/check_native_ground.py host' in emitted
    assert '-File Tools/check_power_of_ten.ps1 -TargetKind Ground' in emitted
    for name, command in (
        ('architecture', [python, 'Tools/check_native_ground.py']),
        ('host', [python, 'Tools/check_native_ground.py', 'host', '--host-cc', 'gcc']),
        ('artifact', [python, 'Tools/check_native_ground.py', 'artifact', '--prefix', 'arm-none-eabi-']),
        ('power10', ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'Tools/check_power_of_ten.ps1', '-TargetKind', 'Ground']),
    ):
        logfile = task / (label + '-' + family + '-' + name + '.log')
        record = {'family': family, 'cwd': str(root), 'command': command,
                  'started_utc': datetime.now(timezone.utc).isoformat(),
                  'emitted_makefile_sha256': hashlib.sha256((root / 'Makefile').read_bytes()).hexdigest()}
        with logfile.open('w', encoding='utf-8') as log:
            completed = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        record.update(exit=completed.returncode, finished_utc=datetime.now(timezone.utc).isoformat(),
                      log=str(logfile), log_sha256=hashlib.sha256(logfile.read_bytes()).hexdigest())
        records.append(record)
        (task / (label + '-gates.json')).write_text(json.dumps(records, indent=2), encoding='utf-8')
        print(family, name, completed.returncode, flush=True)
        if completed.returncode:
            print(logfile.read_text(encoding='utf-8', errors='replace')[-7000:])
            raise SystemExit(completed.returncode)
