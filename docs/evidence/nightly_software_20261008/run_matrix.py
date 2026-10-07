import json
import os
from pathlib import Path
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
cases = {
    'scg': ['.venv/Scripts/python.exe', str(out/'run_scg.py'),
        'apps/SCG/tests/test_feature_tiers.py', 'apps/SCG/tests/test_feature_tier_logging_policy.py',
        'apps/SCG/tests/test_tier_device_boundaries.py', 'apps/SCG/tests/test_tier_device_gui.py',
        '-vv', '-s', '--basetemp=apps/SCG/.work/nc08_matrix1'],
    'flp': ['apps/FLP/.venv/Scripts/python.exe', str(out/'run_flp_plain.py'),
        'apps/FLP/tests/test_project_stage_progress_gui.py',
        'apps/FLP/tests/test_artifact_byte_progress.py', 'apps/FLP/tests/test_project_stage_progress.py',
        'apps/FLP/tests/test_record_block_artifacts.py', 'apps/FLP/tests/test_audit_block_artifacts.py',
        'apps/FLP/tests/test_project_artifact_boundaries.py',
        'apps/FLP/tests/test_project_artifacts.py', 'apps/FLP/tests/test_run_deletion.py',
        '-vv', '-s', '--basetemp=.work/nc08_flp_matrix1'],
}
for name in sys.argv[1:]:
    command = cases[name]
    log = out/(name+'_matrix1.log')
    started = time.monotonic()
    timeout = 1500 if name == 'scg' else 900
    result = dict(command=command, cwd=str(repo), timeout_s=timeout,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip())
    with log.open('w',encoding='utf-8') as stream:
        try:
            completed = subprocess.run(command, cwd=repo, env=dict(os.environ,
                QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8'),
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            result['exit_code'] = completed.returncode
        except subprocess.TimeoutExpired:
            result.update(exit_code=None, timed_out=True)
    result['elapsed_s'] = time.monotonic()-started
    (out/(name+'_matrix1.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(name, result, flush=True)
