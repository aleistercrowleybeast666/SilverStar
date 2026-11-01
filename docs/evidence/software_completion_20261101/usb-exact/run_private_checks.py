"""Run the emitted private-candidate make gates without changing their rules."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

project = Path(sys.argv[1]).resolve()
part = sys.argv[2]
target = Path(__file__).resolve().parent / 'buildchecks-v1' / part
target.mkdir(parents=True, exist_ok=False)
assert (project / 'backend-receipt.json').is_file() or (project / 'usb-backend-receipt.json').is_file()
assert (project / 'receipt.json').is_file()
receipt = json.loads((project / 'receipt.json').read_text(encoding='utf8'))
assert receipt['status'] == 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
sources = ['Makefile', 'Tools/check_power_of_ten.ps1', 'Generated/ground_source_graph.json']
sources += [str(p.relative_to(project)).replace('\\', '/') for p in (project / 'Tools').glob('*.py')]
report = {'project': str(project), 'part': part, 'emitted_inputs_sha256': {
    name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in sources}, 'runs': []}
for gate in ('architecture-check', 'host-tests', 'power10-check', 'artifact-check'):
    command = [shutil.which('mingw32-make'), '-j2', gate, 'PYTHON=' + sys.executable,
               'HOST_CC=' + shutil.which('gcc')]
    result = subprocess.run(command, cwd=project, capture_output=True, text=True,
                            encoding='utf8', errors='replace', timeout=600)
    log = result.stdout + result.stderr
    (target / (gate + '.log')).write_text(log, encoding='utf8')
    report['runs'].append({'gate': gate, 'command': command, 'exit': result.returncode,
                          'log_sha256': hashlib.sha256(log.encode()).hexdigest()})
    (target / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(f'{part}: {gate}: exit {result.returncode}', flush=True)
raise SystemExit(int(any(row['exit'] for row in report['runs'])))
