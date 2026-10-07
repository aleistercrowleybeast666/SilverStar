import os
import subprocess
import sys
import time
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
python = repo/'apps/FLP/.venv/Scripts/python.exe'
runner = out/'run_flp_tests.py'
cases = ['finish', 'cancel', 'close']
results = []
env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
for case in cases:
    node = f'apps/FLP/tests/test_project_stage_progress_gui.py::test_slow_array_save_keeps_gui_responsive_and_atomic[{case}]'
    command = [str(python), str(runner), node, '-q',
        '--basetemp='+str(out/('slow_'+case+'_v6')),
        '-o', 'cache_dir='+str(out/('cache_slow_'+case+'_v6'))]
    started = time.monotonic()
    log = out/('slow_'+case+'_v6.log')
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=repo, env=env, stdout=stream, stderr=subprocess.STDOUT)
    results.append({'node': node, 'command': command, 'exit_code': result.returncode,
        'elapsed_seconds': time.monotonic()-started, 'log': str(log)})
    print(case, result.returncode, flush=True)
    (out/'isolated_gui_v6.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(0 if all(item['exit_code'] == 0 for item in results) else 1)
