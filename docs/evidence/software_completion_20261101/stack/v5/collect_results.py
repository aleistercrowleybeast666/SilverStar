"""Preserve B gate reports and summarize actual results without changing inputs."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v5/b'
OUT = HERE / 'reports-b'


def Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Load(name):
    return json.loads((HERE / name).read_text(encoding='utf8'))


if __name__ == '__main__':
    builds = Load('build-b/commands.json')
    comparisons = Load('build-b/raw-byte-comparison.json')
    gates = Load('gates-b/commands.json')
    negatives = Load('negatives-b/commands.json')
    regression = Load('formal-stack-regression.json')
    assert len(builds) == 20 and all(row['exit_code'] == 0 for row in builds)
    assert len(comparisons) == 10 and all(row['passes'] for row in comparisons)
    assert len(gates) == 25 and all(row['exit_code'] == 0 for row in gates)
    assert len(negatives) == 9 and negatives[0]['exit_code'] == negatives[-1]['exit_code'] == 0
    assert all(row['exit_code'] != 0 and row['restored'] for row in negatives[1:-1])
    assert regression['exit_code'] == 0 and regression['before'] == regression['after']
    OUT.mkdir(exist_ok=False)
    resources = []
    coverage = []
    inventory = []
    for name in ('f407', 'installation', 'h743', 'pid', 'lqr'):
        project = WORK / name / 'Flight_Controller'
        model = json.loads((project / 'SilverStar.ssproject').read_text(encoding='utf8'))
        profile = model['build']['target_profile']
        for config in ('Release', 'Debug'):
            build = project / 'build/FCCG' / profile / config
            reports = {}
            for filename in ('memory-report.json', 'stack-budget.json'):
                source = build / filename
                destination = OUT / (name + '-' + config + '-' + filename)
                shutil.copyfile(source, destination)
                reports[filename] = json.loads(destination.read_text(encoding='utf8'))
                inventory.append({'source': str(source), 'evidence': str(destination.relative_to(HERE)),
                                  'sha256': Hash_Get(destination), 'bytes': destination.stat().st_size})
            stack = reports['stack-budget.json']
            memory = reports['memory-report.json']
            assert stack['passes'] and stack['whole_program_stack_acceptance'] == 'SOFTWARE BOUND PASS'
            assert stack['elf_sha256'] == memory['artifacts']['elf']['sha256']
            assert stack['minimum_margin_bytes'] == 256 and not memory['errors']
            resources.append({'case': name, 'configuration': config, 'target_profile': profile,
                'elf_sha256': stack['elf_sha256'], 'software_stack_acceptance': stack['whole_program_stack_acceptance'],
                'minimum_task_margin_bytes': min(row['margin_bytes'] for row in stack['tasks']),
                'tasks': stack['tasks'], 'main_msp_exceptions': stack['main_msp_exceptions'],
                'control_task': stack['runtime_proofs']['control_task'],
                'regions': [{key: region[key] for key in (
                    'name', 'used_bytes', 'allocated_span_bytes', 'review_budget_bytes', 'budget_free_bytes',
                    'physical_capacity_bytes', 'physical_free_bytes', 'reserved_bytes')}
                    for region in memory['regions']],
                'hardware_high_water_marks': stack['hardware_high_water_marks'],
                'artifact_report_stack_field': memory['stack_proof']})
        makefile = (project / 'Makefile').read_text(encoding='utf8')
        patterns = re.search(r'^FIRST_PARTY_C_SOURCES := \$\(filter (.+),\$\(C_SOURCES\)\)$', makefile, re.M)[1].split()
        manifest = json.loads((project / 'Tools/software_stack_inputs.json').read_text(encoding='utf8'))
        case = next(item for item in manifest['cases'] if item['name'] == name + '-Release')
        expected = sorted(source for source in case['sources'] if any(
            source.startswith(pattern[:-1]) if pattern.endswith('%') else source == pattern for pattern in patterns))
        log = HERE / 'gates-b' / (name + '-Release-static-analysis.log')
        lines = log.read_text(encoding='utf8').splitlines()
        compiled = sorted({match[1] for line in lines if '-fanalyzer' in line and ' -c ' in line and
                           (match := re.search(r' ([^ ]+\.c) -o ', line))})
        missing = sorted(set(expected) - set(compiled))
        extra = sorted(set(compiled) - set(expected))
        assert not missing and not extra and expected
        analysis = project / 'build/FCCG' / profile / 'StaticAnalysis/Release'
        analysis_elf = next(analysis.glob('*.elf'))
        coverage.append({'case': name, 'emitted_makefile_sha256': Hash_Get(project / 'Makefile'),
            'analyzer_log': str(log.relative_to(HERE)), 'analyzer_log_sha256': Hash_Get(log),
            'expected_first_party_sources': expected, 'actual_fanalyzer_sources': compiled,
            'missing': missing, 'extra': extra, 'analyzer_elf_sha256': Hash_Get(analysis_elf),
            'passes': True})
    source_state = subprocess.check_output(['git', 'status', '--porcelain', '--', 'apps/SCG', 'contracts'],
                                           cwd=ROOT, text=True).splitlines()
    summary = {'schema': 'silverstar.software-stack-delivery/1',
        'source_commit': Load('generation-b/source-snapshot.json')['head'],
        'source_state_at_collection': source_state,
        'formal_stack_regression': {'receipt': 'formal-stack-regression.json',
            'exit_code': regression['exit_code'], 'file_count': len(regression['before']),
            'seconds': regression['seconds'], 'log_sha256': regression['log_sha256']},
        'scope': 'Five exact generated models, Release and Debug, fixed compiler installation and reviewed inputs; no universal project approval.',
        'normal_arm_builds': 10, 'artifact_checks': 10, 'raw_independent_comparisons': 10,
        'emitted_architecture_checks': 5, 'emitted_power10_text_checks': 5,
        'real_arm_fanalyzer_builds': 5, 'strict_software_stack_checks': 10,
        'negative_rejections': 7, 'negative_restored_positive': True,
        'all_formal_build_and_gate_commands_exit_zero': True,
        'whole_program_stack_acceptance': 'SOFTWARE BOUND PASS',
        'fixed_task_context_bytes': 256, 'fixed_minimum_spare_bytes': 256,
        'f407_sram_review_budget_bytes': 102400,
        'limits': ['Exact cases only; changed parameters, model names, source/header/build/toolchain identities require separate review.',
                   'Power10 text exit zero is not complete rule or critical-contract acceptance.',
                   'Generic memory artifact report stack_proof stays NOT_PROVEN; separate matched-ELF strict stack reports establish this software bound.',
                   'No measured MCU stack high-water mark, WCET, interrupt latency, RF, electrical or flight qualification.',
                   'Full emitted Host results are recorded separately, including the initial B old-layout fixture failure.',
                   'An early gate-driver launch refused missing raw-byte-comparison prerequisite before running any gates; final-gates.log preserves that startup failure.'],
        'raw_byte_comparison': [{'case': row['name'], 'configuration': row['config'],
                                'artifacts_per_build': len(row['artifacts'][0]), 'changed': row['changed'],
                                'passes': row['passes']} for row in comparisons],
        'reports': inventory}
    (HERE / 'resource-summary.json').write_text(json.dumps(resources, indent=2) + '\n', encoding='utf8')
    (HERE / 'analyzer-coverage.json').write_text(json.dumps(coverage, indent=2) + '\n', encoding='utf8')
    (HERE / 'final-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in summary.items() if key not in ('reports', 'raw_byte_comparison')}, indent=2))
