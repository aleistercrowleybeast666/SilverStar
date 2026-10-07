import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

runner=Path(__file__).resolve().parent
repo=next(p for p in runner.parents if (p/'.git').exists())
out=runner if runner.parent.name=='.work' else repo/'.work'/('nightly_v2_'+uuid4().hex[:8])
out.mkdir(parents=True,exist_ok=True)
flp=['apps/FLP/.venv/Scripts/python.exe']
files=['test_project_stage_progress_gui.py','test_plot_menu_lifetime.py',
 'test_artifact_byte_progress.py','test_project_stage_progress.py',
 'test_record_block_artifacts.py','test_audit_block_artifacts.py',
 'test_project_artifact_boundaries.py','test_project_artifacts.py','test_run_deletion.py',
 'test_worker_retirement.py','test_task_publication_thread_affinity.py']
cases={
 'flp_combined_v2': [*flp,str(runner/'run_probe.py'),
     *['apps/FLP/tests/'+name for name in files],'-vv','-s','-p','no:cacheprovider'],
 'gnss_views_v2': [*flp,str(runner/'run_flp_plain.py'),'apps/FLP/tests/test_gnss_integrity.py','-vv','-s'],
}
cases['flp_combined_v3']=cases['flp_combined_v2']
cases['flp_combined_v4']=[*flp,str(runner/'run_probe.py'),
    *['apps/FLP/tests/'+name for name in files],
    'apps/FLP/tests/test_project_save_path_boundary.py',
    'apps/FLP/tests/test_i18n_consistency.py','-vv','-s','-p','no:cacheprovider']
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
paths=subprocess.check_output(['git','ls-files','-z','apps'],cwd=repo).decode('utf8').strip('\0').split('\0')
snapshot='source_hashes_v4.json' if 'flp_combined_v4' in sys.argv else 'source_hashes_v2.json'
(out/snapshot).write_text(json.dumps({p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in paths},indent=2),encoding='utf8')
failed=False
for name in sys.argv[1:]:
    base=('.work/v'+name[-1]+'_'+uuid4().hex[:8]) if name in ('flp_combined_v3','flp_combined_v4') else ('.work/nc08_'+name+'_'+uuid4().hex[:8])
    command=cases[name]+['--basetemp='+base]
    result=dict(command=command,cwd=str(repo),source_head=revision,timeout_s=900)
    started=time.monotonic()
    with (out/(name+'.log')).open('w',encoding='utf8') as stream:
        try:
            run=subprocess.run(command,cwd=repo,env=dict(os.environ,
                QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8'),
                stdout=stream,stderr=subprocess.STDOUT,timeout=900)
            result['exit_code']=run.returncode
        except subprocess.TimeoutExpired:
            result.update(exit_code=None,timed_out=True)
    result['elapsed_s']=time.monotonic()-started
    (out/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(name,result,flush=True)
    failed |= result['exit_code'] != 0
raise SystemExit(int(failed))
