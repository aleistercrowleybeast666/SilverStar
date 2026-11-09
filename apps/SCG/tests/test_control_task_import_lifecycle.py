"""Real production import/preview buttons, including deferred Qt destruction."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.tuning_bundle import (
    TuningBundle_Read, TuningBundle_Apply, TuningBundle_ControlTaskAttach)
from silverstar_fccg.ui.main_window import MainWindow


@pytest.mark.parametrize('decision', ('parameters_only', 'task', 'cancel'))
def test_real_preview_consumes_option_before_dialog_children_are_deleted(
        qapp, workspace_root, tmp_path, monkeypatch, decision):
    service = FccgService(workspace_root)
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._toolchain_checked = True
    window._model = service.ReferenceProject_Create('real preview lifecycle')
    window._Project_Refresh()
    window.navigation_list.setCurrentRow(1)
    window.workflow_page.coverage.Function_Select('estimator')
    window.show()
    qapp.processEvents()
    source = Path(__file__).parent/'fixtures/tuning_bundle_v1/kf6-pid.sstuning.json'
    bundle = TuningBundle_Read(source)
    before = deepcopy(window._model.Dictionary_Get())
    expected = (TuningBundle_ControlTaskAttach if decision == 'task' else TuningBundle_Apply)(
        window._model, service.catalog, bundle)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args:
                        (str(source), 'TreeDiagram bundle (*.sstuning.json)'))
    errors, observed = [], []
    monkeypatch.setattr(sys, 'excepthook', lambda _kind, error, _trace: errors.append(error))
    window._Error_Show = lambda *args: errors.append(args)
    real_exec = window._MessageBox_Exec

    def Execute_RealPreview(*args, **kwargs):
        result = real_exec(*args, **kwargs)
        # Exercise the actual destruction boundary before the importer
        # resumes. The dialog result comes from its real Apply/Cancel button.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert observed and not shiboken6.isValid(observed[-1])
        return result

    window._MessageBox_Exec = Execute_RealPreview

    def Preview_Click():
        box = QApplication.activeModalWidget()
        try:
            assert isinstance(box, QMessageBox)
            option = box.checkBox()
            assert option is not None and option.isEnabled() and not option.isChecked()
            assert window._model.Dictionary_Get() == before
            observed.append(option)
            if decision in ('task', 'cancel'):
                QTest.mouseClick(option, Qt.MouseButton.LeftButton)
                assert option.isChecked()
            box.finished.connect(box.deleteLater)
            button = QMessageBox.StandardButton.Cancel if decision == 'cancel' else QMessageBox.StandardButton.Apply
            QTest.mouseClick(box.button(button), Qt.MouseButton.LeftButton)
        except BaseException as error:
            errors.append(error)
            if box is not None:
                box.reject()

    try:
        QTimer.singleShot(0, Preview_Click)
        QTest.mouseClick(window.workflow_page.function_buttons['import'], Qt.MouseButton.LeftButton)
        assert observed and not errors, errors
        if decision == 'cancel':
            assert window._model.Dictionary_Get() == before
        else:
            assert window._model.algorithm_parameters == expected.algorithm_parameters
            assert window._model.algorithm_parameters != before['algorithm_parameters']
            controllers = [row for row in (window._model.mission_functions or {}).get('functions', [])
                           if row['instance_id'] == 'controller']
            assert bool(controllers) == (decision == 'task')
            assert ('silverstar.algorithm.control.pid' in window._model.base_components) == (decision == 'task')
    finally:
        window._project_dirty = False
        window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
        window.close()
