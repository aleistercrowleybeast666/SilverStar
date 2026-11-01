"""Persistent actions stay reachable outside a private, cancelable editor."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
from test_release_migration import _Legacy_Create


def test_legacy_copy_action_stays_visible_and_cancel_preserves_model(qapp, workspace_root, tmp_path):
    service=FccgService(workspace_root)
    window=MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._model=_Legacy_Create(service)
    window._Project_Refresh()
    window.show();qapp.processEvents()
    before=deepcopy(window._model.Dictionary_Get())
    boxes=[]
    window._MessageBox_Exec=lambda *args,**kwargs: boxes.append(args) or QMessageBox.StandardButton.Cancel
    try:
        assert window.legacy_migration_button.isVisible()
        QTest.mouseClick(window.legacy_migration_button,Qt.MouseButton.LeftButton)
        assert boxes
        assert window._model.Dictionary_Get()==before
    finally:
        window._MessageBox_Exec=lambda *_args,**_kwargs: QMessageBox.StandardButton.Discard
        window.close()


def test_imported_hardware_save_is_on_main_card_and_not_in_private_draft(qapp,workspace_root,tmp_path):
    service=FccgService(workspace_root)
    service.hardware_importer=CubeMxImporter(WorkspacePolicy(tmp_path))
    imported=service.hardware_importer.Project_Import(workspace_root/'tests/fixtures/cubemx_minimal',
        expected_mcu='STM32F407VET6',risk_acknowledged=True)
    window=MainWindow(SettingsStore(tmp_path/'settings.ini'),service=service)
    window._model.board=''
    window._model.hardware=imported.hardware
    window._Project_Refresh()
    window.show();qapp.processEvents()
    calls=[]
    window._BoardInstanceSave_Request=calls.append
    try:
        button=window.board_hardware_page.export_button
        assert button.isEnabled() and button.isVisible()
        assert window.hardware_workspace.target_cards['flight'].isAncestorOf(button)
        assert window.hardware_workspace.target_cards['ground'].isAncestorOf(window.ground_target_page.export_button)
        QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        assert calls==['flight']
        dialog=HardwareTransactionDialog(window._translator,window._model,service,'flight',parent=window)
        dialog.show();qapp.processEvents()
        assert not dialog.controller.board_hardware_page.export_button.isVisible()
        assert not dialog.controller.board_hardware_page.platform_form.isRowVisible(
            dialog.controller.board_hardware_page.platform_values['provenance'])
        dialog.reject();dialog.deleteLater()
    finally:
        window._MessageBox_Exec=lambda *_args,**_kwargs: QMessageBox.StandardButton.Discard
        window.close()
