"""Compare exact target compiler inputs of fresh Host C and the validated B projects."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
STACK = ROOT / 'docs/evidence/software_completion_20261101/stack/v5'
records = []
for name in ('f407', 'installation'):
    left = ROOT / f'.work/0.1.3-software-completion-20261101/stack/v5/b/{name}/Flight_Controller'
    right = ROOT / f'.work/0.1.3-software-completion-20261101/control/full-host-c/{name}/Flight_Controller'
    graph_b = json.loads((STACK / f'generation-b/b-{name}-graph.json').read_text(encoding='utf8'))
    graph_c = json.loads((HERE / f'full-host-c-generation/{name}-graph.json').read_text(encoding='utf8'))
    names = set(graph_b['sources']) | set(graph_c['sources']) | set(graph_b['asm_sources']) | set(graph_c['asm_sources'])
    names.update(graph_b['virtual_sources'])
    names.update(graph_c['virtual_sources'])
    names.update(graph_b['forced_includes'])
    names.update(graph_c['forced_includes'])
    names.update(('Makefile', 'Generated/project_sources.mk', graph_b['linker_script'], graph_c['linker_script']))
    for directory in set(graph_b['include_dirs']) | set(graph_c['include_dirs']):
        for project in (left, right):
            for path in (project / directory).rglob('*'):
                if path.is_file() and path.suffix.lower() in ('.h', '.hpp'):
                    names.add(path.relative_to(project).as_posix())
    for project in (left, right):
        names.update(path.relative_to(project).as_posix() for path in (project / 'BuildSystem').rglob('*.mk'))
    hashes = {}
    changed = []
    for path in sorted(names):
        a = hashlib.sha256((left / path).read_bytes()).hexdigest() if (left / path).is_file() else None
        b = hashlib.sha256((right / path).read_bytes()).hexdigest() if (right / path).is_file() else None
        hashes[path] = {'b': a, 'c': b}
        if a != b or a is None:
            changed.append(path)
    assert not any(path.startswith('Tests/Host/') for path in graph_c['sources'])
    records.append({'configuration': name, 'graph_equal': graph_b == graph_c,
                    'compared_files_sha256': hashes, 'changed': changed,
                    'scope': 'Exact source graph including flags, all declared C/ASM, target include headers, forced includes, linker and Make inputs; Host-only ABI fixture is not target production code'})
(HERE / 'full-host-c-vs-b.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
print(json.dumps([(row['configuration'], row['graph_equal'], len(row['compared_files_sha256']), row['changed']) for row in records]))
assert all(row['graph_equal'] and not row['changed'] for row in records)
