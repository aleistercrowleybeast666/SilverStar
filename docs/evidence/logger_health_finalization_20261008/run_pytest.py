from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

repo = Path.cwd()
output = Path(__file__).resolve().parent
project = output / 'project/Flight_Controller'
env = dict(os.environ)
env['PYTHONPATH'] = ';'.join(str(path) for path in (
    repo / 'apps/SCG/src', repo / 'apps/SCG/tests',
    repo / 'docs/evidence/nightly_software_20261008'))
env['SCG_ESTIMATOR_HEALTH_PROJECT'] = str(project)
env['SCG_LOGGER_HEALTH_PROJECT'] = str(project)
argv = [sys.executable, '-m', 'pytest',
        'apps/SCG/tests/test_logger_health_boundary.py',
        'apps/SCG/tests/test_estimator_health_publication.py',
        '-q', '-p', 'normal_test_paths', '-p', 'no:cacheprovider',
        '--basetemp=' + str(output / 'pytest_normal_v2'),
        '--junitxml=' + str(output / 'pytest_normal_v2.xml')]
record = dict(argv=argv, cwd=str(repo), hardware=False,
              utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              base_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              source_sha256=hashlib.sha256((project / 'APP/Src/estimator_task.c').read_bytes()).hexdigest(),
              private_directory_plugin='docs/evidence/nightly_software_20261008/normal_test_paths.py',
              initial_attempt='pytest.log: EEEEE, cleanup PermissionError; no product-test acceptance')
with (output / 'pytest_normal_v2.log').open('xb') as stream:
    result = subprocess.run(argv, cwd=repo, env=env, stdout=stream,
                            stderr=subprocess.STDOUT, timeout=180)
record.update(exit_code=result.returncode,
              utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              log_sha256=hashlib.sha256((output / 'pytest_normal_v2.log').read_bytes()).hexdigest())
(output / 'pytest_normal_v2_result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print('pytest exit=' + str(result.returncode), flush=True)
