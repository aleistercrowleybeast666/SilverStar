"""Product transport admission at persisted, public API and renderer boundaries."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.generator.multi_target import _PcAdapter_Render
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_removed_transport_has_no_public_service_backend():
    for name in ('NativeUsb_Inspect', 'NativeUsb_Prepare', 'NativeUsb_Build',
                 'UsbGroundCandidate_Export', 'NativeClassicCdcGroundCandidate_Build'):
        assert not hasattr(FccgService, name), name


def test_saved_cdc_project_remains_readable_and_rejects_without_guessing(builtin_catalog, tmp_path):
    data = ReferenceProject_Create(catalog=builtin_catalog).Dictionary_Get()
    data['ground_target']['pc_interface'] = 'usb_cdc'
    data['ground_target']['pc_resource'] = ''
    path = tmp_path / 'legacy.ssproject'
    path.write_text(json.dumps(data), encoding='utf8')
    original = path.read_bytes()
    model = ProjectModel_Load(path)
    assert model.ground_target.pc_resource == ''
    assert any(issue.code == 'GROUND_NATIVE_CDC_RETIRED' for issue in GroundTargetIssues_Get(model, builtin_catalog))
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
    from silverstar_fccg.project.target_readiness import TargetReadiness_Get
    for scope in TargetScope:
        output = tmp_path / ('generated-' + scope.value)
        with pytest.raises(ValueError, match='MCU native USB CDC has been retired'):
            TargetGeneration_Apply(model, builtin_catalog, WorkspacePolicy(tmp_path), output, scope)
        assert not output.exists()
    for target in ('flight', 'ground'):
        assert any(issue.code == 'GROUND_NATIVE_CDC_RETIRED'
                   for issue in TargetReadiness_Get(model, builtin_catalog, target).issues)
    assert path.read_bytes() == original


@pytest.mark.parametrize('interface', ['usb_cdc', '', 'unimplemented'])
def test_adapter_never_falls_back_to_a_transport(builtin_catalog, interface):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.ground_target = replace(model.ground_target, pc_interface=interface)
    with pytest.raises(ValueError, match='UART'):
        _PcAdapter_Render(model)


def test_ground_migration_requires_two_explicit_selections_and_preserves_original(qapp, workspace_root, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.project.folder_contract import ProjectRoot_Save
    from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
    from test_round2_targets import _GroundBoardProject_Get

    service = FccgService(workspace_root)
    original = _GroundBoardProject_Get(service.catalog).Dictionary_Get()
    original['ground_target'].update(pc_interface='usb_cdc', pc_resource='')
    path = tmp_path / 'legacy.ssproject'
    path.write_text(json.dumps(original), encoding='utf8')
    unchanged = path.read_bytes()
    model = ProjectModel_Load(path)
    output = tmp_path / 'new_uart'
    with pytest.raises(ValueError, match='Select Ground hardware, UART'):
        ProjectRoot_Save(model, output)
    assert not output.exists()
    for cancel in (True, False):
        dialog = HardwareTransactionDialog(Translator('en_US'), model, service, 'ground', 'devices')
        dialog.show()
        qapp.processEvents()
        page = dialog.controller.ground_target_page
        assert page.pc_interface.currentData() == ''
        page.pc_interface.setCurrentIndex(page.pc_interface.findData('uart'))
        assert not page.pc_resource.currentData()
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        page.pc_resource.setCurrentIndex(page.pc_resource.findData('PLATFORM_UART_1'))
        assert 'bit/s' in page.pc_resource_source.text()
        if cancel:
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            assert dialog.Configuration_Get() is None
        else:
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.controller.status_label.text()
            candidate = dialog.Configuration_Get()
            assert not GroundTargetIssues_Get(candidate, service.catalog)
            ProjectRoot_Save(candidate, output)
            restored = ProjectModel_Load(output/'SilverStar.ssproject')
            assert restored.ground_target.pc_interface == 'uart'
            assert restored.ground_target.pc_resource == 'PLATFORM_UART_1'
            assert restored.native_usb is None
        dialog.deleteLater()
        qapp.processEvents()
    assert path.read_bytes() == unchanged
    assert model.ground_target.pc_interface == 'usb_cdc'
