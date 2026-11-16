"""Read sealed no-RTOS Ground MSP reports with their exact core architecture."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from silverstar_fccg.core.workspace import WorkspacePolicy, WorkspacePolicyError
from silverstar_fccg.project.stack_manifest import Manifest_Load

_TOOLS = {'check_ground_stacks.py', 'ground_stack_runtime.py', 'ground_stack_runtime_m3.py', 'check_task_stacks.py',
          'stack_arm.py', 'stack_runtime.py', 'stack_review.py', 'stack_manifest.py',
          'ground_stack_inputs.json', 'check_ground.py', 'ground_artifact_contract.py'}
_CHECKS = {'complete_source_and_objects', 'all_linked_calls_resolved', 'all_vectors_budgeted'}
_ARCHITECTURES = {'cortex_m0plus': (2, 4, 'STM32C071FBP6'), 'cortex_m3': (4, 16, 'STM32F103C8T6')}
_MSP = ('configured_bytes', 'main_reset_bytes', 'priority_levels', 'priority_bits',
        'exception_frame_bytes', 'maximum_configurable_handler_bytes', 'fixed_handler_bytes',
        'worst_known_bytes', 'margin_bytes', 'passes')


def GroundStackReportSummary_Validate(value: dict) -> dict | None:
    try:
        if (value['target'] != 'ground' or value['tasks'] != [] or
                value['configuration'] not in {'Release', 'Debug'} or
                type(value['passes']) is not bool or type(value['minimum_margin_bytes']) is not int or
                value['minimum_margin_bytes'] < 256 or type(value['checks']) is not dict or
                set(value['checks']) != _CHECKS or any(type(v) is not bool for v in value['checks'].values())):
            return None
        minimum = value['minimum_margin_bytes']
        bits, levels, _profile = _ARCHITECTURES[value['architecture']]
        msp = value['main_msp_exceptions']
        if (set(msp) != set(_MSP) or any(type(msp[key]) is not int or msp[key] < 0
                for key in _MSP if key not in ('passes', 'margin_bytes')) or
                type(msp['margin_bytes']) is not int or type(msp['passes']) is not bool or
                msp['configured_bytes'] <= 0 or msp['priority_bits'] != bits or
                msp['priority_levels'] != levels or msp['exception_frame_bytes'] != 36):
            return None
        worst = (msp['main_reset_bytes'] + levels * (msp['maximum_configurable_handler_bytes'] + 36)
                 + msp['fixed_handler_bytes'] + 2 * 36)
        if (msp['worst_known_bytes'] != worst or msp['margin_bytes'] != msp['configured_bytes'] - worst or
                msp['passes'] != (msp['margin_bytes'] >= minimum)):
            return None
        passed = all(value['checks'].values()) and msp['passes']
        if (value['passes'] != passed or value['whole_program_stack_acceptance'] !=
                ('SOFTWARE BOUND PASS' if passed else 'SOFTWARE BOUND FAIL')):
            return None
        if (type(value['source_count']) is not int or not 1 <= value['source_count'] <= 4096 or
                value['su_files'] != value['source_count'] or type(value['su_files']) is not int or
                type(value['compiler']) is not str or not 1 <= len(value['compiler']) <= 1024):
            return None
        tools, review = value['analysis_tools'], value['software_review']
        if (type(tools) is not dict or not _TOOLS <= set(tools) or len(tools) != len(_TOOLS) + 1 or
                any(not re.fullmatch(r'[A-Za-z0-9_]+\.(py|json|md)', name) or
                    type(item['path']) is not str or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                    for name, item in tools.items()) or
                any(type(review[key]) is not str or not 1 <= len(review[key]) <= 256
                    for key in ('case', 'revision', 'document', 'document_sha256')) or
                tools[review['document']]['sha256'] != review['document_sha256']):
            return None
        case = review['case_file']
        if (set(case) != {'path', 'sha256'} or
                not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', review['case']) or
                case['path'] != 'Tools/software_stack_cases/' + review['case'] + '.json' or
                not re.fullmatch(r'[0-9a-f]{64}', case['sha256'])):
            return None
        if (type(value['artifacts']) is not dict or set(value['artifacts']) != {'elf', 'checker'} or
                type(value['report_path']) is not str):
            return None
        for digest in (value['report_sha256'], *(item['sha256'] for item in value['artifacts'].values())):
            if type(digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', digest):
                return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


def GroundStackReportSummary_Read(path: Path, expected_root: Path) -> dict | None:
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
        if report['schema'] != 'silverstar.ground-stack-budget/1' or len(raw) > 4 * 1024 * 1024:
            return None
        configuration = report['configuration']
        expected = {'Release': 'build/ground.elf', 'Debug': 'build/Debug/ground.elf'}.get(configuration)
        if report['elf'] != expected or not path.is_absolute():
            return None
        relative = PurePosixPath(expected)
        policy = WorkspacePolicy(expected_root)
        if path.absolute() != policy.Path_Resolve(relative.parent / 'ground-stack-budget.json', allow_root=False):
            return None
        artifacts = {}
        for name, source in (('elf', relative), ('checker', 'Tools/check_ground_stacks.py')):
            resolved = policy.Path_Resolve(source, allow_root=False)
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if digest != report[name + '_sha256']:
                return None
            artifacts[name] = {'path': str(resolved), 'sha256': digest}
        hashes, tools = report['analysis_tools_sha256'], {}
        if type(hashes) is not dict or not _TOOLS <= set(hashes) or len(hashes) != len(_TOOLS) + 1:
            return None
        for name, digest in hashes.items():
            if not re.fullmatch(r'[A-Za-z0-9_]+\.(py|json|md)', name):
                return None
            source = policy.Path_Resolve('Tools/' + name, allow_root=False)
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                return None
            tools[name] = {'path': str(source), 'sha256': digest}
        review = report['software_review']
        manifest = Manifest_Load(expected_root, Path(tools['ground_stack_inputs.json']['path']),
                                 tools['ground_stack_inputs.json']['sha256'])
        cases = [case for case in manifest['cases'] if case['name'] == review['case'] and
                 case['configuration'] == configuration]
        if len(cases) != 1:
            return None
        case = cases[0]
        if (manifest['review_revision'] != review['revision'] or
                case['review_document'] != 'Tools/' + review['document'] or
                case['review_document_sha256'] != review['document_sha256'] or
                case['compiled_artifacts'].get(relative.name) != report['elf_sha256'] or
                case['compiler'] != report['compiler'] or len(case['sources']) != report['source_count'] or
                case['target_profile'] != _ARCHITECTURES[report['architecture']][2] or
                manifest['sealed_case_files'].get(review['case']) != review['case_file']):
            return None
        value = {key: report[key] for key in ('configuration', 'compiler', 'minimum_margin_bytes', 'architecture',
                 'checks', 'passes', 'source_count', 'su_files')}
        value.update(target='ground', tasks=[], report_path=str(path), report_sha256=hashlib.sha256(raw).hexdigest(),
            artifacts=artifacts, analysis_tools=tools, software_review=review,
            main_msp_exceptions={key: report['whole_program'][key] for key in _MSP},
            whole_program_stack_acceptance='SOFTWARE BOUND PASS' if report['passes'] else 'SOFTWARE BOUND FAIL')
        return GroundStackReportSummary_Validate(value)
    except (OSError, ValueError, KeyError, TypeError, WorkspacePolicyError):
        return None
