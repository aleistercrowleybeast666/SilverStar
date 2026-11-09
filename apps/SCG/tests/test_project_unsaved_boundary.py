"""Applied configuration and private drafts survive actual close/open decisions."""
from copy import deepcopy

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from silverstar_fccg.ui.main_window import MainWindow
from test_three_workspace_workflow import workspace_window, _Events_Flush


def _SavedProject_Open(window, tmp_path):
    model = window._service.ReferenceProject_Create('UnsavedBoundary')
    root = tmp_path / 'project'
    window._service.ProjectRoot_Save(model, root)
    window._Project_Open(root)
    return root / 'SilverStar.ssproject'


def _Configuration_Change(window):
    owner = window._model.strategies['ins']
    result = window._ProjectConfiguration_Change(
        lambda model: model.algorithm_parameters[owner].__setitem__('gravity_mps2', 9.79))
    assert result is not None


def _Close_Click(window, answer, qapp):
    """Use real modal buttons; no mocked dialog result or dangling singleShot."""
    observed = []
    timer = QTimer(window)
    timer.setInterval(10)
    def Respond():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            observed.append(dialog.text())
            dialog.button(answer).click()
    timer.timeout.connect(Respond)
    window.show()
    _Events_Flush(qapp)
    window._MessageBox_Exec = MainWindow._MessageBox_Exec.__get__(window)
    timer.start()
    try:
        accepted = window.close()
    finally:
        timer.stop()
        timer.deleteLater()
    _Events_Flush(qapp)
    return accepted, observed


@pytest.mark.parametrize('answer', [QMessageBox.StandardButton.Cancel,
    QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Save])
def test_applied_model_close_uses_real_save_discard_cancel(workspace_window, tmp_path, qapp, answer):
    window, errors = workspace_window
    path = _SavedProject_Open(window, tmp_path)
    original = path.read_bytes()
    _Configuration_Change(window)
    changed = deepcopy(window._model.Dictionary_Get())
    accepted, observed = _Close_Click(window, answer, qapp)
    assert observed, 'Applied configuration must be protected by a real close confirmation'
    assert window._model.Dictionary_Get() == changed
    if answer == QMessageBox.StandardButton.Save:
        assert accepted and not window.isVisible()
        assert window._service.Project_Open(path).Dictionary_Get() == changed
        assert not window._ProjectFile_DirtyGet()
    else:
        assert path.read_bytes() == original
        assert accepted == (answer == QMessageBox.StandardButton.Discard)
        assert window.isVisible() == (answer == QMessageBox.StandardButton.Cancel)
        assert window._ProjectFile_DirtyGet()
    assert not errors


def test_failed_close_save_retains_applied_model_and_file(workspace_window, tmp_path, qapp, monkeypatch):
    window, errors = workspace_window
    path = _SavedProject_Open(window, tmp_path)
    original = path.read_bytes()
    _Configuration_Change(window)
    changed = deepcopy(window._model.Dictionary_Get())
    def Fail(*args, **kwargs):
        raise OSError('Injected write failure')
    monkeypatch.setattr(window._service, 'ProjectRoot_Save', Fail)
    accepted, observed = _Close_Click(window, QMessageBox.StandardButton.Save, qapp)
    assert observed and not accepted and window.isVisible()
    assert errors and path.read_bytes() == original
    assert window._model.Dictionary_Get() == changed and window._ProjectFile_DirtyGet()


def test_save_as_cancel_does_not_accept_close(workspace_window, qapp, monkeypatch):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('UnsavedDraft')
    window._Project_Refresh()
    monkeypatch.setattr(QFileDialog, 'exec', lambda self: QFileDialog.DialogCode.Rejected)
    accepted, observed = _Close_Click(window, QMessageBox.StandardButton.Save, qapp)
    assert observed and not accepted and window.isVisible()
    assert window._project_root is None and window._ProjectFile_DirtyGet()
    assert not errors


def test_open_cancel_and_read_only_browsing_preserve_savedness(workspace_window, tmp_path, qapp):
    window, errors = workspace_window
    path = _SavedProject_Open(window, tmp_path)
    baseline = deepcopy(window._model.Dictionary_Get())
    assert not window._ProjectFile_DirtyGet()
    for page in range(3):
        window.navigation_list.setCurrentRow(page)
    window.Language_Apply('en_US')
    window.Theme_Apply('dark')
    _Events_Flush(qapp)
    assert window._model.Dictionary_Get() == baseline and not window._ProjectFile_DirtyGet()
    _Configuration_Change(window)
    changed = deepcopy(window._model.Dictionary_Get())
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Cancel
    window._Project_Open(path)
    assert window._model.Dictionary_Get() == changed and window._ProjectFile_DirtyGet()
    assert window.current_project_value.text().endswith(' · Unsaved')
    window._Project_Save()
    assert not window._ProjectFile_DirtyGet()
    assert window.current_project_value.text() == window._model.identity.name
    assert not errors
