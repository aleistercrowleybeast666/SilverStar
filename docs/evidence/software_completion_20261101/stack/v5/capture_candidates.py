"""Capture complete unadmitted A inputs after each successful real build."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
OUT = EVIDENCE / 'inspection-a'
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v5/a'
spec = importlib.util.spec_from_file_location('candidate_review', EVIDENCE.parent / 'v3/inspect_case.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
TOOLS = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools'
NAMES = ('check_task_stacks.py', 'stack_arm.py', 'stack_runtime.py', 'stack_review.py',
         'software_stack_inputs.json', 'software_stack_review.md')

def Snapshot_Get():
    return {name: hashlib.sha256((TOOLS / name).read_bytes()).hexdigest() for name in NAMES}

OUT.mkdir(exist_ok=False)
before = Snapshot_Get()
pending = [(name, config) for name in ('f407', 'installation', 'h743', 'pid', 'lqr')
           for config in ('Release', 'Debug')]
results = []
deadline = time.monotonic() + 3600
while pending:
    path = EVIDENCE / 'build-a/commands.json'
    try:
        records = json.loads(path.read_text(encoding='utf8')) if path.exists() else []
    except json.JSONDecodeError:
        time.sleep(1)
        continue
    ready = next((case for case in pending if any(tuple(row['case']) == ('a', *case)
        and (row['command'][-1] == 'artifact-check' or row['exit_code']) for row in records)), None)
    if ready is None:
        if time.monotonic() > deadline:
            raise TimeoutError('Bounded wait for real candidate builds exhausted')
        time.sleep(5)
        continue
    name, config = ready
    pending.remove(ready)
    try:
        if any(row['exit_code'] for row in records if tuple(row['case']) == ('a', name, config)):
            raise ValueError('Candidate build/artifact gate failed; no inspection acceptance')
        report = review.Inspect_Run(WORK / name / 'Flight_Controller', config, name + '-' + config)
        report['tool_hashes'] = before
        if Snapshot_Get() != before:
            raise ValueError('Proof tool/document changed during candidate capture')
        if not report['diagnostic_msp']['passes']:
            raise ValueError('Actual candidate MSP bound fails its unchanged margin')
        if any(row['configured'] - row['budget'][0] - row['context'] < 256
               for row in report['diagnostic_tasks'].values()):
            raise ValueError('Actual candidate task bound fails its unchanged margin')
    except Exception:
        report = {'not_acceptance': True, 'error': traceback.format_exc()}
    filename = name + '-' + config + '.json'
    (OUT / filename).write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    results.append({'case': ready, 'output': filename, 'captured': 'error' not in report})
    (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf8')
    print(name, config, report.get('error', 'captured; not admitted'), flush=True)
(OUT / 'tool-snapshot.json').write_text(json.dumps({'before': before, 'after': Snapshot_Get()}, indent=2) + '\n', encoding='utf8')
raise SystemExit(int(not all(row['captured'] for row in results)))
