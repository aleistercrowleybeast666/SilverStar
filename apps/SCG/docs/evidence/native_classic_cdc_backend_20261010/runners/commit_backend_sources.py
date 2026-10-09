from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess
root = Path('D:/python_software/SilverStar/.work/ccdi')
task = Path(__file__).resolve().parent
baseline = '9b9a20be2829dcc5135c648f6dc84b6e9af60316'
paths = ['apps/SCG/' + p for p in ['src/silverstar_fccg/app/native_ground.py',
    'src/silverstar_fccg/app/service.py', 'src/silverstar_fccg/build/native_compile.py',
    'tools/validation/native_classic_cdc_compile.py', 'tests/test_native_ground_backend.py']]
def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').rstrip('\r\n')
assert git('rev-parse', 'HEAD') == baseline
assert not git('diff', '--cached', '--name-only')
assert {line[3:] for line in git('status', '--porcelain=v1').splitlines()} == set(paths)
subprocess.run(['git', '-C', str(root), 'diff', '--check'], check=True)
test = json.loads((task / 'nb03-command.json').read_text())
assert test['exit'] == 0 and '28 passed' in (task / 'nb03.log').read_text()
assert json.loads((task / 'nbr01-command.json').read_text())['exit'] == 0
gates = json.loads((task / 'nb03-gates.json').read_text())
assert len(gates) == 8 and all(g['exit'] == 0 for g in gates)
for path in paths:
    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == test['source_sha256'][path]
subprocess.run(['git', '-C', str(root), 'add', '--', *paths], check=True)
assert set(git('diff', '--cached', '--name-only').splitlines()) == set(paths)
subprocess.run(['git', '-C', str(root), 'commit', '-m',
    'feat(scg): bind native CDC Ground projects to guarded backend pipeline'], check=True)
commit = git('rev-parse', 'HEAD')
assert not git('status', '--porcelain=v1')
verified = []
for line in (task / 'nb03-build-index.jsonl').read_text().splitlines():
    row = json.loads(line)
    snapshot = json.loads((Path(row['output']) / 'source-snapshot.json').read_text())
    for path, item in snapshot['modules'].items():
        rel = 'apps/SCG/' + path.replace('\\', '/')
        working = (root / rel).read_bytes()
        assert hashlib.sha256(working).hexdigest() == item['sha256']
        blob = subprocess.check_output(['git', '-C', str(root), 'show', commit + ':' + rel])
        assert blob.replace(b'\r\n', b'\n') == working.replace(b'\r\n', b'\n')
        assert item['source'].replace('\r\n', '\n') == working.decode('utf-8').replace('\r\n', '\n')
    verified.append({'part': row['part'], 'modules': len(snapshot['modules']),
                     'raw_working_and_normalized_git_match': True})
record = {'finished_utc': datetime.now(timezone.utc).isoformat(), 'baseline': baseline,
          'code_commit': commit, 'paths': paths, 'snapshot_checks': verified,
          'tests': '28 passed; separate preserved-entry/build regression 11 passed',
          'gates': '8/8 exit 0', 'formal_generation': 'BLOCKED', 'clean': True}
(task / 'backend-code-checkpoint.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=True))
