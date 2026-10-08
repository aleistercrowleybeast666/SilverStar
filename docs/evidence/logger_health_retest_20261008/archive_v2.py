from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

repo = Path.cwd()
source = Path(__file__).resolve().parent
target = repo / 'docs/evidence/logger_health_retest_20261008'
assert not target.exists()
target.mkdir(parents=True)
for path in source.iterdir():
    if path.is_file() and path.suffix in ('.py', '.json', '.log', '.patch', '.txt', '.gdb', '.xml') and path.name != 'active_gate.json':
        shutil.copyfile(path, target / path.name)
for directory in ['hardware_preflight','hardware_program','hardware_startup','hardware_post','health_fixed','source_snapshot']:
    base = source / directory
    if not base.exists(): continue
    for path in base.rglob('*'):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
for path in (source / 'pytest_normal_v2').rglob('*'):
    if path.is_file() and path.suffix in ('.log', '.json', '.c') and any(part in ('boundary', 'health') for part in path.parts):
        destination = target / 'focused_pytest' / path.relative_to(source / 'pytest_normal_v2')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
project = source / 'project/Flight_Controller'
shutil.copyfile(repo / '.work/bench08c_f407/SilverStar.ssproject', target / 'reference_config.ssproject')
shutil.copyfile(source / 'project/SilverStar.ssproject', target / 'generated_config.ssproject')
shutil.copyfile(source / 'project/KF6_Static_20261008_f045d8c.ssdecoder', target / 'candidate.ssdecoder')
shutil.copyfile(project / 'build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.bin', target / 'candidate.bin')
shutil.copyfile(project / 'build/FCCG/SilverStar_F407/Release/auto/stack-budget.json', target / 'stack-budget.json')
shutil.copyfile(repo / 'docs/evidence/nightly_software_20261008/normal_test_paths.py', target / 'normal_test_paths.py')
shutil.copyfile(repo / 'docs/evidence/logger_health_finalization_20261008/verify_archive.py', target / 'verify_archive.py')
inputs = ['apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c',
          'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py',
          'apps/SCG/tests/fixtures/logger_health_boundary.c',
          'apps/SCG/tests/logger_health_boundary_support.py',
          'apps/SCG/tests/test_logger_health_boundary.py', 'apps/GSHC/app.py']
source_record = {}
for relative in inputs:
    path = repo / relative
    source_record[relative] = dict(raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  normalized_sha256=hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest())
    destination = target / 'repository_inputs' / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, destination)
(target / 'source_revision.json').write_text(json.dumps(dict(
    base_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    compiled_dirty_patch_sha256=hashlib.sha256((source / 'source_diff.patch').read_bytes()).hexdigest(),
    owner_and_test_inputs=source_record,
    scope='Only authorized exact V11 binding added to baseline four-line fix. Final commit source verified by normalized hash; formal evidence uses -text.'), indent=2), encoding='utf-8')
files = {path.relative_to(target).as_posix():dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
         for path in sorted(target.rglob('*')) if path.is_file() and path.name != 'manifest.json'}
(target / 'manifest.json').write_text(json.dumps(dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='Exact authorized source proof, complete fresh software gates, actual Flight program/readback and single GSHC mission 51. TF file acceptance NOT_RUN.',
    files=files), indent=2), encoding='utf-8')
print(len(files), sum(item['bytes'] for item in files.values()))
