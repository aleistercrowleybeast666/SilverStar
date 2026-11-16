"""Generate the final pair into an empty destination using final owner bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'apps/SCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
from silverstar_fccg.project.model import ProjectModel_Load


def Snapshot_Get(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def Main_Run():
    work = ROOT / '.work/platform-finish-20261116/boards'
    destination = work / 'candidate-p'
    receipt_path = work / 'pair-fresh-generation.json'
    if destination.exists() or receipt_path.exists():
        raise ValueError('Preserve existing generated projects and receipts')
    before = {folder: Snapshot_Get(ROOT / folder) for folder in ('apps/SCG/src', 'apps/SCG/plugins', 'contracts')}
    service = FccgService(ROOT / 'apps/SCG')
    model = ProjectModel_Load(ROOT / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject')
    result = TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(ROOT / 'apps/SCG'), destination, TargetScope.ALL)
    after = {folder: Snapshot_Get(ROOT / folder) for folder in before}
    changed = [folder + '/' + name for folder in before for name in before[folder].keys() | after[folder].keys()
               if before[folder].get(name) != after[folder].get(name)]
    comparisons = {}
    for target in ('Flight_Controller', 'Ground_Station'):
        snapshots = []
        for candidate in ('candidate-o', 'candidate-p'):
            folder = work / candidate / target
            snapshots.append({p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file() and p.relative_to(folder).parts[0] != 'build'
                and p.suffix.lower() in ('.c', '.h', '.s', '.ld', '.mk')})
        comparisons[target] = {'count': len(snapshots[1]), 'changed': [name for name in snapshots[0].keys() | snapshots[1].keys()
            if snapshots[0].get(name) != snapshots[1].get(name)]}
    current = {target: ProjectTargetGenerated_IsCurrent(model, service.catalog, destination / directory, target)
        for target, directory in (('flight', 'Flight_Controller'), ('ground', 'Ground_Station'))}
    receipt = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'target': str(destination), 'normal_generation_targets': result.targets, 'source_snapshot': before,
        'changed_source': changed, 'compile_input_comparison_to_o': comparisons, 'current_generation': current,
        'hardware_tested': False}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    if changed or not all(current.values()) or any(value['changed'] for value in comparisons.values()):
        raise ValueError('Fresh generation source/current/compile-input invariant failed')
    print(json.dumps({'current': current, 'compile_inputs': comparisons, 'changed_source': changed}))


if __name__ == '__main__':
    Main_Run()
