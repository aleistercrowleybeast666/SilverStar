from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
results = []
lock = threading.Lock()
environment = dict(os.environ)
environment['PATH'] = str(ROOT / '.venv/Scripts') + os.pathsep + environment['PATH']

def run(name, project, arguments):
    command = ['mingw32-make', *arguments]
    log = OUT / (name + '.log')
    start = time.monotonic()
    print('BEGIN', name, flush=True)
    with log.open('wb') as output:
        try:
            code = subprocess.run(command, cwd=project, stdout=output, stderr=subprocess.STDOUT, env=environment, timeout=1200).returncode
        except subprocess.TimeoutExpired:
            code = 'TIMEOUT'
    with lock:
        results.append({'name': name, 'command': command, 'cwd': str(project), 'exit_code': code, 'seconds': time.monotonic() - start, 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        (OUT / 'matrix_results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('END', name, code, flush=True)

def matrix(name):
    for layout in ['auto', 'legacy']:
        project = OUT / (name + '_' + layout + '_v1') / 'Flight_Controller'
        gates = [('arm', ['-j4', 'CONFIG=Release', 'artifact-check'])]
        if layout == 'auto':
            gates += [('architecture', ['architecture-check']), ('power10', ['power10-check']), ('host', ['host-tests']), ('analyzer', ['-j4', 'CONFIG=Release', 'static-analysis'])]
        gates += [('resources', ['CONFIG=Release', 'memory-report', 'stack-report'])]
        for gate, args in gates:
            run(name.lower() + '_' + layout + '_' + gate, project, args)

with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(matrix, ['SF6', 'KF6', 'PureINS', 'ESKF15']))
print('COMPLETE', flush=True)
