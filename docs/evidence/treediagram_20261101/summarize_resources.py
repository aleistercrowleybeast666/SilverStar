"""Derive resource percentages and margins from retained linked reports."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Main():
    cases = []
    for batch in ('firmware-v1', 'bundle-firmware-v1'):
        commands = json.loads((HERE / batch / 'commands.json').read_text())
        for project in json.loads((HERE / batch / 'projects.json').read_text()):
            name = project['name']
            root = HERE / batch / (name + '-retained')
            reports = list(root.rglob('memory-report.json'))
            assert len(reports) == 1, (name, reports)
            source = reports[0]
            data = json.loads(source.read_text())
            banks = []
            for original in data['regions']:
                bank = {key: value for key, value in original.items() if key != 'sections'}
                used, capacity = bank['used_bytes'], bank['physical_capacity_bytes']
                assert bank['physical_free_bytes'] == capacity - used
                assert abs(bank['used_percent'] - used * 100 / capacity) < 1e-8
                if bank['review_budget_bytes'] is not None:
                    assert bank['budget_free_bytes'] == bank['review_budget_bytes'] - used
                bank['tail_after_allocated_span_bytes'] = bank['linker_capacity_bytes'] - bank['allocated_span_bytes']
                banks.append(bank)
            gates = {row['name'][len(name) + 1:]: row['exit_code'] for row in commands
                     if row['name'].startswith(name + '-') and
                     row['name'][len(name) + 1:] in ('all', 'architecture-check', 'power10-check',
                         'static-analysis', 'artifact-check', 'host-tests', 'stack-report')}
            cases.append(dict(name=name, mcu=data['mcu'], source=str(source.relative_to(HERE)),
                source_sha256=Hash(source), artifacts=data['artifacts'],
                generation_input_sha256=data.get('generation_input_sha256'), gates=gates,
                stack_status='strict command FAIL' if gates.get('stack-report') else
                    'task estimate only' if 'stack-report' in gates else 'no full stack gate',
                whole_program_stack='NOT PROVEN', regions=banks))
    h7_root = HERE.parent / 'h7_storage_20261101/v6'
    source = h7_root / 'memory-report.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    banks = []
    for original in data['regions']:
        bank = {key: value for key, value in original.items() if key != 'sections'}
        assert bank['physical_free_bytes'] == bank['physical_capacity_bytes'] - bank['used_bytes']
        assert abs(bank['used_percent'] - bank['used_bytes'] * 100 / bank['physical_capacity_bytes']) < 1e-8
        bank['tail_after_allocated_span_bytes'] = bank['linker_capacity_bytes'] - bank['allocated_span_bytes']
        banks.append(bank)
    commands = json.loads((h7_root/'commands.json').read_text(encoding='utf-8'))
    gates = {row['command'][-1]: row['exit_code'] for row in commands}
    gates['storage_integrity_runner'] = json.loads((h7_root/'h743-storage-host-command.json').read_text(encoding='utf-8'))['exit_code']
    cases.append(dict(name='h743-owned-v6', mcu=data['mcu'],
        source='../h7_storage_20261101/v6/memory-report.json', source_sha256=Hash(source),
        code_commit=json.loads((h7_root/'source-snapshot.json').read_text(encoding='utf-8'))['git_head_at_generation'],
        artifacts=data['artifacts'], generation_input_sha256=data['generation_input_sha256'],
        gates=gates, host_scope='complete storage_integrity runner; not full generated make host-tests',
        stack_status='strict command FAIL' if gates['stack-report'] else 'task estimate only',
        whole_program_stack='NOT PROVEN', regions=banks))
    for source in sorted((HERE / 'native-resources').glob('*/report.json')):
        data = json.loads(source.read_text())
        banks = []
        for original in data['regions']:
            capacity, used = original['capacity_bytes'], original['used_bytes']
            reserved = sum(row['bytes'] for row in original['sections']
                           if 'heap_stack' in row['name'])
            banks.append(dict(name=original['name'], used_bytes=used,
                physical_capacity_bytes=capacity, physical_free_bytes=capacity-used,
                used_percent=100*used/capacity, free_percent=100*(capacity-used)/capacity,
                allocated_span_bytes=original['allocated_span_bytes'],
                tail_after_allocated_span_bytes=original['tail_bytes_after_last_section'],
                review_budget_bytes=None, budget_free_bytes=None, budget_used_percent=None,
                reserved_bytes=reserved, reserved_included_in_used=True))
        cases.append(dict(name='native-private-' + data['part'], mcu=data['part'],
            source=str(source.relative_to(HERE)), source_sha256=Hash(source),
            artifacts=data['artifacts'], gates={'release_admission': 'BLOCKED'},
            stack_status='reserved linker bytes only', whole_program_stack='NOT PROVEN', regions=banks))
    result = dict(scope='linked section bytes, including load copies and explicit reservations; no hardware measurement',
        caveats=['Unallocated banks and summed free bytes are not a contiguous allocation guarantee.',
                 'Physical free bytes and review-budget free bytes are different limits.',
                 'No unused RAM value establishes dynamic stack safety; strict stack failures remain failures.',
                 'null review budget means none recorded for this bank, never an inferred budget.'], cases=cases)
    (HERE/'resource-summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    lines = ['# Linked memory resource summary', '', *result['caveats'], '',
        '| Case / MCU | Bank | Used / physical bytes | Used % | Physical free bytes (%) | Review budget / free bytes | Reserved in used | Allocated span / tail | Stack |',
        '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for case in cases:
        for bank in case['regions']:
            budget = ('—' if bank['review_budget_bytes'] is None else
                      f"{bank['review_budget_bytes']} / {bank['budget_free_bytes']}")
            lines.append(f"| {case['name']} / {case['mcu']} | {bank['name']} | {bank['used_bytes']} / {bank['physical_capacity_bytes']} | "
                f"{bank['used_percent']:.3f}% | {bank['physical_free_bytes']} ({bank['free_percent']:.3f}%) | {budget} | "
                f"{bank['reserved_bytes']} | {bank['allocated_span_bytes']} / {bank['tail_after_allocated_span_bytes']} | "
                f"{case['stack_status']}; whole program NOT PROVEN |")
    (HERE/'RESOURCE_SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps([dict(name=row['name'], gates=row['gates']) for row in cases], indent=2))


if __name__ == '__main__':
    Main()
