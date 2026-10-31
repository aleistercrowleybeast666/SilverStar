"""Compare exact checked-in pre-fix parser with the repaired parser on frozen inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORK = REPO / '.work/0.1.3-treediagram-20261101/legacy-migration-v1'
WORK.mkdir(parents=True, exist_ok=False)
source_path = 'apps/SCG/src/silverstar_fccg/project/model.py'
before = subprocess.check_output(['git', 'show', '4f701b4:' + source_path], cwd=REPO)
path = WORK/'before_model.py'
path.write_bytes(before)
spec = importlib.util.spec_from_file_location('_migration_before', path)
old = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old
spec.loader.exec_module(old)
from silverstar_fccg.project import model as current

result = dict(before_commit='4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e',
    before_source_sha256=hashlib.sha256(before).hexdigest(),
    after_source_sha256=hashlib.sha256((REPO/source_path).read_bytes()).hexdigest(), cases=[])
for fixture in sorted((REPO/'apps/SCG/tests/fixtures/legacy_project_fields').glob('v*.json')):
    row = dict(input=fixture.name, input_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest())
    for label, module in [('before', old), ('after', current)]:
        try:
            output = module.ProjectModel_Parse(json.loads(fixture.read_text(encoding='utf-8')))
            row[label] = dict(status='parsed', format_version=output.format_version,
                protocols=output.ProtocolProfiles_Get(), ground_hardware=output.ground_target.hardware.mode,
                algorithm_parameters=output.algorithm_parameters)
        except Exception as error:
            row[label] = dict(status='rejected', error_type=type(error).__name__, message=str(error))
    if fixture.name == 'v2.json':
        assert row['after']['status'] == 'rejected' and 'device instance' in row['after']['message']
    else:
        assert row['before']['status'] == 'rejected' and row['after']['status'] == 'parsed'
    result['cases'].append(row)
(HERE/'legacy-migration-before-after.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
