"""Property owner tests through the same Qt controls used by the three workspaces."""
from copy import deepcopy

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QPushButton

from test_three_workspace_workflow import _Capsule_Click, _Events_Flush, workspace_window
from silverstar_fccg.project.mission_process import MissionProcess_FirmwareDefault
from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
from silverstar_fccg.ui.workflow_properties import WorkflowPropertiesDialog


def _Number_Type(widget, value):
    widget.setFocus()
    widget.lineEdit().selectAll()
    QTest.keyClicks(widget.lineEdit(), value)


def test_apply_collects_unconfirmed_fields_and_retains_invalid_draft(workspace_window, qapp):
    window, errors = workspace_window
    model = window._service.ReferenceProject_Create('Stage values')
    model.mission_process = MissionProcess_FirmwareDefault(acceleration_detection=True)
    window._model = model
    window._Project_Refresh()
    before = deepcopy(model.Dictionary_Get())
    def Edit(dialog):
        editor = dialog.stage_editor
        editor.signal_combo.setCurrentIndex(editor.signal_combo.findData('stage_elapsed_s'))
        _Number_Type(editor.number, '1.125')
        _Number_Type(editor.hold, '7')
        editor.hold.lineEdit().selectAll()
        QTest.keyClick(editor.hold.lineEdit(), Qt.Key.Key_Backspace)
        apply = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        QTest.mouseClick(apply, Qt.MouseButton.LeftButton)
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.error.text() and '1.125' in editor.number.lineEdit().text()
        assert window._model.Dictionary_Get() == before
        _Number_Type(editor.hold, '15')
        QTest.mouseClick(apply, Qt.MouseButton.LeftButton)
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    _Capsule_Click(window, 'coast', Edit)
    row = next(item for item in window._model.mission_process['stages'] if item['stage_id'] == 'coast')
    assert row['condition']['value'] == 1.125 and row['hold_ms'] == 15
    assert not errors


@pytest.mark.parametrize('scope', ('algorithms', 'preparation', 'protocols'))
def test_workflow_options_cancel_keeps_canonical_model_and_no_orphan_widget(workspace_window, qapp, scope):
    window, _errors = workspace_window
    model = window._service.ReferenceProject_Create('Property owner')
    window._model = model
    window._Project_Refresh()
    before = deepcopy(model.Dictionary_Get())
    dialog = WorkflowPropertiesDialog(window._translator, window.workflow_page._display,
                                      window._service.catalog, scope, window)
    dialog.show()
    qapp.processEvents()
    assert window._model.Dictionary_Get() == before
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.Configuration_Get() is None
    dialog.deleteLater()
    _Events_Flush(qapp)
    assert window._model.Dictionary_Get() == before
    assert not any(widget.isVisible() and not widget.isAncestorOf(window) and widget is not window
                   for widget in qapp.topLevelWidgets())


def test_stage_reference_finishes_before_shared_function_dialog(workspace_window, qapp):
    window, _errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Stage reference')
    window._model.mission_process = MissionProcess_FirmwareDefault(acceleration_detection=True)
    window._Project_Refresh()
    window.navigation_list.setCurrentRow(1)
    seen = []
    def Stage(dialog):
        dialog.stage_editor.name_edit.setText('Coast renamed')
        button = dialog.findChild(QPushButton, 'stageReference_ins')
        assert button
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert dialog.result() == QDialog.DialogCode.Accepted
        seen.append('stage')
    _Capsule_Click(window, 'coast', Stage)
    def Function():
        child = QApplication.activeModalWidget()
        if isinstance(child, MissionStageTransactionDialog):
            seen.append(child._function_id)
            seen.append(sum(isinstance(widget, MissionStageTransactionDialog) and widget.isVisible()
                            for widget in qapp.topLevelWidgets()))
            child.reject()
    QTimer.singleShot(0, Function)
    _Events_Flush(qapp)
    assert seen == ['stage', 'ins', 1]
    assert next(row for row in window._model.mission_process['stages'] if row['stage_id'] == 'coast')['name'] == 'Coast renamed'
