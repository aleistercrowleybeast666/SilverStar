"""Final complete compatibility group, bound to unchanged tracked source trees."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASE = REPO/'.work/0.1.3-treediagram-20261101/cap6'
assert not BASE.exists(), 'Use a new task directory; never erase prior test evidence.'


def Git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def SourceIdentity():
    return dict(scg_tree=Git('rev-parse', 'HEAD:apps/SCG'), contracts_tree=Git('rev-parse', 'HEAD:contracts'),
                dirty=Git('status', '--porcelain', '--', 'apps/SCG', 'contracts'))


before = SourceIdentity()
assert not before['dirty']
command = [sys.executable, '-u', '-m', 'pytest',
    'apps/SCG/tests/test_device_capability_architecture.py',
    'apps/SCG/tests/test_project_domain.py', 'apps/SCG/tests/test_release_migration.py',
    '-q', '--basetemp=' + str(BASE)]
environment = dict(PYTHONPATH=str(REPO/'apps/SCG/src'), QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8')
receipt = dict(code_commit=Git('rev-parse', 'HEAD'), command=command, cwd=str(REPO),
               environment=environment, before=before)
log = HERE/'capability-v6.log'
with log.open('x', encoding='utf-8') as output:
    result = subprocess.run(command, cwd=REPO, env={**os.environ, **environment},
                            stdout=output, stderr=subprocess.STDOUT)
receipt.update(exit_code=result.returncode, after=SourceIdentity(), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
receipt['sources_unchanged'] = receipt['before'] == receipt['after']
(HERE/'capability-v6-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
(HERE/'capability-v6.exit').write_text(str(result.returncode)+'\n', encoding='utf-8')
assert receipt['sources_unchanged'], 'Source drift detected; do not attribute a complete pass to the final commit.'
print(log.read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
