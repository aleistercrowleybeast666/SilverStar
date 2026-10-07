import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

runner = Path(__file__).resolve().parent
repo = next(p for p in runner.parents if (p/'.git').exists())
out = runner if runner.parent.name == '.work' else repo/'.work'/('nightly_closeout_rerun_'+uuid4().hex[:8])
out.mkdir(parents=True,exist_ok=True)
gui = ['apps/FLP/tests/test_project_stage_progress_gui.py',
       'apps/FLP/tests/test_plot_menu_lifetime.py']
artifact = ['apps/FLP/tests/test_artifact_byte_progress.py',
    'apps/FLP/tests/test_project_stage_progress.py',
    'apps/FLP/tests/test_record_block_artifacts.py',
    'apps/FLP/tests/test_audit_block_artifacts.py',
    'apps/FLP/tests/test_project_artifact_boundaries.py',
    'apps/FLP/tests/test_project_artifacts.py', 'apps/FLP/tests/test_run_deletion.py']
cases = {
 'scg_final': ['.venv/Scripts/python.exe', str(runner/'run_scg.py'),
     'apps/SCG/tests/test_feature_tiers.py', 'apps/SCG/tests/test_feature_tier_logging_policy.py',
     'apps/SCG/tests/test_tier_device_boundaries.py', 'apps/SCG/tests/test_tier_device_gui.py',
     '-vv', '-s', '--basetemp=apps/SCG/.work/nc08_final'],
 'flp_final': ['apps/FLP/.venv/Scripts/python.exe', str(runner/'run_flp_plain.py'),
     *gui, *artifact, '-vv', '-s', '--basetemp=.work/nc08_flp_final'],
 'flp_native_final': ['apps/FLP/.venv/Scripts/python.exe', str(runner/'run_probe.py'),
     *gui, '-vv', '-s', '-p', 'no:cacheprovider', '--basetemp=.work/nc08_flp_native_final'],
 'gshc_final': ['.venv/Scripts/python.exe', str(runner/'run_gshc.py'),
     'apps/GSHC/tests/test_air_protocol.py', 'apps/GSHC/tests/test_navigation_readiness.py',
     'apps/GSHC/tests/test_nrf24_transport.py', '-vv', '-s', '--basetemp=.work/nc08_gshc_final'],
 'flp_worker_final': ['apps/FLP/.venv/Scripts/python.exe',str(runner/'run_probe.py'),
     'apps/FLP/tests/test_worker_retirement.py',
     'apps/FLP/tests/test_task_publication_thread_affinity.py',
     '-vv','-s','-p','no:cacheprovider','--basetemp=.work/nc08_flp_worker_final'],
}
source = subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
files = subprocess.check_output(['git','ls-files','-z','apps'],cwd=repo).decode('utf8').strip(chr(0)).split(chr(0))
source_hash = {p: hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in files}
(out/'source_hashes_final.json').write_text(json.dumps(source_hash,indent=2),encoding='utf8')
failed = False
for name in sys.argv[1:]:
    command = cases[name]
    command[-1] += '_'+uuid4().hex[:8]
    start = time.monotonic()
    result = dict(command=command, cwd=str(repo), source_head=source, timeout_s=900)
    with (out/(name+'.log')).open('w',encoding='utf8') as stream:
        try:
            run = subprocess.run(command,cwd=repo,env=dict(os.environ,
                QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8',
                PYTHONPATH=str(repo/'apps/GSHC')+os.pathsep+str(repo/'apps/GSHC/tests')),
                stdout=stream,stderr=subprocess.STDOUT,timeout=900)
            result['exit_code']=run.returncode
        except subprocess.TimeoutExpired:
            result.update(exit_code=None,timed_out=True)
    result['elapsed_s']=time.monotonic()-start
    (out/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(name,result,flush=True)
    failed |= result['exit_code'] != 0
raise SystemExit(int(failed))
