"""Exercise the real generated Ground make target through existing GUI consumers.

The Qt page is rendered offscreen. This verifies report ingestion/persistence and
display assertions; it is not a manual desktop usability or hardware test.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys


def Main_Run():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo / 'apps/SCG/src'))
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase
    from silverstar_fccg.build.quality_batch import QualityBatch_Run
    from silverstar_fccg.build.runner import BuildAction
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.core.task import TaskContext
    from silverstar_fccg.project.artifact_stack import ArtifactStackReportSummary_Decode, ArtifactStackReportSummary_Encode
    from silverstar_fccg.project.model import ProjectModel_Load
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.project.generation_state import ProjectTargetGenerated_IsCurrent
    from silverstar_fccg.project.quality_results import QualityResult_Save, QualityResults_Load
    from silverstar_fccg.ui.pages.build import BuildPage
    root = args.project.resolve(strict=True)
    if args.output.exists():
        raise ValueError('Do not overwrite prior workflow evidence')
    args.output.mkdir(parents=True)
    model = deepcopy(ProjectModel_Load(args.model or repo / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject'))
    assert ProjectTargetGenerated_IsCurrent(model, FccgService(repo / 'apps/SCG').catalog, root, 'ground')
    model.build = model.ground_target.build
    model.build.tool_paths.update(make='D:/msys64/ucrt64/bin/mingw32-make.exe',
        compiler='D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe', python=sys.executable)
    lines = []
    batch = QualityBatch_Run((('ground', root, model),), BuildAction.STACK_REPORT,
                             TaskContext(line_callback=lines.append))
    (args.output / 'quality-events.log').write_text('\n'.join(lines) + '\n', encoding='utf8')
    outcome = batch.targets[0]
    if not batch.succeeded:
        raise AssertionError('Actual QualityBatch stack check failed: ' + outcome.error)
    summary = ArtifactStackReportSummary_Encode(outcome.result.output, root)
    value = ArtifactStackReportSummary_Decode(summary)
    assert value['target'] == 'ground' and value['tasks'] == [] and value['passes']
    record = QualityResult_Save(root, task='stack_report', succeeded=outcome.succeeded,
        duration=outcome.duration, summary=summary, input_sha256=outcome.input_sha256,
        command=outcome.result.command, details=outcome.result.output)
    assert record in QualityResults_Load(root)
    app = QApplication.instance() or QApplication([])
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    if font_path.is_file():
        if QFontDatabase.addApplicationFont(str(font_path)) < 0:
            raise AssertionError('Available CJK font could not be loaded for offscreen evidence')
        app.setFont(QFont('Microsoft YaHei', 9))
    page = BuildPage(Translator('zh_CN'))
    page.quality_target_checks['ground'].setChecked(True)
    page.TargetQualityResults_Set('ground', [record], {})
    page.target_stack_sections['ground'].toggle_button.setChecked(True)
    page.resize(1280, 800)
    page.show()
    app.processEvents()
    label = page.target_stack_values['ground'].text()
    detail = page.target_stack_details['ground'].text()
    assert '无 RTOS' in label and '未实测' in label and 'MSP / main / ISR' in detail
    assert f"{value['main_msp_exceptions']['margin_bytes']:,}" in detail
    page.grab().save(str(args.output / 'ground-stack-page.png'))
    page.TargetQualityResults_Set('ground', [record], {'stack_report': 'stale'})
    assert page.target_stack_sections['ground'].isHidden() and page.target_stack_details['ground'].text() == ''
    page.close()
    receipt = {'hardware_tested': False, 'gui_backend': 'Qt offscreen; no native mouse test',
        'batch_succeeded': batch.succeeded, 'command': outcome.result.command,
        'exit_code': outcome.result.return_code, 'input_sha256': outcome.input_sha256,
        'report_sha256': value['report_sha256'], 'main_msp_exceptions': value['main_msp_exceptions'],
        'display': label, 'current_generation': True, 'persistence_roundtrip': True, 'stale_hides_budget': True,
        'logs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir()}}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    Main_Run()
