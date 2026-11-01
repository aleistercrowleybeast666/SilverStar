"""Execute one complete emitted Host suite and bind its unchanged generated sources."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
project = Path(sys.argv[1]).resolve()
label = sys.argv[2]
source_commit = 'e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a'
assert label in ('default', 'installation')
assert project.is_dir() and (project / 'Tests/Host/run_tests.ps1').is_file()


def source_tree():
    return {str(path.relative_to(project)).replace('\\', '/'):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(project.rglob('*')) if path.is_file() and
            path.relative_to(project).parts[0].lower() != 'build'}


def source_unchanged():
    differences = subprocess.check_output(['git', 'diff', '--name-only', source_commit, '--',
        'apps/SCG/src', 'apps/SCG/plugins', 'contracts'], cwd=ROOT, text=True)
    assert not differences.strip(), differences


source_unchanged()
before = source_tree()
log_path = HERE / f'full-host-b-{label}.log'
receipt_path = HERE / f'full-host-b-{label}.json'
assert not log_path.exists() and not receipt_path.exists()
command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
           str(project / 'Tests/Host/run_tests.ps1'), '-HostCompiler', 'D:/msys64/ucrt64/bin/gcc.exe']
print(json.dumps({'label': label, 'source_commit': source_commit, 'command': command}), flush=True)
started = time.time()
with log_path.open('wb') as output:
    result = subprocess.run(command, cwd=project, stdout=output, stderr=subprocess.STDOUT, timeout=1800)
elapsed = time.time() - started
after = source_tree()
changed = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
source_unchanged()
record = {'label': label, 'source_commit': source_commit, 'project': str(project),
          'command': command, 'exit': result.returncode, 'elapsed_seconds': elapsed,
          'scope': 'Complete emitted Host suite, no -Only filter; actual generated source snapshot',
          'generated_sources_sha256': before, 'changed_generated_sources': changed,
          'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
          'hardware': 'Host logical ports only; no MCU recovery, physical device or deadline qualification'}
receipt_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(json.dumps({'label': label, 'exit': result.returncode, 'elapsed_seconds': elapsed,
                  'changed_generated_sources': changed}), flush=True)
assert not changed, changed
raise SystemExit(result.returncode)
