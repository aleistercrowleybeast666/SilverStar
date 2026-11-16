"""Summarize completed receipts only; no generated source or build mutation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / '.work/platform-finish-20261116/boards'
DEST = Path(__file__).resolve().parent


def Load(relative):
    return json.loads((WORK / relative).read_text(encoding='utf8'))


def Main_Run():
    if (DEST / 'receipt.json').exists():
        raise ValueError('Preserve prior final receipt')
    gates = []
    for name, path, count in (
            ('SSFC H743 fresh P', 'candidate-p-Flight_Controller-final-validation/receipt.json', 12),
            ('SSGS C071 fresh P', 'ssgs-current-validation/receipt.json', 14),
            ('F103 E19 Ground D', 'm3-d-validation/receipt.json', 14)):
        value = Load(path)
        if len(value['commands']) != count or not value['inputs_unchanged'] or any(row['exit_code'] for row in value['commands']):
            raise ValueError('Incomplete actual gate receipt: ' + path)
        gates.append({'target': name, 'receipt': path, 'gate_count': count, 'inputs_unchanged': True,
            'commands': [{key: row[key] for key in ('argv', 'config', 'gate', 'exit_code', 'seconds', 'log_sha256')}
                         for row in value['commands']]})
    packages = []
    for location in ('dist/pf1117-boards-current/delivery-receipt.json', 'dist/pf1117-boards/delivery-receipt.json'):
        value = json.loads((ROOT / location).read_text(encoding='utf8'))
        for row in value['packages']:
            if not row['readback_all_sha256_equal']:
                raise ValueError('Package independent readback incomplete')
            packages.append({**row, 'recommended_pair': 'Current.zip' in row['zip'],
                'historical_pair': row['zip'].endswith('SSFC1_0_SSGS1_0.zip')})
    generation = Load('pair-fresh-generation.json')
    current = Load('current-staged-readonly.json')
    original = Load('staged-readonly.json')
    f103 = next(row for row in original['targets'] if row['target'] == 'F103 E19 reference')
    workflows = {name: Load(path) for name, path in (
        ('SSGS P', 'ssgs-workflow-current/receipt.json'), ('F103 D', 'm3-workflow-final/receipt.json'))}
    if any(not row['batch_succeeded'] or row['exit_code'] or not row['current_generation'] or
           not row['persistence_roundtrip'] or not row['stale_hides_budget'] for row in workflows.values()):
        raise ValueError('Actual quality consumer incomplete')
    inventory = Load('duplicate-build-inventory.json')
    cleanup_path = DEST.parent / 'delivery/board-duplicate-cleanup.json'
    cleanup = json.loads(cleanup_path.read_text(encoding='utf8'))
    if not cleanup['complete'] or cleanup['skipped'] or cleanup['deleted_files'] != inventory['candidate_count']:
        raise ValueError('Root actual cleanup receipt is incomplete')
    index = DEST / 'runs/index.json'
    receipt = {'source_commit': '6fed5b639d0835de7874a74db25a63ab0da814ad', 'hardware_tested': False,
        'normal_fresh_generation': {key: generation[key] for key in ('changed_source', 'compile_input_comparison_to_o', 'current_generation')},
        'actual_gates': gates, 'packages': packages, 'fresh_pair_staged_readonly': current,
        'f103_staged_readonly': f103, 'quality_consumers': workflows,
        'regression': {'m3_ground_flight_presentation_reference_selection': '100 passed in 23.66s; m3-tests-final-a.log',
            'new_h7_tick_irq_host_selection': '2 passed; tick-host.log; prior text/route failure retained',
            'git_clean_blob_smudge': '148 paths exact; git-bytes-final.json',
            'c0_vendor_provenance': '84 selected SDK source files SHA equal; vendor-provenance-check.json'},
        'formal_text_evidence': {'index': 'runs/index.json', 'sha256': hashlib.sha256(index.read_bytes()).hexdigest(),
            'format': 'gzip JSON preserves each original text record and raw SHA; products remain in dist'},
        'cleanup': {'candidate_inventory_files': inventory['candidate_count'], 'candidate_inventory_bytes': inventory['candidate_bytes'],
            'retained_files': inventory['retained_count'], 'retained_bytes': inventory['retained_bytes'],
            'deleted_files': cleanup['deleted_files'], 'deleted_bytes': cleanup['deleted_bytes'], 'skipped': cleanup['skipped'],
            'execution_owner': 'root; see ../delivery/board-duplicate-cleanup.json and board-duplicate-cleanup-verification.json'},
        'limitations': ['Source-authority verification is not verification of the separately packaged EXE authority.',
            'Whole-firmware critical-contract audit remains NOT PROVEN; exact stack acceptance is limited to sealed cases.',
            'Qt screenshots and BuildPage tests are offscreen; native application display acceptance is reported separately.',
            'PCB, wiring, clock, power, RF, sensor calibration, WCET, high-water stack and flight performance require hardware evidence.']}
    (DEST / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(json.dumps({'gates': sum(row['gate_count'] for row in gates), 'packages': len(packages),
        'fresh_current_reports': len(current['targets']), 'hardware_tested': False}))


if __name__ == '__main__':
    Main_Run()
