"""Normally generate identical compiler inputs into independent fresh roots."""
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
SCG = ROOT / 'apps/SCG'
REPLICA = sys.argv[1]
if REPLICA not in ('a', 'b'): raise ValueError('Expected independent replica a/b')
OUT = Path(__file__).resolve().parent / ('generation-' + REPLICA)
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v4'
sys.path.insert(0, str(SCG / 'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.tuning_bundle import TuningBundle_ControlTaskAttach

def Snapshot_Read():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for directory in (SCG / 'plugins/builtin', SCG / 'src', ROOT / 'contracts')
            for path in sorted(directory.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}

before = Snapshot_Read()
OUT.mkdir(parents=True, exist_ok=False)
(WORK / REPLICA).mkdir(parents=True, exist_ok=False)
service = FccgService(SCG)
records = []
for replica in (REPLICA,):
    for name in ('f407', 'installation', 'h743', 'pid', 'lqr'):
        if name == 'h743':
            spec = importlib.util.spec_from_file_location('h7_fixture', SCG / 'tools/validation/h743_static_validate.py')
            fixture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture)
            model, validation = fixture.Scenario_Create(service,
                ROOT / '.work/h7_20261025/verified_release/CubeMX_StaticInput', 'eskf20', 1, {})
            if not validation.valid:
                raise RuntimeError(str(validation))
        else:
            model = ReferenceProject_Create('SoftwareCompletion_' + (name.upper() if name in ('pid', 'lqr') else name), catalog=service.catalog)
            if name == 'installation':
                model.base_components.append('silverstar.installation.capture')
                model.device_instances = [replace(item, profile='jy901b_mag_capture')
                    if item.plugin == 'silverstar.device.imu.jy901b' else item for item in model.device_instances]
                LoggingProfile_Reconcile(model, service.catalog)
        if name in ('pid', 'lqr'):
            bundle = ROOT / 'docs/evidence/software_completion_20261101/delivery/actual-runs-v1' / (name + '.sstuning.json')
            model = TuningBundle_ControlTaskAttach(model, service.catalog, json.loads(bundle.read_text(encoding='utf8')))
        destination = WORK / replica / name
        result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        print(replica, name, result, flush=True)
        key = replica + '-' + name
        (OUT / (key + '-model.json')).write_text(json.dumps(model.Dictionary_Get(), indent=2) + '\n', encoding='utf8')
        (OUT / (key + '-graph.json')).write_text(json.dumps(asdict(SourceGraph_Resolve(model, service.catalog)), indent=2) + '\n', encoding='utf8')
        records.append({'replica': replica, 'name': name, 'project': str(destination / 'Flight_Controller')})
        (OUT / 'projects.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
after = Snapshot_Read()
changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
(OUT / 'source-snapshot.json').write_text(json.dumps({
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'scope': 'Final-source software proof candidates; independent real builds and frozen proof verification required',
    'before': before, 'after': after, 'changed': changed}, indent=2) + '\n', encoding='utf8')
if changed:
    raise RuntimeError('Source changed during generation: ' + repr(changed))
print('PASS: five final-source normal fresh projects; compiler source snapshot unchanged', flush=True)
