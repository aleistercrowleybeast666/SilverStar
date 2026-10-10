"""Ordinary service bypass reproduction with a non-executing build runner."""
from pathlib import Path
import hashlib, json, subprocess, sys, types
root = Path('D:/python_software/SilverStar/.work/ccdi')
task = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'apps/SCG/src'))
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.build.runner import BuildAction
from silverstar_fccg.core.errors import FccgError
import silverstar_fccg.app.service as current

revision = '9b9a20be2829dcc5135c648f6dc84b6e9af60316'
command = ['git', '-C', str(root), 'show', revision + ':apps/SCG/src/silverstar_fccg/app/service.py']
before_source = subprocess.check_output(command, text=True, encoding='utf-8')
module = types.ModuleType('silverstar_fccg.app.service_guard_before')
sys.modules[module.__name__] = module
exec(compile(before_source, module.__name__, 'exec'), module.__dict__)
calls = []
class NonExecutingRunner:
    def __init__(self, *args):
        pass
    def Run(self, *args, **kwargs):
        calls.append('build runner reached; no command executed')
        return 'NON_EXECUTING_RUNNER_REACHED'

model = ProjectModel_Load(Path('C:/Users/chdxm/AppData/Local/Temp/sscdc-ground-f103-12c/candidate_config.ssproject'))
model.ground_target.hardware.inventory['native_complete_classic_cdc'] = {}
module.BuildRunner = NonExecutingRunner
before = module.FccgService(task / 'guard-before')
before_result = before.Build_Run(model, task / 'guard-project', BuildAction.BUILD, ensure_buildable=False)
assert before_result == 'NON_EXECUTING_RUNNER_REACHED' and len(calls) == 1
current.BuildRunner = NonExecutingRunner
after = current.FccgService(task / 'guard-after')
try:
    after.Build_Run(model, task / 'guard-project', BuildAction.BUILD, ensure_buildable=False)
except FccgError as error:
    after_result = {'code': error.code, 'detail': str(error)}
else:
    raise AssertionError('new normal build guard did not reject native marker')
assert len(calls) == 1
record = {'baseline': revision, 'before_source_sha256': hashlib.sha256(before_source.encode()).hexdigest(),
          'before_read_command': command, 'before': before_result, 'after': after_result,
          'current_source_sha256': hashlib.sha256((root / 'apps/SCG/src/silverstar_fccg/app/service.py').read_bytes()).hexdigest(),
          'runner_calls': calls, 'actual_build_or_hardware_commands': 0,
          'scope': 'Ordinary Python service guard; mocked runner never executes imported Makefile'}
(task / 'formal-build-guard-pre-post.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=True))
