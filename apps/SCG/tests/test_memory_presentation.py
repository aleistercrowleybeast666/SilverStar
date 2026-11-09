"""Present exact report banks and invalidate changed artifacts; no MCU evidence."""
import hashlib
import json
from types import SimpleNamespace

from silverstar_fccg.project.artifact_memory import (
    ArtifactMemoryReportSummary_Encode, ArtifactMemoryReportSummary_Decode)


def _Report_Write(tmp_path, target='flight'):
    artifacts = {}
    for name in ('elf', 'map', 'linker', 'contract'):
        path = tmp_path / name
        path.write_text('test fixture ' + name)
        artifacts[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    regions = []
    for name, capacity, used, budget in (('FLASH', 786432, 307200, None),
                                        ('DTCMRAM', 131072, 110000, 114688),
                                        ('RAM_D2', 294912, 1000, None)):
        regions.append(dict(name=name, physical_capacity_bytes=capacity, used_bytes=used,
            physical_free_bytes=capacity-used, allocated_span_bytes=used, reserved_bytes=1024,
            review_budget_bytes=budget, budget_free_bytes=None if budget is None else budget-used,
            linker_capacity_bytes=capacity, linker_free_bytes=capacity-used))
    report = dict(schema='silverstar.memory-report/1', target=target, mcu='fixture MCU',
                  generation_input_sha256='b'*64, regions=regions, artifacts=artifacts,
                  errors=[], stack_proof='NOT_PROVEN')
    path = tmp_path / 'memory-report.json'
    path.write_text(json.dumps(report), encoding='utf-8')
    return path, report


def test_report_snapshot_keeps_each_bank_and_rejects_changed_elf(tmp_path):
    path, report = _Report_Write(tmp_path)
    output = 'FIRMWARE_MEMORY_REPORT|' + str(path)
    summary = ArtifactMemoryReportSummary_Encode(output, tmp_path)
    value = ArtifactMemoryReportSummary_Decode(summary)
    assert value['regions'] == report['regions']
    assert ArtifactMemoryReportSummary_Encode(output, tmp_path / 'other-target') == ''
    assert ArtifactMemoryReportSummary_Encode(output, tmp_path, 'ground') == ''
    assert value['stack_proof'] == 'NOT_PROVEN'
    (tmp_path / 'elf').write_text('rebuilt after report')
    assert ArtifactMemoryReportSummary_Encode(output, tmp_path) == ''
    assert ArtifactMemoryReportSummary_Encode(output + '\n' + output, tmp_path) == ''


def test_resource_card_shows_all_target_banks_and_stale_state(qapp, tmp_path):
    from silverstar_fccg.ui.pages.build import BuildPage
    from silverstar_fccg.core.i18n import Translator
    path, _report = _Report_Write(tmp_path, 'ground')
    summary = ArtifactMemoryReportSummary_Encode('FIRMWARE_MEMORY_REPORT|' + str(path), tmp_path, 'ground')
    record = SimpleNamespace(task='artifact_check', summary=summary, result='passed', timestamp='', details='', duration=0)
    page = BuildPage(Translator('en_US'))
    page.quality_target_checks['ground'].setChecked(True)
    page.TargetQualityResults_Set('ground', [record], {})
    assert all(name in page.ground_memory_value.text() for name in ('FLASH', 'DTCMRAM', 'RAM_D2'))
    assert '786,432' in page.ground_memory_value.text()
    assert '4,688' in page.ground_memory_value.text()
    assert 'Build source: configuration not recorded' in page.ground_memory_value.text()
    assert 'elf / map' in page.ground_memory_value.text()
    assert page.ground_memory_value.property('statusLevel') == 'error'  # Budget margin < 10%, even with more physical RAM.
    assert 'DTCMRAM' not in page.memory_margin_value.text()
    page.TargetQualityResults_Set('ground', [record], {'artifact_check': 'stale'})
    assert 'DTCMRAM' not in page.ground_memory_value.text()
    assert page.ground_memory_value.property('statusLevel') == 'warning'
    page.close()
