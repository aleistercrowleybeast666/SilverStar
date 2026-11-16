"""Ground report presentation uses synthetic identities, never MCU evidence."""
import hashlib
import json
from types import SimpleNamespace

import pytest
from silverstar_fccg.build.quality_batch import TargetQualityResult
from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.project.artifact_stack import (
    ArtifactStackReportSummary_Decode,
    ArtifactStackReportSummary_Encode,
)


def _Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _Report_Write(root, configuration='Release', architecture='cortex_m0plus'):
    from silverstar_fccg.project.artifact_ground_stack import _TOOLS
    build = root / ('build' if configuration == 'Release' else 'build/Debug')
    build.mkdir(parents=True)
    tools = root / 'Tools'
    tools.mkdir()
    for name in _TOOLS | {'software_stack_ssgs_review.md'}:
        (tools / name).write_text('Synthetic presentation identity: ' + name, encoding='utf8')
    elf = build / 'ground.elf'
    elf.write_text('Synthetic ELF identity; not compiled', encoding='utf8')
    document = tools / 'software_stack_ssgs_review.md'
    case = {'name': 'synthetic-ground', 'configuration': configuration, 'compiler': 'fixture',
        'target_profile': 'STM32C071FBP6' if architecture == 'cortex_m0plus' else 'STM32F103C8T6',
        'sources': ['synthetic.c'], 'review_document': 'Tools/' + document.name,
        'review_document_sha256': _Hash_Get(document), 'compiled_artifacts': {'ground.elf': _Hash_Get(elf)}}
    case_file = tools / 'software_stack_cases/synthetic-ground.json'
    case_file.parent.mkdir()
    case_file.write_text(json.dumps(case), encoding='utf8')
    row = {'name': case['name'], 'path': case_file.relative_to(root).as_posix(), 'sha256': _Hash_Get(case_file)}
    index = {'schema': 'silverstar.software-stack-inputs/2', 'review_revision': 'synthetic', 'cases': [row]}
    (tools / 'ground_stack_inputs.json').write_text(json.dumps(index), encoding='utf8')
    msp = {'configured_bytes': 4096, 'main_reset_bytes': 400, 'priority_levels': 4, 'priority_bits': 2,
        'exception_frame_bytes': 36, 'maximum_configurable_handler_bytes': 100, 'fixed_handler_bytes': 0,
        'worst_known_bytes': 1016, 'margin_bytes': 3080, 'passes': True}
    if architecture == 'cortex_m3':
        msp.update(priority_levels=16, priority_bits=4, worst_known_bytes=2648, margin_bytes=1448)
    report = {'schema': 'silverstar.ground-stack-budget/1', 'configuration': configuration,
        'architecture': architecture,
        'compiler': 'fixture', 'elf': elf.relative_to(root).as_posix(), 'elf_sha256': _Hash_Get(elf),
        'checker_sha256': _Hash_Get(tools / 'check_ground_stacks.py'), 'minimum_margin_bytes': 256,
        'source_count': 1, 'su_files': 1, 'whole_program': msp, 'passes': True, 'hardware_tested': False,
        'checks': {'complete_source_and_objects': True, 'all_linked_calls_resolved': True, 'all_vectors_budgeted': True},
        'analysis_tools_sha256': {name: _Hash_Get(tools / name) for name in _TOOLS | {document.name}},
        'software_review': {'case': case['name'], 'revision': 'synthetic', 'document': document.name,
            'document_sha256': _Hash_Get(document), 'case_file': {key: row[key] for key in ('path', 'sha256')}}}
    path = build / 'ground-stack-budget.json'
    path.write_text(json.dumps(report), encoding='utf8')
    return path, report


@pytest.mark.parametrize('configuration', ['Release', 'Debug'])
@pytest.mark.parametrize('architecture,margin', [('cortex_m0plus', 3080), ('cortex_m3', 1448)])
def test_ground_msp_report_is_exact_and_has_no_fabricated_tasks(tmp_path, configuration, architecture, margin):
    path, _ = _Report_Write(tmp_path, configuration, architecture)
    output = 'FIRMWARE_STACK_REPORT|' + str(path)
    summary = ArtifactStackReportSummary_Decode(ArtifactStackReportSummary_Encode(output, tmp_path))
    assert summary['target'] == 'ground' and summary['tasks'] == []
    assert summary['main_msp_exceptions']['margin_bytes'] == margin
    result = BuildResult(BuildAction.STACK_REPORT, ('make', 'stack-report'), 0, output)
    assert TargetQualityResult('ground', tmp_path, None, result, '', 0).succeeded
    assert not TargetQualityResult('flight', tmp_path, None, result, '', 0).succeeded
    assert not TargetQualityResult('ground', tmp_path, None,
        BuildResult(BuildAction.STACK_REPORT, (), 0, 'PASS'), '', 0).succeeded


@pytest.mark.parametrize('change', ['elf', 'checker', 'tool', 'case', 'index', 'review',
    'margin', 'sum', 'frame', 'levels', 'bits', 'check', 'count', 'compiler', 'minimum', 'path', 'config', 'architecture'])
def test_ground_report_rejects_changed_identity_and_inconsistent_bounds(tmp_path, change):
    path, report = _Report_Write(tmp_path)
    files = {'elf': 'build/ground.elf', 'checker': 'Tools/check_ground_stacks.py',
        'tool': 'Tools/ground_stack_runtime.py', 'case': 'Tools/software_stack_cases/synthetic-ground.json',
        'index': 'Tools/ground_stack_inputs.json', 'review': 'Tools/software_stack_ssgs_review.md'}
    if change in files:
        (tmp_path / files[change]).write_text('modified', encoding='utf8')
    if change == 'margin': report['whole_program']['margin_bytes'] += 1
    if change == 'sum': report['whole_program']['worst_known_bytes'] -= 1
    if change == 'frame': report['whole_program']['exception_frame_bytes'] = 108
    if change == 'levels': report['whole_program']['priority_levels'] = 3
    if change == 'bits': report['whole_program']['priority_bits'] = 4
    if change == 'check': report['checks']['all_vectors_budgeted'] = False
    if change == 'count': report['source_count'] = 2
    if change == 'compiler': report['compiler'] = 'different'
    if change == 'minimum': report['minimum_margin_bytes'] = 0
    if change == 'path': report['elf'] = '../outside.elf'
    if change == 'config': report['configuration'] = 'Debug'
    if change == 'architecture': report['architecture'] = 'cortex_m3'
    path.write_text(json.dumps(report), encoding='utf8')
    assert ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path) == ''


def test_ground_gui_displays_msp_scope_and_hides_stale_result(qapp, tmp_path):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.ui.pages.build import BuildPage
    path, report = _Report_Write(tmp_path)
    record = SimpleNamespace(task='stack_report', result='passed', timestamp='', details='', duration=0,
        summary=ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path))
    page = BuildPage(Translator('en_US'))
    page.quality_target_checks['ground'].setChecked(True)
    page.TargetQualityResults_Set('ground', [record], {})
    assert 'No RTOS' in page.target_stack_values['ground'].text()
    assert 'not measured' in page.target_stack_values['ground'].text()
    assert 'MSP / main / ISR' in page.target_stack_details['ground'].text()
    assert '4 configurable IRQ levels' in page.target_stack_details['ground'].text()
    assert '3,080' in page.target_stack_details['ground'].text()
    report['whole_program'].update(configured_bytes=1100, margin_bytes=84, passes=False)
    report['passes'] = False
    path.write_text(json.dumps(report), encoding='utf8')
    record.summary = ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path)
    record.result = 'failed'
    page.TargetQualityResults_Set('ground', [record], {})
    assert 'bound failed' in page.target_stack_values['ground'].text()
    page.TargetQualityResults_Set('ground', [record], {'stack_report': 'stale'})
    assert page.target_stack_details['ground'].text() == ''
    assert page.target_stack_sections['ground'].isHidden()
    page.close()


def test_ground_report_bytes_invalidate_quality_input_hash(tmp_path):
    from silverstar_fccg.project.quality_inputs import QualityInputHash_Get
    from test_target_quality_checks import _Inputs_Create
    target, root, _ = _Inputs_Create(tmp_path)[1]
    with (root / 'Makefile').open('a', encoding='utf8') as stream:
        stream.write('\nstack-report:\n\t@echo synthetic routing only\n')
    report = root / 'build/ground-stack-budget.json'
    report.parent.mkdir()
    report.write_text('before', encoding='utf8')
    old = QualityInputHash_Get(root, target, 'stack_report')
    report.write_text('after', encoding='utf8')
    assert old != QualityInputHash_Get(root, target, 'stack_report')


def test_m3_gui_uses_sixteen_real_priority_levels(qapp, tmp_path):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.ui.pages.build import BuildPage
    path, _ = _Report_Write(tmp_path, architecture='cortex_m3')
    record = SimpleNamespace(task='stack_report', result='passed', timestamp='', details='', duration=0,
        summary=ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path))
    page = BuildPage(Translator('en_US'))
    page.quality_target_checks['ground'].setChecked(True)
    page.TargetQualityResults_Set('ground', [record], {})
    assert '16 configurable IRQ levels' in page.target_stack_details['ground'].text()
    assert '36 B' in page.target_stack_details['ground'].text()
    assert 'Scope' in page.target_stack_details['ground'].text()
    assert 'No RTOS' in page.target_stack_values['ground'].text()
    page.close()


@pytest.mark.parametrize('value', ['[]', 'null', '1', '"text"'])
def test_non_object_summary_is_rejected(value):
    assert ArtifactStackReportSummary_Decode('artifact_stack_v1=' + value) is None
