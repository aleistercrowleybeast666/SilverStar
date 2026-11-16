"""Normal final regeneration of the owned pair; preserve configuration and builds."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save


def Snapshot_Get(folders):
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in folders for p in (ROOT / folder).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def Main_Run():
    work = ROOT / '.work/platform-finish-20261116/boards'
    receipt = work / 'pair-final-synchronization.json'
    if receipt.exists():
        raise ValueError('Preserve prior synchronization evidence')
    source_before = Snapshot_Get(('apps/SCG/src', 'apps/SCG/plugins', 'contracts'))
    project = ROOT / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject'
    old_file_hash = hashlib.sha256(project.read_bytes()).hexdigest()
    service = FccgService(ROOT / 'apps/SCG')
    model = ProjectModel_Load(project)
    before = model.Dictionary_Get()
    model = service.ProjectConfiguration_Reconcile(model).model
    after = model.Dictionary_Get()
    for value in (before, after):
        value.pop('component_locks', None)
    before_json = json.dumps(before, sort_keys=True, ensure_ascii=False)
    after_json = json.dumps(after, sort_keys=True, ensure_ascii=False)
    if before_json != after_json:
        raise ValueError('Reconciliation changed configuration beyond component provenance')
    ProjectModel_Save(model, project, WorkspacePolicy(ROOT / 'apps/SCG'))
    destination = work / 'candidate-o'
    previous = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in destination.rglob('*') if p.is_file() and 'build' not in p.relative_to(destination).parts
                and p.suffix.lower() in ('.c', '.h', '.s', '.ld', '.mk')}
    start = time.monotonic()
    result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(ROOT / 'apps/SCG'), destination, TargetScope.ALL)
    changed_compile = [name for name, digest in previous.items() if not (destination / name).is_file() or
                       hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest]
    source_after = Snapshot_Get(('apps/SCG/src', 'apps/SCG/plugins', 'contracts'))
    changed_source = [name for name in source_before.keys() | source_after.keys()
                      if source_before.get(name) != source_after.get(name)]
    current = {target: ProjectTargetGenerated_IsCurrent(model, service.catalog, destination / directory, target)
               for target, directory in (('flight', 'Flight_Controller'), ('ground', 'Ground_Station'))}
    record = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'hardware_tested': False, 'targets': result.targets, 'seconds': time.monotonic() - start,
        'source_snapshot': source_before, 'changed_source': changed_source, 'compiler_inputs_before': previous,
        'changed_compiler_inputs': changed_compile, 'configuration_unchanged': True,
        'configuration_json_sha256': hashlib.sha256(before_json.encode('utf8')).hexdigest(),
        'example_before_sha256': old_file_hash, 'example_after_sha256': hashlib.sha256(project.read_bytes()).hexdigest(),
        'current_generation': current}
    receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    if changed_source or changed_compile or not all(current.values()):
        raise ValueError('Final synchronization failed source/configuration/current-generation checks')
    print(json.dumps({'changed_source': changed_source, 'changed_compiler_inputs': changed_compile,
                      'current_generation': current, 'seconds': record['seconds']}))


if __name__ == '__main__':
    Main_Run()
