import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'apps/FCCG/src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope

source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
service = FccgService(ROOT / 'apps/FCCG')
results = []
for name in ['PureINS', 'KF6', 'ESKF15', 'SF6']:
    baseline = ROOT / '.work/SF6_20261001_v1' / (name + '_v8')
    original = service.Project_Open(baseline)
    for layout in ['legacy', 'auto']:
        project = OUT / (name + '_' + layout + '_v1')
        assert not project.exists(), project
        candidate = copy.deepcopy(original)
        candidate.build = replace(candidate.build, memory_layout=layout)
        candidate = service.ProjectConfiguration_Reconcile(candidate).model
        ProjectRoot_Save(candidate, project, create_new=True)
        reopened = service.Project_Open(project)
        generated = TargetGeneration_Apply(reopened, service.catalog, service.policy, project, TargetScope.FLIGHT, confirm_dangerous=True)
        ProjectRoot_Save(reopened, project)
        check = service.Project_Open(project)
        assert check.Dictionary_Get() == reopened.Dictionary_Get()
        flight = project / 'Flight_Controller'
        results.append({'name': name, 'layout': layout, 'source_commit': source_commit, 'project': str(project), 'configuration': check.Dictionary_Get(), 'generated_files': len(generated.file_hashes), 'files': {p.relative_to(flight).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(flight.rglob('*')) if p.is_file()}})
        print('GENERATED', name, layout, flush=True)
(OUT / 'generation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print('COMPLETE', flush=True)
