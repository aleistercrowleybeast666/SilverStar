from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, sys

task = Path(__file__).resolve().parent
wt = Path('D:/python_software/SilverStar/.work/ccdi')
code = json.loads((task / 'backend-code-checkpoint.json').read_text())
assert subprocess.check_output(['git', '-C', str(wt), 'rev-parse', 'HEAD'], text=True).strip() == code['code_commit']
stage = task / 'backend-evidence-final'
assert not stage.exists()
stage.mkdir()
(stage / '.gitattributes').write_text('* -text\n', encoding='utf-8')
summary = json.loads((task / 'backend-build-verification.json').read_text())
gates = json.loads((task / 'nb03-gates.json').read_text())
assert len(gates) == 8 and all(row['exit'] == 0 for row in gates)

def copy(src, dst):
    assert src.is_file(), str(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())

for relative in code['paths']:
    copy(wt / relative, stage / 'source_archive' / relative)
for family, record in summary['families'].items():
    source = Path(record['output'])
    destination = stage / 'final' / family
    paths = ['backend-receipt.json', 'backend-owner.json', 'receipt.json', 'source-snapshot.json',
             'commands.log', 'candidate_config.ssproject', 'Makefile',
             'Generated/native_ground_contract.json', 'Generated/ground_source_graph.json',
             'build/native-artifact-report.json', 'build/native-artifact-vectors.bin',
             'build/native-host/ready_transport_fixture.c']
    for build in ('build', 'build/analysis'):
        paths += [build + '/' + name for name in ('native.elf', 'native.map', 'vectors.bin')]
    paths += [p.relative_to(source).as_posix() for p in source.rglob('*.su')]
    paths += [p.relative_to(source).as_posix() for p in (source / 'build').rglob('*.exe')]
    for path in sorted(set(paths)):
        copy(source / path, destination / path)
    copy(Path(record['project']) / 'SilverStar.ssproject', destination / 'saved-project/SilverStar.ssproject')
    # Archive generated/derived first-party owners, never repeat the complete vendor originals.
    receipt = json.loads((source / 'receipt.json').read_text())
    for path in receipt['experimental_files_sha256']:
        copy(source / path, destination / path)
    (stage / 'facts').mkdir(exist_ok=True)
    (stage / 'facts' / (family + '.json')).write_text(json.dumps(record['facts'], indent=2), encoding='utf-8')
for pattern in ('nb01*', 'nb02*', 'nb03*', 'nbr01*'):
    for source in task.glob(pattern):
        if source.is_file():
            copy(source, stage / 'attempts' / source.name)
for name in ('backend-code-checkpoint.json', 'backend-build-verification.json', 'formal-build-guard-pre-post.json'):
    copy(task / name, stage / 'checks' / name)
for name in ('run_backend_tests.py', 'run_backend_regressions.py', 'run_backend_gates.py',
             'backend_pytest.py', 'reproduce_formal_build_guard.py', 'inspect_backend_evidence.py',
             'package_backend_evidence.py', 'commit_backend_sources.py'):
    copy(task / name, stage / 'runners' / name)
test_paths_plugin = Path('D:/python_software/SilverStar/docs/evidence/nightly_software_20261008/normal_test_paths.py')
copy(test_paths_plugin, stage / 'runners/normal_test_paths.py')
prior_review = Path('C:/Users/chdxm/Documents/Codex/2026-10-09/task-2/runtime-9f-9b-review/review.md')
old = wt / 'apps/SCG/docs/evidence/native_classic_cdc_ground_f407_20261010/verification.json'
report = task / 'NATIVE_CLASSIC_CDC_BACKEND_20261010.md'
verification = {
    'created_utc': datetime.now(timezone.utc).isoformat(), 'code_commit': code['code_commit'],
    'source_baseline': code['baseline'],
    'tested_source': 'nb03 full 28-test suite and both real builds used auditable dirty snapshots based on 9b. All 45 captured modules match raw working files and normalized code_commit blobs. No later report commit rebuild is claimed.',
    'scope': 'Backend API native import -> bound/persisted/reloaded model -> native renderer -> actual ARM/analyzer compile/receipt. Exact F103/F407 candidates; no formal admission, GUI, EP0 repair/review or hardware.',
    'source_changes': code['paths'], 'snapshot_checks': code['snapshot_checks'],
    'families': summary['families'], 'gates': gates,
    'tests': {'nb03': {'passed': 28, 'skipped': 0, 'elapsed_seconds': 233.59,
                      'warning': 'pytest cache_dir config warning; compiler warnings zero'},
              'nbr01': {'passed': 11, 'scope': 'Separate preserved static import/model and ordinary build tooling regressions'},
              'nb02': {'passed': 24, 'scope': 'Intermediate normal backend suite before final guards'},
              'nb01': {'status': 'FAILED_SETUP', 'reason': 'Restricted Windows pytest mode0700 temporary ACL; initial log codec error; no functional pass'}},
    'limits': 'Formal generation BLOCKED. Complete EP0/async lifecycle, manual critical-contract acceptance, call graph/indirect calls/library/recursion, MSP/ISR stack, timing/WCET/hardware NOT PROVEN. b66 platform-stopped review not retried or integrated. Unknown profiles rejected.',
    'prior_review': {'path': str(prior_review), 'sha256': hashlib.sha256(prior_review.read_bytes()).hexdigest(),
                     'scope': 'Parent independent ordinary 9f/9b review passed; not review of new backend code or blocked b66',
                     'manifest_items': 1338, 'git_blobs_including_manifest_itself': 1339},
    'prior_manifest_sha256': hashlib.sha256(old.read_bytes()).hexdigest(),
    'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
    'python_version': sys.version,
    'archive_policy': 'Actual generated/derived first-party owners, receipts/logs/snapshots/config/ELF/map/stack/Host/artifact evidence archived. Full original vendor source and objects remain in fresh C output/cache; original inputs and all listed hashes verified. No vendor source duplication in this evidence.',
    'files': {p.relative_to(stage).as_posix(): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in sorted(stage.rglob('*')) if p.is_file()},
}
(stage / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
print(json.dumps({'stage': str(stage), 'listed_items': len(verification['files']),
                  'total_files_including_verification': len(verification['files']) + 1,
                  'total_bytes': sum(p.stat().st_size for p in stage.rglob('*') if p.is_file()),
                  'manifest_sha256': hashlib.sha256((stage / 'verification.json').read_bytes()).hexdigest()}))
