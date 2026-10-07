import json
import os
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
prefix = 'apps/FLP/tests/test_project_stage_progress_gui.py::'
nodes = [
    *[f'test_background_save_stages_finish_only_after_gui_publication[{value}]' for value in ('False', 'True')],
    *[f'test_project_open_reads_in_worker_and_reports_cache_or_parse[{value}]' for value in ('valid', 'missing', 'corrupt')],
    *[f'test_cancelled_or_closed_open_never_publishes_complete[{value}]' for value in ('cancel', 'close')],
    'test_failed_open_never_reports_complete',
    *[f'test_original_save_lifecycle_unchanged[{value}]' for value in
      ('clean_close', 'cancel_close_option', 'cancel_after_commit', 'snapshot_removed')],
]
results = []
for index, node in enumerate(nodes):
    command = [str(repo/'apps/FLP/.venv/Scripts/python.exe'), str(out/'run_flp_tests.py'),
               '-p', 'closeout_test_paths', prefix+node, '-q',
               '--basetemp='+str(repo/'.work'/f'fs10{index}')]
    log = out/f'isolated_stage_v10_{index}.log'
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=repo, env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                                stdout=stream, stderr=subprocess.STDOUT)
    results.append(dict(command=command, exit_code=result.returncode,
                        elapsed_seconds=time.monotonic()-started, log=str(log)))
    (out/'isolated_stages_v10.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(index, result.returncode, flush=True)
raise SystemExit(0 if all(item['exit_code'] == 0 for item in results) else 1)
