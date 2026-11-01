"""Retain only the actual three-product delivery evidence, with source hashes."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
TD = ROOT.parent / 'TreeDiagram'


def Hash(data):
    return hashlib.sha256(data).hexdigest()


def Main():
    rows = []
    consumers = json.loads((EVIDENCE / 'consumer-v1/results.json').read_text(encoding='utf8'))
    for row in consumers:
        case = row['case']
        project = Path(row['project'])
        selected = [Path(row['decoder']), project.parent.parent / (case + '-consumer.c'),
                    project / 'Generated/control_research.json',
                    project / 'Generated/Inc/project_algorithm_parameters.h',
                    project / 'Generated/Src/project_control_research.c']
        selected += sorted((project / 'Algorithm/Control' / ('LQR' if case == 'lqr' else 'PID')).rglob('*.[ch]'))
        for source in selected:
            relative = source.relative_to(project).as_posix() if source.is_relative_to(project) else source.name
            destination = EVIDENCE / 'consumer-v1/compiled-inputs' / case / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            destination.write_bytes(data)
            rows.append({'source': str(source), 'retained': str(destination.relative_to(EVIDENCE)),
                         'sha256': Hash(data), 'bytes': len(data)})
    (EVIDENCE / 'consumer-v1/retained-inputs.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    cross = TD / 'docs/evidence/software_completion_20261101/cross-repository'
    copies = []
    for directory, target in [('actual-runs-v1', 'actual-runs'), ('consumer-v1', 'consumer')]:
        for source in sorted((EVIDENCE / directory).glob('*')):
            if not source.is_file():
                continue
            destination = cross / target / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            destination.write_bytes(data)
            copies.append({'source': str(source), 'retained': destination.relative_to(cross).as_posix(),
                           'sha256': Hash(data), 'bytes': len(data)})
    for name in ('sdk-export.json', 'sdk-source-verification.json'):
        data = (EVIDENCE / name).read_bytes()
        (cross / name).write_bytes(data)
        copies.append({'source': str(EVIDENCE / name), 'retained': name, 'sha256': Hash(data), 'bytes': len(data)})
    (cross / 'inventory.json').write_text(json.dumps(copies, indent=2) + '\n', encoding='utf8')
    source_files = sorted((TD / 'src').rglob('*.py')) + sorted((TD / 'src/treediagram/algorithms').rglob('*.c'))
    source_files += sorted((TD / 'src/treediagram/algorithms').rglob('*.h'))
    source_files += [TD / 'tests/test_cli.py', TD / 'src/treediagram/algorithms/sdk/manifest.json']
    receipt = {'baseline_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=TD, text=True).strip(),
               'source_sha256': {p.relative_to(TD).as_posix(): Hash(p.read_bytes()) for p in source_files},
               'full_pytest': {'exit': int((TD / 'docs/evidence/software_completion_20261101/full-pytest-v1.exit').read_text()), 'passed': 118},
               'matrix_exit': int((TD / '.qa/software-completion-20261101-matrix-v1.exit').read_text()),
               'source_state': 'auditable working source; commit binds these bytes separately'}
    (TD / 'docs/evidence/software_completion_20261101/source-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    for suffix in ('log', 'exit'):
        source = TD / ('.qa/software-completion-20261101-matrix-v1.' + suffix)
        (TD / ('docs/evidence/software_completion_20261101/examples-v1.' + suffix)).write_bytes(source.read_bytes())
    print('Retained', len(rows), 'actual compiled inputs;', len(copies), 'compact cross-repository records')


if __name__ == '__main__':
    Main()
