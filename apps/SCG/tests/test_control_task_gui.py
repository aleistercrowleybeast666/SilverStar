"""Controller task scheduling is an explicit opt-in at the existing bundle UI."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.tuning_bundle import TuningBundle_Digest
from silverstar_fccg.ui.main_window import MainWindow


@pytest.mark.parametrize('decision', ('cancel', 'parameters_only', 'task', 'wrong_period'))
def test_bundle_import_has_explicit_task_choice(qapp, workspace_root, tmp_path, monkeypatch, decision):
    service = FccgService(workspace_root)
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._toolchain_checked = True
    window._model = service.ReferenceProject_Create('control options')
    window._Project_Refresh()
    source = Path(__file__).parent/'fixtures/tuning_bundle_v1/kf6-pid.sstuning.json'
    value = json.loads(source.read_text(encoding='utf8'))
    if decision == 'wrong_period':
        value['control_research']['parameters']['sample_period_s'] = .02
        value['content_sha256'] = TuningBundle_Digest(value)
        source = tmp_path/'20ms.sstuning.json'
        source.write_text(json.dumps(value), encoding='utf8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args: (str(source), 'TreeDiagram bundle (*.sstuning.json)'))
    before = deepcopy(window._model.Dictionary_Get())
    errors, seen = [], []
    window._Error_Show = lambda *args: errors.append(args)
    def preview(*_args, **kwargs):
        option = kwargs['check_box']
        assert option is not None and not option.isChecked()
        assert option.isEnabled() == (decision != 'wrong_period')
        assert window._model.Dictionary_Get() == before
        if decision == 'task': option.setChecked(True)
        seen.append(True)
        return QMessageBox.StandardButton.Cancel if decision == 'cancel' else QMessageBox.StandardButton.Apply
    window._MessageBox_Exec = preview
    window._ParameterProfile_Import('silverstar.algorithm.estimator.kf6')
    assert seen and not errors, errors
    controllers = [row for row in (window._model.mission_functions or {}).get('functions', [])
                   if row['instance_id'] == 'controller']
    if decision == 'task':
        assert len(controllers) == 1
        assert controllers[0]['output'] == 'control.research.command'
        assert controllers[0]['depends_on'] == ['estimator']
        assert 'silverstar.algorithm.control.pid' in window._model.base_components
    else:
        assert not controllers
        assert 'silverstar.algorithm.control.pid' not in window._model.base_components
    if decision == 'cancel': assert window._model.Dictionary_Get() == before
    window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
    window.close()
