"""Repeat the complete GUI/domain selection after the final contract revision."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'verification-v10'
TEMP = ROOT / '.work/0.1.3-software-completion-20261101/gui/verification-v10'


def Snapshot():
    roots = [ROOT / 'apps/SCG/src', ROOT / 'apps/SCG/plugins/builtin', ROOT / 'contracts']
    extensions = {'.py', '.c', '.h', '.json', '.ps1', '.ld', '.s', '.md'}
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in roots for path in sorted(folder.rglob('*'))
            if path.is_file() and path.suffix.lower() in extensions and '__pycache__' not in path.parts}


def Write(name, value):
    (OUTPUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')


def Main():
    OUTPUT.mkdir(exist_ok=False)
    assert not TEMP.exists()
    identity = json.loads((HERE / 'verification-v9/identity.json').read_text(encoding='utf8'))
    command = [('--basetemp=' + str(TEMP)) if value.startswith('--basetemp=') else value
               for value in identity['command']]
    env = {**os.environ, **identity['environment'], 'PYTHONUTF8': '1'}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    identity.update(base_commit=head, command=command, reason='Final control-unit metadata, provenance headers and sealed stack owner landed after v9; repeat the whole selection on the final source commit.')
    Write('identity.json', identity)
    before = Snapshot()
    Write('source-before.json', before)
    start = time.monotonic()
    with (OUTPUT / 'pytest.log').open('w', encoding='utf8') as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    after = Snapshot()
    changed = [path for path in before.keys() | after.keys() if before.get(path) != after.get(path)]
    Write('source-after.json', after)
    Write('result.json', {'exit_code': result.returncode, 'seconds': time.monotonic() - start,
                          'source_changed': changed, 'source_epoch_stable': not changed})
    print('GUI final complete selection:', result.returncode, 'source_changed', changed, flush=True)
    raise SystemExit(result.returncode if not changed else 2)


if __name__ == '__main__':
    Main()
