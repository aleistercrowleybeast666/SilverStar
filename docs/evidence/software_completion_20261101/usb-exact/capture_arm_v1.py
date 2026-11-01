"""Archive exact source snapshots, command logs and linked outputs of private builds."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/sc-261101-usb'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


rows = []
for epoch, ordinal, part in (('arm-v1', 0, 'F103'), ('arm-v1', 1, 'F407'),
                             ('arm-v2', 0, 'F103'), ('arm-v2', 1, 'F407'), ('c071-v1', 0, 'C071')):
    project = WORK / epoch / f'o{ordinal}/b'
    compiler = json.loads((project / 'receipt.json').read_text(encoding='utf8'))
    backend = json.loads((project / 'backend-receipt.json').read_text(encoding='utf8'))
    before = epoch == 'arm-v1'
    assert (backend['status'] == 'FailedCandidate') if before else (backend['status'] == 'CompiledCandidate')
    paths = ['receipt.json', 'backend-receipt.json', 'source-snapshot.json', 'commands.log',
             'candidate_config.ssproject', 'Makefile', 'Generated/ground_source_graph.json',
             'Tools/check_power_of_ten.ps1']
    paths += [str(p.relative_to(project)).replace('\\', '/') for p in (project / 'build').rglob('*')
              if p.is_file() and (p.suffix in ('.elf', '.map') or p.name in ('memory-report.json', 'native-artifact-report.json'))]
    paths = [name for name in dict.fromkeys(paths) if (project / name).is_file()]
    archive = HERE / f'{epoch}-{part}-artifacts.zip'
    assert not archive.exists(), str(archive)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for name in paths:
            output.writestr(name, (project / name).read_bytes())
    row = {'epoch': epoch, 'part': part, 'project': str(project), 'status': backend['status'],
           'failure': backend.get('failure'), 'limits': backend.get('limits'),
           'compiler_status': compiler['status'], 'warning_diagnostics': compiler.get('warning_diagnostics'),
           'archive': archive.name, 'archive_sha256': digest(archive),
           'archived_files_sha256': {name: digest(project / name) for name in paths}}
    if not before:
        checks = HERE / 'buildchecks-v1' / part / 'receipt.json'
        values = json.loads(checks.read_text(encoding='utf8'))
        assert len(values['runs']) == 4
        row['emitted_gate_exits'] = {entry['gate']: entry['exit'] for entry in values['runs']}
        row['checks_receipt_sha256'] = digest(checks)
    rows.append(row)
owners = (HERE / 'OWNED_FILES.txt').read_text(encoding='utf8').splitlines()
report = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          'source_identity': 'Exact archived dirty source snapshots and artifacts; no clean-commit claim',
          'final_owned_sources_sha256': {name: digest(ROOT / name) for name in owners},
          'runs': rows, 'hardware': 'No USB connection, flash, physical radio, actuator or motion operation'}
(HERE / 'arm-final-receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
print(json.dumps([(row['epoch'], row['part'], row['status'], row.get('emitted_gate_exits')) for row in rows]))
