"""Real shared-source and dependency edits through the ordinary stage dialog."""
from copy import deepcopy
from dataclasses import replace

from PySide6.QtWidgets import QCheckBox, QDialog

from test_three_workspace_workflow import workspace_window, _Capsule_Click, _Events_Flush, _Snapshot
from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsCanonical_Get
from silverstar_fccg.ui.widgets import StandardComboBox


def _Sources_Prepare(window):
    model = window._service.ReferenceProject_Create('Shared source transaction')
    # Two explicitly selected providers. Interface allocation is outside this
    # editor regression; this fixture is not generated firmware/hardware proof.
    model.device_instances.append(replace(model.DeviceInstance_Get('imu0'), instance_id='imu1'))
    window._model = window._service.ProjectConfiguration_Reconcile(model).model
    window._Project_Refresh()
    window.navigation_list.setCurrentRow(1)


def _Source_Choose(dialog, provider):
    combo = dialog.findChild(StandardComboBox, 'functionInput_ins_imu.acceleration')
    assert combo is not None and combo.isEnabled()
    index = combo.findData(provider)
    assert index >= 0
    combo.setCurrentIndex(index)


def _TelemetryStart_Choose(dialog):
    form = dialog.bindings[0]._sections['telemetry.range'].body.layout()
    start = form.itemAt(0, form.ItemRole.FieldRole).widget()
    start.setCurrentIndex(start.findData(('stage_enter', 'ascent')))


def _InFunction(stage_dialog, identity, edit, *, apply=True):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    outcomes = []
    def During():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog is not stage_dialog
            assert dialog._function_id == identity
            assert sum(len(editor._sections) for editor in dialog.bindings) == 2
            edit(dialog)
            if apply:
                dialog.accept()
                assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
            outcomes.append(None)
        except BaseException as error:
            outcomes.append(error)
            dialog.reject()
    QTimer.singleShot(0, During)
    stage_dialog._FunctionDialog_Open(identity, stage_dialog.stage_editor._process['stages'][stage_dialog.stage_editor._index]['stage_id'])
    assert outcomes
    if outcomes[0] is not None:
        raise outcomes[0]


def test_shared_source_group_and_dependency_apply_once_cancel_and_reopen(workspace_window, tmp_path, qapp):
    window, errors = workspace_window
    _Sources_Prepare(window)
    before = _Snapshot(window._model)
    changes = []
    window.workflow_page.configurationChanged.connect(changes.append)

    def Edit(dialog, apply):
        assert not dialog.bindings and not dialog.parameters.editors
        _InFunction(dialog, 'ins', lambda child: _Source_Choose(child, 'imu1'))
        def Telemetry(child):
            dependency = child.findChild(QCheckBox, 'functionDependency_telemetry_estimator')
            assert dependency.isEnabled()
            dependency.setChecked(True)
            _TelemetryStart_Choose(child)
        _InFunction(dialog, 'telemetry', Telemetry)
        if apply:
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
        else:
            dialog.reject()

    _Capsule_Click(window, 'ascent', lambda dialog: Edit(dialog, False))
    _Events_Flush(qapp)
    assert _Snapshot(window._model) == before and not changes
    _Capsule_Click(window, 'ascent', lambda dialog: Edit(dialog, True))
    _Events_Flush(qapp)
    assert len(changes) == 1 and not errors
    assert window._model.capability_source_overrides['imu.acceleration'] == 'imu1'
    assert window._model.capability_source_overrides['imu.angular_rate'] == 'imu1'
    canonical = {row['instance_id']: row for row in FunctionsCanonical_Get(window._model, window._service.catalog)['functions']}
    functions = Functions_Derive(window._model, window._service.catalog)['functions']
    assert all(row['input_bindings'] == canonical[row['instance_id']]['input_bindings'] for row in functions)
    assert next(row for row in functions if row['instance_id'] == 'telemetry')['depends_on'] == ['estimator']
    saved = _Snapshot(window._model)
    root = window._service.ProjectRoot_Save(window._model, tmp_path / 'connected')
    assert _Snapshot(window._service.Project_Open(root)) == saved

    # The table is the sole function list. Further source changes live only in
    # the nested owner transaction and still roll back with the stage dialog.
    assert window.workflow_page.findChild(StandardComboBox, 'functionInput_ins_imu.acceleration') is None
    assert not any(editor._sections for editor in window.workflow_page.function_editors)
    def Pending(dialog, apply):
        def Inspect(child):
            _Source_Choose(child, 'imu0')
        _InFunction(dialog, 'ins', Inspect)
        if apply:
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
        else:
            dialog.reject()
    _Capsule_Click(window, 'ascent', lambda dialog: Pending(dialog, False))
    _Events_Flush(qapp)
    assert _Snapshot(window._model) == saved
    assert window.workflow_page.PendingFunctions_Collect() is None
    _Capsule_Click(window, 'ascent', lambda dialog: Pending(dialog, True))
    _Events_Flush(qapp)
    assert len(changes) == 2 and not errors
    # The canonical default source needs no redundant override entry.
    restored = Functions_Derive(window._model, window._service.catalog)['functions']
    ins = next(row for row in restored if row['instance_id'] == 'ins')
    assert ins['input_bindings']['imu.acceleration'] == 'imu0'
    assert ins['input_bindings']['imu.angular_rate'] == 'imu0'
    assert 'imu.acceleration' not in window._model.capability_source_overrides
    assert 'imu.angular_rate' not in window._model.capability_source_overrides
    assert window.workflow_page.PendingFunctions_Collect() is None


def test_dependency_outside_owner_interval_keeps_modal_draft_for_repair(workspace_window, qapp):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Dependency validation')
    window._Project_Refresh()
    before = _Snapshot(window._model)
    def Edit(dialog):
        dependency = dialog.findChild(QCheckBox, 'functionDependency_telemetry_ins')
        assert dependency.isEnabled()
        dependency.setChecked(True)
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert 'FUNCTION_INPUT_INTERVAL' in dialog.error.text()
        assert dialog.bindings[0]._sections['telemetry.range'].Expanded_Is()
        assert dialog.groups['records'].Expanded_Is()
        assert dialog._translator.Text_Get('workflow.validation.dependency_interval') in dialog.error.text()
        assert dependency.isChecked() and _Snapshot(window._model) == before
        _TelemetryStart_Choose(dialog)
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    _Capsule_Click(window, 'ascent', lambda dialog: (_InFunction(dialog, 'telemetry', Edit), dialog.accept()))
    _Events_Flush(qapp)
    assert not errors
    telemetry = next(row for row in window._model.mission_functions['functions'] if row['instance_id'] == 'telemetry')
    assert telemetry['depends_on'] == ['ins']
