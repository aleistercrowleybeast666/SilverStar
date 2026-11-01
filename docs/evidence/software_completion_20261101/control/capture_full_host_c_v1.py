"""Summarize two complete emitted Host runs without combining partial runs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from generate_full_host_c import ROOT, HERE, WORK


def Sha256_Read(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


output = HERE / 'full-host-c-summary.json'
assert not output.exists(), 'Preserve an existing formal receipt'
summaries = []
for label in ('f407', 'installation'):
    receipt_path = HERE / f'full-host-c-{label}.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf8'))
    log_path = HERE / f'full-host-c-{label}.log'
    log = log_path.read_text(encoding='utf8')
    assert receipt['exit'] == 0
    assert receipt['changed_generated_sources'] == []
    assert receipt['changed_control_or_plugin_contract_sources'] == []
    assert receipt['log_sha256'] == Sha256_Read(log_path)
    matches = re.findall(r'^SilverStar host summary: executables=(\d+) checks=(\d+) '
        r'failures=(\d+) compile_pass_cases=(\d+) expected_compile_failures=(\d+) '
        r'not_applicable=(\d+)\s*$', log, re.MULTILINE)
    assert len(matches) == 1 and 'All SilverStar host tests passed.' in log
    values = dict(zip(('executables', 'checks', 'failures', 'compile_pass_cases',
        'expected_compile_failures', 'not_applicable'), map(int, matches[0])))
    assert values['failures'] == 0
    reasons = [line for line in log.splitlines() if line.startswith('FCCG_HOST_NOT_APPLICABLE|')]
    assert len(reasons) == values['not_applicable']
    warnings = [line for line in log.splitlines() if 'warning:' in line]
    storage_done = re.findall(r'^FCCG_PROGRESS\|STORAGE_INTEGRITY\|DONE\|\d+\|4\|(.+)$',
        log, re.MULTILINE)
    storage_done = [item.strip() for item in storage_done]
    assert storage_done == ['compile', 'byte-integrity', 'logger-compile', 'logger-integrity']
    project = WORK / label / 'Flight_Controller'
    executables = {path.relative_to(project).as_posix(): Sha256_Read(path)
        for path in sorted((project / 'build/FCCG/Host').rglob('*.exe'))}
    assert executables
    summaries.append({'configuration': label, **values,
        'elapsed_seconds': receipt['elapsed_seconds'], 'not_applicable_reasons': reasons,
        'compiler_warning_lines': warnings,
        'storage_completed_steps': storage_done,
        'log_sha256': Sha256_Read(log_path), 'receipt_sha256': Sha256_Read(receipt_path),
        'owning_diff_during_run': receipt['changed_owning_sources'],
        'produced_host_executables_sha256': executables})

record = {'source_commit': 'e7c42b7c4971fddb02c6d5c60864b50dffaa3f1a',
    'source_epoch': 'That commit plus the exact Host-only test_interfaces.c fixture diff captured by full-host-c-generation/source-snapshot.json',
    'fixture_sha256': Sha256_Read(ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_interfaces.c'),
    'generation_snapshot_sha256': Sha256_Read(HERE / 'full-host-c-generation/source-snapshot.json'),
    'target_input_comparison_sha256': Sha256_Read(HERE / 'full-host-c-vs-b.json'),
    'compiler_version': subprocess.check_output(['D:/msys64/ucrt64/bin/gcc.exe', '--version'], text=True),
    'powershell_version': subprocess.check_output(['powershell', '-NoProfile', '-Command',
        '$PSVersionTable.PSVersion.ToString()'], text=True).strip(),
    'runs': summaries,
    'scope': 'Each configuration ran its complete emitted Host command once to completion; no selected-pass stitching. These default/installation models have control disabled. Actual producer tests and disabled-adapter integration are included; enabled PID/LQR task evidence is the separate complete task-v7b execution. Logical Host ports, not physical hardware.',
    'storage_scope': 'Mandatory emitted storage integrity tail included in each original complete log; it is not folded into the runner counted checks.',
    'not_proven': ['whole-program critical-contract acceptance', 'hardware timing/WCET',
        'electrical actuator behavior', 'physical flight qualification']}
output.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(json.dumps([{key: run[key] for key in ('configuration', 'executables', 'checks',
    'failures', 'compile_pass_cases', 'expected_compile_failures', 'not_applicable')}
    for run in summaries]), flush=True)
