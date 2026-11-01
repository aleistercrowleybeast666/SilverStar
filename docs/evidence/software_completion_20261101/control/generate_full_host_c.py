"""Fresh ordinary default/installation models and generation after the Host ABI fixture update."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SCG = ROOT / 'apps/SCG'
HERE = Path(__file__).resolve().parent
OUT = HERE / 'full-host-c-generation'
WORK = ROOT / '.work/0.1.3-software-completion-20261101/control/full-host-c'
sys.path.insert(0, str(SCG / 'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create


def Snapshot_Read():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in (SCG / 'plugins/builtin', SCG / 'src', ROOT / 'contracts')
            for path in sorted(directory.rglob('*')) if path.is_file() and
            '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}


if __name__ == '__main__':
    before = Snapshot_Read()
    OUT.mkdir(parents=True, exist_ok=False)
    WORK.mkdir(parents=True, exist_ok=False)
    service = FccgService(SCG)
    records = []
    for name in ('f407', 'installation'):
        model = ReferenceProject_Create('SoftwareCompletion_' + name, catalog=service.catalog)
        if name == 'installation':
            model.base_components.append('silverstar.installation.capture')
            model.device_instances = [replace(item, profile='jy901b_mag_capture')
                if item.plugin == 'silverstar.device.imu.jy901b' else item for item in model.device_instances]
            LoggingProfile_Reconcile(model, service.catalog)
        destination = WORK / name
        result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        print(name, result, flush=True)
        (OUT / (name + '-model.json')).write_text(json.dumps(model.Dictionary_Get(), indent=2) + '\n', encoding='utf8')
        (OUT / (name + '-graph.json')).write_text(json.dumps(asdict(SourceGraph_Resolve(model, service.catalog)), indent=2) + '\n', encoding='utf8')
        records.append({'name': name, 'project': str(destination / 'Flight_Controller')})
    after = Snapshot_Read()
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    identity = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'production_diff': subprocess.check_output(['git', 'diff', '--', 'apps/SCG/src', 'apps/SCG/plugins', 'contracts'], cwd=ROOT, text=True, encoding='utf8'),
        'before': before, 'after': after, 'changed': changed}
    (OUT / 'source-snapshot.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf8')
    (OUT / 'projects.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
    assert not changed, changed
    print('PASS: two fresh Host C projects, source snapshot unchanged', flush=True)
