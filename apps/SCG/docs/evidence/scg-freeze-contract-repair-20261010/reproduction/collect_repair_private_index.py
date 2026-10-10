from pathlib import Path
import json, hashlib

task = Path(__file__).parent
rows = []
unified_outputs = {row['output'] for row in map(json.loads,
    (task/'srb01-build-index.jsonl').read_text().splitlines())}
for path in sorted(Path(r'C:\Users\chdxm\AppData\Local\Temp\srb01').glob('o_*/b/receipt.json')):
    if str(path.parent) in unified_outputs:
        continue
    receipt = json.loads(path.read_text())
    if receipt.get('status') != 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED':
        continue
    if receipt.get('validation_scope') != 'PRIVATE_NATIVE_GROUND_RUNTIME_CANDIDATE':
        continue
    assert receipt['source_commit'] == 'a0afca6a11a9cf7066baf62afecf95fd549c9736'
    root = path.parent
    rows.append({'part': receipt['facts']['part'], 'output': str(root),
        'result': 'CompiledCandidate', 'receipt_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'scope': 'Actual formerly skipped private Native ARM/analyzer regression at srb01; discovered from successful compile receipts, not reconstructed.'})
assert {row['part'] for row in rows} == {'STM32F103C8T6', 'STM32F407VET6'}, rows
(task/'srprivate01-build-index.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
print(json.dumps(rows,indent=2))
