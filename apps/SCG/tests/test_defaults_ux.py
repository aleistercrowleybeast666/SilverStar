"""Real draft/Apply boundaries and shared-radio validation for default recovery."""
from copy import deepcopy
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPushButton

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.air_link import AirLinkIssues_Get, RadioCandidateIssues_Get
from silverstar_fccg.project.alignment import AlignmentConfiguration, AlignmentConstraint
from silverstar_fccg.project.model import AirLinkConfiguration, DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.radio_transaction import RadioTransaction_EndpointSet
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog
from silverstar_fccg.ui.pages.navigation_alignment import AlignmentConfigurationEditor


@pytest.mark.parametrize('scope', ['flight', 'ground'])
def test_configured_opposite_peer_must_match_even_for_single_target(workspace_root, scope):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('peer frequency')
    model = RadioTransaction_EndpointSet(model, service.catalog, 'ground',
        'silverstar.device.telemetry.sx1278', 'e32_400m20s', 17)
    if scope == 'ground':
        model.air_link = replace(model.air_link, radio_family='sx127x', frequency_hz=433000000,
                                spreading_factor=7, bandwidth_hz=125000)
    before = deepcopy(model.Dictionary_Get())
    issues = AirLinkIssues_Get(model, service.catalog, target_scope=scope)
    assert {'AIR_LINK_FAMILY_MISMATCH', 'AIR_LINK_FREQUENCY_OUT_OF_RANGE'} <= {x.code for x in issues}
    assert model.Dictionary_Get() == before
    restored = ProjectModel_Parse(before)
    assert 'AIR_LINK_FAMILY_MISMATCH' in {x.code for x in Project_Validate(restored, service.catalog).issues}


def test_packet_catalog_cannot_bypass_lora_only_product_policy(workspace_root):
    service = FccgService(workspace_root)
    radio = service.catalog.Component_Get('silverstar.device.telemetry.sx1281').radio
    radio = replace(radio, technology='packet', phy_modes=('gfsk',))
    link = replace(AirLinkConfiguration(), radio_technology='packet', phy_mode='gfsk')
    issues = RadioCandidateIssues_Get(link, radio, 'e28_2g4m12sx')
    assert any(x.code == 'AIR_LINK_PHY_INCOMPATIBLE' and 'LoRa' in x.message for x in issues)


@pytest.mark.parametrize('cancel', [True, False])
def test_radio_restore_clears_unentered_draft_without_changing_endpoints(qapp, workspace_root, cancel):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('restore radio')
    before = deepcopy(model.Dictionary_Get())
    dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
    dialog.show()
    frequency = dialog.editor.fields['frequency_hz']
    frequency.setFocus()
    frequency.selectAll()
    QTest.keyClicks(frequency, '2420')
    assert frequency._pending_text is not None
    QTest.mouseClick(dialog.defaults_button, Qt.MouseButton.LeftButton)
    assert frequency._pending_text is None
    assert frequency.CommittedValue_Get() == 2473
    assert model.Dictionary_Get() == before
    if cancel:
        dialog.reject()
        assert dialog.Configuration_Get() is None
    else:
        QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
        result = dialog.Configuration_Get()
        assert result.Dictionary_Get() == before
        reopened = RadioTransactionDialog(Translator('en_US'), result, service.catalog)
        assert reopened.editor.fields['frequency_hz'].CommittedValue_Get() == 2473
        reopened.reject()


def test_radio_non_lora_options_are_unavailable_and_conflicts_explain_bands(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('LoRa only')
    dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
    dialog.show()
    for name in ('radio_technology', 'phy_mode'):
        widget = dialog.editor.fields[name]
        assert [widget.itemData(i) for i in range(widget.count()) if widget.model().item(i).isEnabled()] == ['lora']
    ground = dialog.endpoints['ground'][0]
    ground.setCurrentIndex(ground.findData(('silverstar.device.telemetry.sx1278', 'e32_400m20s')))
    assert '433' in dialog.endpoint_details['ground'].text()
    assert '2473' in dialog.endpoint_details['flight'].text()
    assert '双端' in dialog.error.text()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.Configuration_Get() is None
    dialog.reject()


def test_enter_in_radio_number_never_triggers_restore(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('explicit restore only')
    dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
    dialog.show()
    frequency = dialog.editor.fields['frequency_hz']
    frequency.setFocus()
    frequency.selectAll()
    QTest.keyClicks(frequency, '2420')
    QTest.keyClick(frequency, Qt.Key.Key_Return)
    assert frequency.CommittedValue_Get() == 2420
    assert dialog._draft.air_link.frequency_hz == 2420000000
    assert not dialog.defaults_button.isDefault() and not dialog.defaults_button.autoDefault()
    assert dialog.Configuration_Get() is None
    dialog.reject()


def test_alignment_default_is_private_keeps_strategy_source_and_can_cancel(qapp):
    original = AlignmentConfiguration(
        constraints=(AlignmentConstraint('gravity', weight=2),
                     AlignmentConstraint('reference_direction', body_axis='+Y', nav_azimuth_deg=40)),
        external_source_instance='imu2', external_yaw_authoritative=True)
    strategy = 'silverstar.algorithm.alignment.external_attitude_source'
    source = DeviceInstance('imu2', 'silverstar.device.imu.jy901b')
    editor = AlignmentConfigurationEditor(Translator('zh_CN'))
    results = []
    editor.configurationConfirmed.connect(lambda name, value: results.append((name, value)))
    editor.Configuration_Set(original, strategy, (source,))
    editor.show()
    QTest.mouseClick(editor.defaults_button, Qt.MouseButton.LeftButton)
    assert editor.draft_dirty and not results
    assert editor._committed == original
    assert editor.DraftStrategy_Get() == strategy and editor._source.currentData() == 'imu2'
    editor.Draft_Discard()
    assert not editor.draft_dirty and editor._constraints == list(original.constraints)
    QTest.mouseClick(editor.defaults_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(editor.confirm_button, Qt.MouseButton.LeftButton)
    name, result = results[-1]
    assert name == strategy and result.external_source_instance == 'imu2'
    assert result.constraints == AlignmentConfiguration().constraints
    assert not result.external_yaw_authoritative


@pytest.mark.parametrize('cancel', [True, False])
def test_algorithm_footer_defaults_keep_scope_and_clear_pending_text(qapp, workspace_root, cancel):
    from silverstar_fccg.project.mission_functions import Functions_Derive, FunctionsCatalog_Get
    from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
    from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('algorithm defaults')
    declarations = {r['plugin_id']:r for r in FunctionsCatalog_Get(service.catalog)}
    function = next(row for row in Functions_Derive(model, service.catalog)['functions']
                    if declarations[row['plugin_id']].get('parameter_owner'))
    before = deepcopy(model.Dictionary_Get())
    dialog = MissionStageTransactionDialog(Translator('en_US'), model, service.catalog,
        model.mission_process['stages'][0]['stage_id'], function_id=function['instance_id'])
    dialog.show()
    owner = dialog.parameter_owner.currentData()
    numeric = next(editor for (component, _), editor in dialog.parameters.editors.items()
                   if component == owner and isinstance(editor, EnterCommittedDoubleSpinBox))
    numeric.setFocus()
    numeric.selectAll()
    QTest.keyClick(numeric, Qt.Key.Key_Backspace)
    assert numeric._pending_text is not None
    QTest.mouseClick(dialog.defaults_button, Qt.MouseButton.LeftButton)
    assert numeric._pending_text is None
    assert dialog._draft.mission_functions == model.mission_functions
    assert model.Dictionary_Get() == before
    if cancel:
        dialog.reject()
        assert dialog.Configuration_Get() is None
    else:
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    assert model.Dictionary_Get() == before


def test_hardware_overview_has_no_duplicate_editor_buttons(qapp, workspace_root):
    from test_hardware_workspace import _Editors_Create
    from silverstar_fccg.ui.pages.hardware_workspace import HardwareWorkspacePage
    translator = Translator('zh_CN')
    workspace = HardwareWorkspacePage(translator, *_Editors_Create(translator))
    assert not workspace.device_group.findChildren(QPushButton)
    assert len(workspace.target_buttons) == 2


def test_radio_open_keeps_actual_power_and_restoring_phy_does_not_reset_it(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('actual radio power')
    for endpoint in ('flight', 'ground'):
        model = RadioTransaction_EndpointSet(model, service.catalog, endpoint,
            'silverstar.device.telemetry.sx1281', 'e28_2g4m27sx', 27)
    from silverstar_fccg.project.air_link import AirLinkDefaults_Get
    model.air_link = AirLinkDefaults_Get(model.air_link, 'sx128x')
    dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
    assert all(power.currentData() == 27 for _, power in dialog.endpoints.values())
    dialog.defaults_button.click()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    assert dialog.Configuration_Get().Dictionary_Get() == model.Dictionary_Get()


@pytest.mark.parametrize('language', ['zh_CN', 'en_US'])
def test_property_dialog_actions_fit_laptop_logical_screen(qapp, workspace_root, language):
    from PySide6.QtCore import QRect, QPoint
    from PySide6.QtWidgets import QDialogButtonBox, QScrollArea
    from silverstar_fccg.ui.window_geometry import Window_ConstrainInitialGeometry
    from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('small screen')
    for dialog in (RadioTransactionDialog(Translator(language), model, service.catalog),
                   MissionStageTransactionDialog(Translator(language), model, service.catalog,
                       model.mission_process['stages'][0]['stage_id'])):
        dialog.show()
        qapp.processEvents()
        available = QRect(0, 0, 910, 480)  # 1366x768 at 150%, with taskbar allowance.
        Window_ConstrainInitialGeometry(dialog, available)
        qapp.processEvents()
        assert available.contains(dialog.frameGeometry())
        buttons = [box for box in dialog.findChildren(QDialogButtonBox) if box.parentWidget() is dialog]
        assert buttons
        for box in buttons:
            for button in box.buttons():
                if not button.isVisible():
                    continue
                assert dialog.rect().contains(QRect(button.mapTo(dialog, QPoint()), button.size()))
        for scroll in dialog.findChildren(QScrollArea):
            if scroll.isVisible():
                assert scroll.widget().width() <= scroll.viewport().width()
        dialog.reject()
