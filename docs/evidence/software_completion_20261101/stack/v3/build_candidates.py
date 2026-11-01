"""Real independent builds, exact emitted artifact gate and raw-byte comparison."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent / 'build-v1'
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v3'
GCC = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
HOST = Path('D:/msys64/ucrt64/bin')
environment = os.environ.copy()
environment['PATH'] = os.pathsep.join((str(GCC), str(HOST), str(Path(sys.executable).parent), environment['PATH']))

def Build_Run(case):
    replica, name, configuration = case
    project = WORK / replica / name / 'Flight_Controller'
    records = []
    for target in ('all', 'artifact-check'):
        command = [str(HOST / 'mingw32-make.exe'), '-C', str(project), '-j4', 'CONFIG=' + configuration,
                   'GCC_PATH=' + str(GCC), 'PYTHON=' + sys.executable, target]
        log = OUT / ('-'.join(case) + '-' + target + '.log')
        start = time.monotonic()
        with log.open('w', encoding='utf8') as stream:
            result = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        records.append({'case': case, 'command': command, 'exit_code': result.returncode,
            'seconds': round(time.monotonic() - start, 3), 'log': log.name,
            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        print(*case, target, result.returncode, flush=True)
        if result.returncode and target == 'all':
            break
    return records

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=False)
    records = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(Build_Run, (replica, name, configuration))
            for replica in ('a', 'b') for name in ('f407', 'installation', 'h743')
            for configuration in ('Release', 'Debug')]
        for future in as_completed(futures):
            records.extend(future.result())
            (OUT / 'commands.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
    comparisons = []
    for name in ('f407', 'installation', 'h743'):
        for config in ('Release', 'Debug'):
            roots = [WORK / replica / name / 'Flight_Controller/build/FCCG' /
                     ('STM32H743_Custom' if name == 'h743' else 'SilverStar_F407') / config for replica in ('a', 'b')]
            # Read actual target id, rather than assume a custom target spelling.
            roots = [WORK / replica / name / 'Flight_Controller/build/FCCG' /
                     json.loads((WORK / replica / name / 'Flight_Controller/SilverStar.ssproject').read_text())['build']['target_profile'] / config
                     for replica in ('a', 'b')]
            snapshots = [{path.relative_to(base).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in base.rglob('*') if path.is_file() and path.suffix in ('.o', '.su', '.d', '.elf', '.map')}
                         for base in roots]
            changed = sorted(key for key in snapshots[0].keys() | snapshots[1].keys()
                             if snapshots[0].get(key) != snapshots[1].get(key))
            comparisons.append({'name': name, 'config': config, 'roots': [str(path) for path in roots],
                                'artifacts': snapshots, 'changed': changed, 'passes': not changed and bool(snapshots[0])})
    (OUT / 'raw-byte-comparison.json').write_text(json.dumps(comparisons, indent=2) + '\n', encoding='utf8')
    raise SystemExit(int(any(row['exit_code'] for row in records) or any(not row['passes'] for row in comparisons)))
