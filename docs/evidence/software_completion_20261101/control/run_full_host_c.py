"""Complete emitted Host run bound to the exact fresh C generation snapshot."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from generate_full_host_c import Snapshot_Read, ROOT, HERE, WORK, OUT

label = sys.argv[1]
assert label in ('f407', 'installation')
project = WORK / label / 'Flight_Controller'
generation = json.loads((OUT / 'source-snapshot.json').read_text(encoding='utf8'))
assert generation['changed'] == []
control_owners = set((HERE / 'OWNED_FILES.txt').read_text(encoding='utf8').splitlines())
initial = Snapshot_Read()
initial_owner_changed = sorted(name for name in initial.keys() | generation['after'].keys()
                              if initial.get(name) != generation['after'].get(name))
assert not [name for name in initial_owner_changed if name in control_owners or
    name.startswith(('apps/SCG/plugins/builtin/', 'contracts/'))], 'Relevant owner changed since fresh generation'


def generated_sources():
    # Bytecode is a generated Python cache, not an owning or generated source.
    return {str(path.relative_to(project)).replace('\\', '/'):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(project.rglob('*')) if path.is_file() and
            path.relative_to(project).parts[0].lower() != 'build' and
            '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}


before = generated_sources()
log_path = HERE / f'full-host-c-{label}.log'
receipt_path = HERE / f'full-host-c-{label}.json'
assert not log_path.exists() and not receipt_path.exists()
command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
           str(project / 'Tests/Host/run_tests.ps1'), '-HostCompiler', 'D:/msys64/ucrt64/bin/gcc.exe']
environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
print(json.dumps({'label': label, 'generation_head': generation['head'], 'command': command}), flush=True)
started = time.time()
with log_path.open('wb') as output:
    result = subprocess.run(command, cwd=project, env=environment,
                            stdout=output, stderr=subprocess.STDOUT, timeout=1800)
after = generated_sources()
changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
current = Snapshot_Read()
owner_changed = sorted(name for name in current.keys() | generation['after'].keys()
                       if current.get(name) != generation['after'].get(name))
relevant_owner_changed = [name for name in owner_changed if name in control_owners or
    name.startswith(('apps/SCG/plugins/builtin/', 'contracts/'))]
record = {'label': label, 'generation_head': generation['head'], 'project': str(project),
    'command': command, 'environment_override': {'PYTHONDONTWRITEBYTECODE': '1'},
    'exit': result.returncode, 'elapsed_seconds': time.time() - started,
    'scope': 'Complete emitted Host suite; no -Only filter; no hand-modified generated source',
    'generated_sources_sha256': before, 'changed_generated_sources': changed,
    'changed_owning_sources': owner_changed,
    'changed_owning_sources_before_run': initial_owner_changed,
    'changed_control_or_plugin_contract_sources': relevant_owner_changed,
    'parallel_scope': 'Other Python owners may change after generation; their full diff is recorded, never attributed to this immutable generated Host epoch',
    'log_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
    'hardware': 'Host logical ports only; no MCU recovery, physical device or deadline qualification'}
receipt_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(json.dumps({key: record[key] for key in ('label', 'exit', 'elapsed_seconds',
      'changed_generated_sources', 'changed_owning_sources')}), flush=True)
assert not changed and not relevant_owner_changed, (changed, relevant_owner_changed)
raise SystemExit(result.returncode)
