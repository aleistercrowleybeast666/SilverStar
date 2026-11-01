"""Run the B projects' emitted gates, without altering their commands or inputs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v5/b'
GCC = Path('D:/Arm GNU Toolchain/14.3 rel1/bin')
HOST = Path('D:/msys64/ucrt64/bin')
OUT = HERE / 'gates-b'
environment = os.environ.copy()
environment['PATH'] = os.pathsep.join((str(GCC), str(HOST), str(Path(sys.executable).parent), environment['PATH']))


def Case_Run(name):
    project = WORK / name / 'Flight_Controller'
    rows = []
    # Static analysis is the real emitted ANALYZE=1 ARM build, in its separate
    # build directory. It does not replace either normal compiled artifact.
    targets = [('Release', target) for target in
               ('architecture-check', 'power10-check', 'static-analysis', 'stack-report')]
    targets.append(('Debug', 'stack-report'))
    for configuration, target in targets:
        command = [str(HOST / 'mingw32-make.exe'), '-C', str(project), '-j4',
                   'CONFIG=' + configuration, 'GCC_PATH=' + str(GCC),
                   'PYTHON=' + sys.executable, target]
        log = OUT / (name + '-' + configuration + '-' + target + '.log')
        started = time.monotonic()
        with log.open('w', encoding='utf8') as stream:
            result = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        rows.append({'name': name, 'configuration': configuration, 'target': target,
                     'command': command, 'exit_code': result.returncode,
                     'seconds': round(time.monotonic() - started, 3), 'log': log.name,
                     'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        print(name, configuration, target, result.returncode, flush=True)
        (OUT / (name + '-commands.json')).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    return rows


if __name__ == '__main__':
    built = json.loads((HERE / 'build-b/commands.json').read_text(encoding='utf8'))
    compared = json.loads((HERE / 'build-b/raw-byte-comparison.json').read_text(encoding='utf8'))
    assert len(built) == 20 and all(row['exit_code'] == 0 for row in built)
    assert len(compared) == 10 and all(row['passes'] for row in compared)
    OUT.mkdir(exist_ok=False)
    rows = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(Case_Run, name) for name in ('f407', 'installation', 'h743', 'pid', 'lqr')]
        for future in as_completed(pending):
            rows.extend(future.result())
            (OUT / 'commands.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    raise SystemExit(int(any(row['exit_code'] for row in rows)))
