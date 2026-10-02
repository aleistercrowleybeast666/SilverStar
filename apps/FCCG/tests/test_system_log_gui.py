"""Synthetic checker output verifies presentation/export, not firmware safety."""
import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QFileDialog, QPlainTextEdit, QPushButton

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow


@pytest.mark.parametrize('critical_failure', (False, True))
def test_system_log_shows_current_findings_and_blocks_stale_export(
    qapp, tmp_path: Path, workspace_root: Path, monkeypatch, critical_failure,
):
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=FccgService(workspace_root))
    errors = []
    monkeypatch.setattr(window, '_Error_Show', lambda *args: errors.append(args))
    monkeypatch.setattr(window, '_MessageBox_Exec', lambda *_args, **_kwargs: None)
    root = tmp_path/'project'
    flight = root/'Flight_Controller'
    source = flight/'APP/fixture.c'
    source.parent.mkdir(parents=True)
    source.write_text('void Fixture(int value) { (void)value; }\n', encoding='utf-8')
    (flight/'Tools').mkdir()
    (flight/'Tools/check_power_of_ten.ps1').write_text('# GUI fixture; not executed\n', encoding='utf-8')
    (flight/'Makefile').write_text('# GUI fixture; not executed\n', encoding='utf-8')
    (flight/'SilverStar.ssproject').write_text(json.dumps(window._model.Dictionary_Get()), encoding='utf-8')
    window._project_root = root
    output = ('POWER10_RULE5|Flight|functions=2|eligible_assertions=1|\n'
              'POWER10_RULE5_FUNCTION|Flight|APP/fixture.c|1|Fixture|11|0\n'
              'POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending\n')
    if critical_failure:
        output += 'POWER10_CONTRACT_REVIEW|FAIL|unchecked_recovery\n'
    try:
        # A critical-contract FAIL must remain red even with exit code zero.
        window._Build_Complete(BuildResult(BuildAction.POWER10_CHECK, (), 0, output))
        label = window.build_page.quality_result_labels['power10_check']
        assert label.property('statusLevel') == ('error' if critical_failure else 'info')
        assert bool(errors) is critical_failure
        window.system_log_button.click()
        dialog = window._system_log_dialog
        assert dialog.isVisible()
        text = dialog.findChild(QPlainTextEdit, 'systemLogOutput').toPlainText()
        assert 'Fixture' in text and str(source.resolve()) in text
        assert 'NOT_PROVEN' in text and 'full_path,file,line' in text
        window.system_log_button.click()
        assert window._system_log_dialog is dialog
        export = dialog.findChild(QPushButton, 'systemLogExport')
        assert export.isEnabled()
        destination = tmp_path/'review.csv'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(destination), 'CSV')):
            export.click()
        rows = list(csv.DictReader(destination.read_text(encoding='utf-8-sig').splitlines()))
        row = next(row for row in rows if row['function'] == 'Fixture')
        assert row['full_path'] == str(source.resolve()) and row['line'] == '1'
        original = destination.read_bytes()
        source.write_text('/* changed after scan */\n', encoding='utf-8')
        window._Power10Report_Export()
        assert errors[-1][0] == window._translator.Text_Get('power10.report_stale')
        assert destination.read_bytes() == original
    finally:
        window._project_state = type(window._project_state).DRAFT
        window.close()
        qapp.processEvents()
