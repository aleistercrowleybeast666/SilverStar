from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, subprocess
task = Path(__file__).resolve().parent
root = Path('D:/python_software/SilverStar/.work/ccdi')
rows = [json.loads(line) for line in (task / 'nb03-build-index.jsonl').read_text().splitlines()]
result = {'created_utc': datetime.now(timezone.utc).isoformat(),
          'code_commit': json.loads((task / 'backend-code-checkpoint.json').read_text())['code_commit'],
          'families': {}}
for row in rows:
    family = 'f103' if row['part'] == 'STM32F103C8T6' else 'f407'
    out = Path(row['output'])
    receipt = json.loads((out / 'receipt.json').read_text())
    backend = json.loads((out / 'backend-receipt.json').read_text())
    assert receipt['status'] == 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert backend['status'] == 'CompiledCandidate'
    assert all(command['exit'] == 0 for command in receipt['commands'])
    for path, expected in receipt['output_artifact_sha256'].items():
        assert hashlib.sha256((out / path).read_bytes()).hexdigest() == expected
    for path, expected in receipt['experimental_files_sha256'].items():
        assert hashlib.sha256((out / path).read_bytes()).hexdigest() == expected
    sdk = Path(receipt['facts']['irq_evidence_source'])
    assert hashlib.sha256(sdk.read_bytes()).hexdigest() == receipt['facts']['irq_header_sha256']
    irq_text = re.sub(r'/\*.*?\*/|//[^\r\n]*', '', sdk.read_text(encoding='utf-8-sig'), flags=re.S)
    irq = dict((name, int(value)) for name, value in re.findall(r'(?m)^\s*(\w+_IRQn)\s*=\s*(-?\d+)\s*(?=,|\})', irq_text))
    assert irq == dict(receipt['facts']['irq_numbers'])
    if family == 'f407':
        assert irq['FPU_IRQn'] == 81
    original = Path('C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation/cube-' + family + '-usb')
    for path, expected in receipt['input_sha256'].items():
        assert hashlib.sha256((original / path).read_bytes()).hexdigest() == expected
    elfs = {build: hashlib.sha256((out / build / 'native.elf').read_bytes()).hexdigest()
            for build in ('build', 'build/analysis')}
    baseline = json.loads((root / 'apps/SCG/docs/evidence/native_classic_cdc_ground_f407_20261010/verification.json').read_text())
    result['families'][family] = {
        'part': row['part'], 'output': str(out), 'project': row['project'],
        'snapshot': row['snapshot_root'], 'compile_commands': len(receipt['commands']),
        'c_sources': len(receipt['graph']['sources']), 'startup_asm_sources': len(receipt['graph']['asm_sources']),
        'compiler_warnings': receipt['warning_diagnostics'],
        'toolchain_version': receipt['toolchain_version'],
        'generated_hashes_checked': len(receipt['experimental_files_sha256']),
        'artifact_hashes_checked': len(receipt['output_artifact_sha256']),
        'original_native_hashes_checked': len(receipt['input_sha256']),
        'independent_sdk': str(sdk), 'independent_sdk_sha256': receipt['facts']['irq_header_sha256'],
        'independent_irq_enumerators': len(irq), 'fpu_final_enumerator': irq.get('FPU_IRQn'),
        'runtime_model_sha256': receipt['runtime_model_sha256'],
        'backend_model_sha256': backend['model_sha256'], 'elf_sha256': elfs,
        'elf_matches_14e_baseline': elfs == baseline['families'][family]['elf_sha256'],
        'facts': receipt['facts'], 'formal_generation': 'BLOCKED',
    }
    assert receipt['runtime_model_sha256'] == backend['model_sha256']
(task / 'backend-build-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({family: {k: v for k, v in item.items() if k in
    {'compile_commands','c_sources','startup_asm_sources','generated_hashes_checked','artifact_hashes_checked',
     'independent_irq_enumerators','elf_sha256','elf_matches_14e_baseline','runtime_model_sha256'}}
    for family, item in result['families'].items()}, indent=2))
