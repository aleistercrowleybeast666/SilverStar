"""Inventory the small public handoff; never copy generated firmware or old runs."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
names = ['.gitattributes', 'REPORT_ZH.md', 'RESOURCE_SUMMARY.md', 'resource-summary.json',
         'capability-v6-receipt.json', 'validation-scopes.json',
         'python-environment.txt', 'code-stage-list.json', 'final-code-stage-list.json']
for stem in ('scg-final-v2', 'scg-runtime-v2', 'scg-resource-v1', 'entry-v3', 'layout-v3',
             'flp-v3', 'flp-contract-v1', 'native-v2', 'gshc-full-v5', 'capability-v6'):
    names.extend((stem + '.log', stem + '.exit'))
for folder in ('ss-tm-wire-v1', 'gui-offscreen-125-v8', 'gui-offscreen-150-v8'):
    names.extend(path.relative_to(HERE).as_posix() for path in (HERE/folder).iterdir() if path.is_file())
rows = []
for name in sorted(names):
    path = HERE/name
    assert path.is_file() and path.resolve().is_relative_to(HERE)
    rows.append(dict(path=name, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
receipt = json.loads((HERE/'capability-v6-receipt.json').read_text(encoding='utf-8'))
result = dict(schema='silverstar.public-evidence-selection/1',
    source_relative_root='docs/evidence/treediagram_20261101',
    receiver_code_commit=receipt['code_commit'],
    note='Original source and complete historical success/failure logs remain in the separately committed SilverStar evidence directory. This selection contains summaries, final logs, wire evidence and real Qt offscreen images; no generated firmware. The copying repository should add the actual SilverStar evidence commit to its provenance manifest after that commit exists.',
    files=rows, total_bytes=sum(row['bytes'] for row in rows))
(HERE/'public-copy-list.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(f"{len(rows)} files, {result['total_bytes']} bytes")
