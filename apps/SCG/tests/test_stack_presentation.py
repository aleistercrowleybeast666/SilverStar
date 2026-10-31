"""Report identity and honest scope presentation, using synthetic report inputs."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.build.quality_batch import TargetQualityResult
from silverstar_fccg.project.artifact_stack import (
    ArtifactStackReportSummary_Encode, ArtifactStackReportSummary_Decode)


def _Report_Write(root):
    elf = root / 'build/FCCG/Fixture/Release/fixture.elf'
    checker = root / 'Tools/check_task_stacks.py'
    for artifact in (elf, checker):
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text('synthetic presentation input: ' + artifact.name)
    report = dict(schema='silverstar.stack-budget/1', configuration='Release', compiler='fixture',
        elf=elf.relative_to(root).as_posix(), elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
        checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(), minimum_margin_bytes=256,
        whole_program_stack_acceptance='NOT PROVEN: MSP/main/ISR nesting and hardware margins require separate evidence',
        checks={'all_enabled_tasks_budgeted': True}, passes=True, tasks=[dict(task='Serial',
            configured_bytes=6144, call_chain_bytes=4800, context_bytes=256,
            worst_known_bytes=5056, margin_bytes=1088, passes=True,
            chain=[dict(function='AppTask_Serial', frame_bytes=4800)])])
    path = elf.parent / 'stack-budget.json'
    path.write_text(json.dumps(report), encoding='utf-8')
    return path, report


def test_stack_report_bound_to_exact_elf_and_checker(tmp_path):
    path, source = _Report_Write(tmp_path)
    output = 'FIRMWARE_STACK_REPORT|' + str(path)
    summary = ArtifactStackReportSummary_Encode(output, tmp_path)
    report = ArtifactStackReportSummary_Decode(summary)
    assert report['tasks'] == source['tasks']
    assert ArtifactStackReportSummary_Encode(output, tmp_path / 'other-target') == ''
    assert report['whole_program_stack_acceptance'].startswith('NOT PROVEN:')
    assert report['report_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert ArtifactStackReportSummary_Encode(output + '\n' + output, tmp_path) == ''
    (tmp_path / 'Tools/check_task_stacks.py').write_text('changed checker')
    assert ArtifactStackReportSummary_Encode(output, tmp_path) == ''
    path, source = _Report_Write(tmp_path)
    (tmp_path / source['elf']).write_text('changed ELF')
    assert ArtifactStackReportSummary_Encode(output, tmp_path) == ''


@pytest.mark.parametrize('change', ['margin', 'sum', 'flag', 'check', 'scope', 'traversal', 'bool', 'empty', 'chain', 'configuration'])
def test_inconsistent_or_out_of_root_report_is_rejected(tmp_path, change):
    path, report = _Report_Write(tmp_path)
    if change == 'margin': report['tasks'][0]['margin_bytes'] = 2000
    if change == 'sum': report['tasks'][0]['call_chain_bytes'] = 4000
    if change == 'flag': report['tasks'][0]['passes'] = False
    if change == 'check': report['checks']['all_enabled_tasks_budgeted'] = False
    if change == 'scope': report['whole_program_stack_acceptance'] = 'PASS'
    if change == 'traversal': report['elf'] = '../outside.elf'
    if change == 'bool': report['tasks'][0]['context_bytes'] = True
    if change == 'empty': report['tasks'] = []
    if change == 'chain': report['tasks'][0]['chain'][0]['frame_bytes'] = 4000
    if change == 'configuration': report['configuration'] = 'Debug'
    path.write_text(json.dumps(report), encoding='utf-8')
    assert ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path) == ''


def test_exit_zero_without_verified_report_cannot_pass_batch(tmp_path):
    path, report = _Report_Write(tmp_path)
    def result(output):
        return TargetQualityResult('flight', tmp_path, None,
            BuildResult(BuildAction.STACK_REPORT, ('make', 'stack-report'), 0, output), '', 0)
    assert not result('PASS').succeeded
    output = 'FIRMWARE_STACK_REPORT|' + str(path)
    assert result(output).succeeded
    report['tasks'][0].update(configured_bytes=5000, margin_bytes=-56, passes=False)
    report['passes'] = False
    path.write_text(json.dumps(report), encoding='utf-8')
    assert ArtifactStackReportSummary_Decode(ArtifactStackReportSummary_Encode(output, tmp_path))['passes'] is False
    assert not result(output).succeeded


def test_stack_card_keeps_scope_visible_and_hides_stale_figures(qapp, tmp_path):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.ui.pages.build import BuildPage
    path, _ = _Report_Write(tmp_path)
    summary = ArtifactStackReportSummary_Encode('FIRMWARE_STACK_REPORT|' + str(path), tmp_path)
    record = SimpleNamespace(task='stack_report', summary=summary, result='passed', timestamp='', details='', duration=0)
    page = BuildPage(Translator('en_US'))
    page.TargetQualityResults_Set('flight', [record], {})
    assert 'NOT PROVEN' in page.target_stack_values['flight'].text()
    assert '6,144' in page.target_stack_details['flight'].text()
    assert 'Serial' in page.target_stack_details['flight'].toolTip()
    assert page.target_quality_labels['flight']['stack_report'].property('statusLevel') == 'warning'
    page.TargetQualityResults_Set('flight', [record], {'stack_report': 'stale'})
    assert page.target_stack_details['flight'].text() == ''
    assert page.target_stack_sections['flight'].isHidden()
    page.close()


def test_stack_inputs_include_compiler_stack_products_and_route_real_make_target(tmp_path):
    from test_target_quality_checks import _Inputs_Create
    from silverstar_fccg.build.runner import BuildRunner
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.project.quality_inputs import QualityInputHash_Get
    target, root, model = _Inputs_Create(tmp_path)[0]
    with (root / 'Makefile').open('a', encoding='utf-8') as stream:
        stream.write('\nstack-report:\n\t@echo synthetic routing fixture\n')
    command = BuildRunner(WorkspacePolicy(root)).Command_Get(model, BuildAction.STACK_REPORT)
    assert command[-1] == 'stack-report'
    product = root / 'build/sample.su'
    product.parent.mkdir()
    product.write_text('AppTask_Serial 16 static\n')
    before = QualityInputHash_Get(root, target, 'stack_report')
    source_only = QualityInputHash_Get(root, target, 'stack_report', include_artifacts=False)
    product.write_text('AppTask_Serial 64 static\n')
    assert before != QualityInputHash_Get(root, target, 'stack_report')
    assert source_only == QualityInputHash_Get(root, target, 'stack_report', include_artifacts=False)
    report = product.parent / 'stack-budget.json'
    report.write_text('{"fixture":true}')
    after = QualityInputHash_Get(root, target, 'stack_report')
    report.write_text('{"fixture":false}')
    assert after != QualityInputHash_Get(root, target, 'stack_report')
