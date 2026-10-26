from copy import deepcopy

from PySide6.QtWidgets import QDialog, QWidget

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.mission_functions import Functions_Derive, Functions_Require, FunctionsReferenceRunner
from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
from silverstar_fccg.ui.widgets import CollapsibleSection


def test_expanded_section_body_never_becomes_a_top_level(qapp):
    owner = QWidget()
    section = CollapsibleSection('expanded', parent=owner, expanded=True)
    assert section.body.parentWidget() is section
    assert not section.body.isWindow()
    owner.show(); qapp.processEvents()
    assert not section.body.isWindow()


def test_stage_dialog_is_one_model_transaction(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.Project_Open(workspace_root / 'examples/Uncontrolled_Desktop_Reference.ssproject')
    before = deepcopy(model.Dictionary_Get())
    for language in ('zh_CN', 'en_US'):
        dialog = MissionStageTransactionDialog(Translator(language), model, service.catalog, 'coast')
        dialog.resize(740, 620); dialog.show(); qapp.processEvents()
        dialog.stage_editor.name_edit.setText('Cancelled name')
        component, values = next(iter(dialog._draft.algorithm_parameters.items()))
        parameter = next(iter(values))
        dialog._Parameter_Set(component, parameter, values[parameter])
        dialog.reject()
        assert dialog.Configuration_Get() is None
        assert model.Dictionary_Get() == before
        dialog.deleteLater(); qapp.processEvents()
    dialog = MissionStageTransactionDialog(Translator('zh_CN'), model, service.catalog, 'coast')
    dialog.stage_editor.name_edit.setText('Coast edited transactionally')
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    result = dialog.Configuration_Get()
    assert next(row for row in result.mission_process['stages'] if row['stage_id'] == 'coast')['name'] == 'Coast edited transactionally'
    assert model.Dictionary_Get() == before
    assert result.mission_functions == Functions_Derive(model, service.catalog)


def test_v2_inclusive_same_stage_and_cross_stage_do_not_restart(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('Inclusive')
    configuration = Functions_Derive(model, service.catalog)
    function = next(row for row in configuration['functions'] if row['instance_id'] == 'estimator')
    function.update(start={'kind':'stage_enter','stage_id':'flight'},
                    stop={'kind':'stage_exit','stage_id':'descent'}, depends_on=[])
    configuration = {'schema_version':2, 'functions':[function]}
    runner = FunctionsReferenceRunner(configuration, ['flight','coast','descent','landed'])
    assert runner.Snapshot_Step(1, stage_id='flight')['start_requests'] == ['estimator']
    for time, stage in ((2,'coast'),(3,'descent')):
        result = runner.Snapshot_Step(time, stage_id=stage)
        assert result['active'] == ['estimator'] and not result['start_requests']
    assert runner.Snapshot_Step(4, stage_id='descent', stage_exited=True)['stop_requests'] == ['estimator']
    function['stop'] = {'kind':'stage_exit','stage_id':'flight'}
    runner = FunctionsReferenceRunner(configuration, ['flight','landed'])
    assert runner.Snapshot_Step(1, stage_id='flight')['active'] == ['estimator']
    assert runner.Snapshot_Step(2, stage_id='flight', stage_exited=True)['stop_requests'] == ['estimator']
    configuration['schema_version'] = 1
    import pytest
    with pytest.raises(ValueError, match='requires_v2'): Functions_Require(configuration)
