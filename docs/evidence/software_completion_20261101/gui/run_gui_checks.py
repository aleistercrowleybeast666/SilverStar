"""Record one complete GUI suite and its stable Python/catalog source epoch."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
evidence = Path(__file__).parent/sys.argv[1]
evidence.mkdir(exist_ok=False)
work = ROOT/'.work/0.1.3-software-completion-20261101/gui'/sys.argv[1]
assert not work.exists()
tests = ['test_hardware_transaction.py', 'test_control_task_gui.py',
    'test_hardware_workspace.py', 'test_radio_transaction.py', 'test_control_task_import_boundary.py', 'test_hardware_overview_actions.py', 'test_release_migration.py',
    'test_three_workspace_workflow.py', 'test_workflow_window_lifecycle.py',
    'test_workflow_startup_windows.py', 'test_workflow_connections.py']
command = [sys.executable, '-m', 'pytest', *(str(ROOT/'apps/SCG/tests'/name) for name in tests),
           '-q', '--basetemp='+str(work)]
environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPATH=str(ROOT/'apps/SCG/src'))


def Snapshot():
    paths = set((ROOT/'apps/SCG/src').rglob('*.py'))
    paths.update((ROOT/'apps/SCG/src/silverstar_fccg/i18n').glob('*.json'))
    paths.update((ROOT/'contracts').glob('*.json'))
    paths.update((ROOT/'apps/SCG/plugins/builtin').glob('*/plugin.json'))
    paths.update(ROOT/'apps/SCG/tests'/name for name in tests)
    paths.add(ROOT/'apps/SCG/tests/fixtures/hardware_dialog_lifecycle.py')
    paths.add(ROOT/'tools/silverstar_mission_functions.py')
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


before = Snapshot()
(evidence/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf8')
identity = {'base_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'command': command, 'python': sys.version, 'environment':{k:environment[k] for k in ('QT_QPA_PLATFORM','PYTHONPATH','PYTHONDONTWRITEBYTECODE')},
    'scope':'GUI/domain software checks; no ARM build or hardware claim'}
(evidence/'identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8')
(evidence/'source.diff').write_bytes(subprocess.check_output(['git','diff','--binary','--',
    'apps/SCG/src','apps/SCG/tests','apps/SCG/plugins/builtin/*/plugin.json','contracts','tools/silverstar_mission_functions.py'],cwd=ROOT))
started=time.monotonic()
with (evidence/'pytest.log').open('wb') as log:
    result=subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
after=Snapshot()
changed=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]
(evidence/'source-after.json').write_text(json.dumps(after,indent=2),encoding='utf8')
summary={'exit_code':result.returncode,'seconds':time.monotonic()-started,
    'source_changed':changed,'source_epoch_stable':not changed}
(evidence/'result.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print(json.dumps(summary))
raise SystemExit(result.returncode if not changed else 3)
