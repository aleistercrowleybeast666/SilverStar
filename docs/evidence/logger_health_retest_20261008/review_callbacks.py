"""Read-only source/linked graph comparison; never bypasses the stack gate."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

repo = Path.cwd()
output = Path(__file__).resolve().parent
new = output / 'project/Flight_Controller'
old = repo / '.work/bench08c_f407/Flight_Controller'
objdump = 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-objdump.exe'
artifact = 'build/FCCG/SilverStar_F407/Release/auto/SilverStar_0_1_1.elf'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def parse(root, label):
    argv = [objdump, '-d', str(root / artifact)]
    result = subprocess.run(argv, capture_output=True, timeout=30)
    (output / (label + '_disassembly.log')).write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0
    rows = {}
    for line in result.stdout.decode().splitlines():
        match = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if match:
            name = match[1]
            rows[name] = []
        else:
            match = re.match(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{4,8}\s+)+(\S+)\s*(.*)', line)
            if match:
                rows[name].append((match[1], match[2]))
    edges = {}
    indirect = {}
    for name, instructions in rows.items():
        edges[name] = set()
        for op, args in instructions:
            target = re.search(r'<([^>+]+)(?:\+[^>]+)?>', args)
            if ((op.startswith('b') or op in ('cbz', 'cbnz')) and target and
                (target[1] != name or op in ('bl', 'bl.w', 'blx')) and target[1] in rows):
                edges[name].add(target[1])
            if ((op == 'blx' and '<' not in args) or
                (op.startswith('bx') and args.strip() != 'lr')):
                indirect.setdefault(name, []).append([op, args])
    return rows, edges, indirect, dict(argv=argv, exit_code=result.returncode,
                                     elf_sha256=digest(root / artifact))

old_rows, old_edges, old_indirect, old_identity = parse(old, 'baseline')
new_rows, new_edges, new_indirect, new_identity = parse(new, 'candidate')
manifest = (new / 'Generated/project_sources.mk').read_text(encoding='utf-8')
block = re.search(r'(?ms)^C_SOURCES \+= \\\n(.*?)(?:\n\n|\Z)', manifest)
sources = [line.strip().removesuffix('\\').strip() for line in block[1].splitlines()]
source_changes = []
for relative in sources:
    previous = (old / relative).read_text(encoding='utf-8')
    current = (new / relative).read_text(encoding='utf-8')
    if previous != current:
        source_changes.append(relative)
delta = {name: dict(added=sorted(new_edges.get(name, set()) - old_edges.get(name, set())),
                   removed=sorted(old_edges.get(name, set()) - new_edges.get(name, set())))
         for name in sorted(set(old_edges) | set(new_edges))
         if old_edges.get(name, set()) != new_edges.get(name, set())}
focus = ['AppTask_Estimator', 'Estimator_HealthEventsPublish',
         'LoggerBus_FinalizationStateGet', 'PlatformCritical_Enter', 'PlatformCritical_Exit']
(output / 'callback_focus_disassembly.txt').write_text(
    '\n'.join(f'{label} {name}\n' + '\n'.join(op + ' ' + args for op, args in rows.get(name, []))
              for label, rows in [('baseline', old_rows), ('candidate', new_rows)]
              for name in focus), encoding='utf-8')
record = dict(scope='Independent read-only raw linked graph/source comparison. No binding override, callback resolution or task-stack acceptance.',
              old=old_identity, candidate=new_identity, compiled_sources=len(sources),
              changed_compiled_source_text=source_changes, direct_edge_delta=delta,
              indirect_sites_changed=old_indirect != new_indirect,
              indirect_sites_baseline=old_indirect, indirect_sites_candidate=new_indirect,
              focus_direct_calls={name: sorted(new_edges.get(name, set())) for name in focus},
              focus_indirect={name: new_indirect.get(name, []) for name in focus},
              review='Only four added source lines. No callback table, function-pointer assignment, recursion or allocation added. New getter restores IRQ state before returning; snapshot-to-push race remains ordinary failure. Full task/library/ISR bounds remain NOT_PROVEN until unmodified gate is legitimately run.',
              stack_gate_exit=json.loads((output / 'stack_result.json').read_text())['exit_code'],
              binding_authorized=True,
              review_boundary='Raw graph comparison does not substitute for original stack gate; see stack_result.json for executed gate')
(output / 'callback_review.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({key:record[key] for key in ('compiled_sources', 'changed_compiled_source_text',
                                            'direct_edge_delta', 'indirect_sites_changed', 'focus_direct_calls')}, indent=2))
