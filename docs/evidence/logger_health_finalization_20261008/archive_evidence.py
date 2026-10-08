from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

repo = Path.cwd()
source = Path(__file__).resolve().parent
target = repo / 'docs/evidence/logger_health_finalization_20261008'
target.mkdir(parents=True, exist_ok=True)

def copy_exact(original, destination):
    if destination.exists():
        assert destination.read_bytes() == original.read_bytes(), 'Never overwrite differing evidence'
    else:
        shutil.copyfile(original, destination)
names = ['generate.py', 'run_gates.py', 'run_pytest.py', 'review_callbacks.py',
         'generation_plan.json', 'generation_result.json', 'generated_input_manifest.json',
         'artifact_identity.json', 'versions.json', 'manual_review.json',
         'source_diff.patch', 'extra_binding_proposal_initial.json',
         'prior_session_identity_limits.json', 'callback_review.json',
         'callback_focus_disassembly.txt', 'baseline_disassembly.log',
         'candidate_disassembly.log', 'pytest.log', 'pytest_normal_v2.log',
         'pytest_normal_v2.xml', 'pytest_normal_v2_result.json', 'processes_after_gates.json']
for step in ['architecture', 'power10', 'release', 'stack', 'analyzer', 'host']:
    names.extend([step + '.log', step + '_result.json'])
for name in names:
    copy_exact(source / name, target / name)
for directory in ['red', 'red_valid_fixture', 'green_owner', 'green_generated', 'source_snapshot']:
    for path in (source / directory).rglob('*'):
        if path.is_file() and path.suffix in ('.c', '.py', '.ps1', '.log', '.json'):
            relative = path.relative_to(source)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_exact(path, destination)
copy_exact(repo / '.work/bench08c_f407/SilverStar.ssproject', target / 'reference_config.ssproject')
copy_exact(source / 'project/SilverStar.ssproject', target / 'generated_config.ssproject')
copy_exact(source / 'project/KF6_Static_20261008_f045d8c.ssdecoder', target / 'candidate.ssdecoder')
copy_exact(repo / 'docs/evidence/nightly_software_20261008/normal_test_paths.py', target / 'normal_test_paths.py')
inputs = ['apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c',
          'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py',
          'apps/SCG/tests/fixtures/logger_health_boundary.c',
          'apps/SCG/tests/logger_health_boundary_support.py',
          'apps/SCG/tests/test_logger_health_boundary.py']
source_record = {}
for relative in inputs:
    path = repo / relative
    source_record[relative] = dict(raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  normalized_sha256=hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest())
    destination = target / 'repository_inputs' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy_exact(path, destination)
(target / 'source_revision.json').write_text(json.dumps(dict(
    base_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    compiled_dirty_patch_sha256=hashlib.sha256((source / 'source_diff.patch').read_bytes()).hexdigest(),
    owner_and_test_inputs=source_record,
    note='Commit verification compares normalized source text; evidence files remain byte exact via -text. No self-referential commit identity.'), indent=2), encoding='utf-8')
copy_exact(Path(__file__), target / 'archive_evidence.py')
print(str(target))
