"""Actual import command uses strict Preview and one final publication."""
from copy import deepcopy
import json

from PySide6.QtWidgets import QMessageBox

from test_three_workspace_workflow import workspace_window, _Events_Flush
from silverstar_fccg.project.function_parameters import ParameterProfile_Build
from silverstar_fccg.project.tuning_bundle import TuningBundle_Digest


def test_bundle_preview_cancel_and_apply_preserve_owner_boundary(workspace_window, tmp_path, qapp, monkeypatch):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Bundle GUI')
    window._Project_Refresh()
    owner = window._model.strategies['ins']
    profile = ParameterProfile_Build(window._model, window._service.catalog, owner)
    next(row for row in profile['parameters'] if row['id'] == 'mechanization_aggregation')['value'] = 1
    value = dict(schema_id='silverstar.tuning-bundle/1', schema_version=1,
        model_id='synthetic-gui-model', run_id='synthetic-gui-run',
        coordinates='ENU; body+Z; Hamilton-wxyz; q_nb', implementation_identity='0'*64,
        profiles=[profile], control_research=None, limitations=['Synthetic software fixture.'], content_sha256='')
    value['content_sha256'] = TuningBundle_Digest(value)
    path = tmp_path/'parameters.sstuning.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr('silverstar_fccg.ui.main_window.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    before = deepcopy(window._model.Dictionary_Get())
    previews = []
    def Preview(*args, **kwargs):
        previews.append(kwargs['details'])
        return QMessageBox.StandardButton.Cancel
    window._MessageBox_Exec = Preview
    window.workflow_page.coverage.Function_Select('ins')
    assert window.workflow_page.function_buttons['import'].isEnabled()
    window.workflow_page.function_buttons['import'].click()
    assert window._model.Dictionary_Get() == before
    assert 'mechanization_aggregation' in previews[0]
    assert window._translator.Text_Get('workflow.import.research_control') in previews[0]
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Apply
    window.workflow_page.function_buttons['import'].click()
    _Events_Flush(qapp)
    expected = deepcopy(before)
    expected['algorithm_parameters'][owner]['mechanization_aggregation'] = 1
    assert window._model.Dictionary_Get() == expected
    assert not errors


def test_bundle_invalid_digest_does_not_open_apply_or_modify_project(workspace_window, tmp_path, monkeypatch):
    window, errors = workspace_window
    path = tmp_path/'bad.sstuning.json'
    path.write_text('{"schema_id":"silverstar.tuning-bundle/1"}', encoding='utf-8')
    monkeypatch.setattr('silverstar_fccg.ui.main_window.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    before = deepcopy(window._model.Dictionary_Get())
    window._MessageBox_Exec = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Invalid bundle reached Apply'))
    window._ParameterProfile_Import('unused')
    assert errors and window._model.Dictionary_Get() == before
