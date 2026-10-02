from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QInputDialog

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware import BoardPluginExporter, CubeMxImporter
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.installer import PluginInstaller
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import BoardHardwareInventory_Get
from silverstar_fccg.ui.main_window import MainWindow


def test_alignment_group_contains_mode_draft_and_actions(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=FccgService(workspace_root))
    window.navigation_list.setCurrentRow(2)
    window.show()
    qapp.processEvents()
    group = window.flight_configuration_page.strategy_group
    editor = window.algorithm_parameters_page.alignment_editor
    assert group.isAncestorOf(editor)
    assert group.isAncestorOf(editor.confirm_button)
    combo = window.flight_configuration_page.strategy_combos['alignment']
    assert combo.mapTo(group, QPoint()).y() < editor.mapTo(group, QPoint()).y()
    original = deepcopy(window._model.alignment)
    combo.setCurrentIndex(combo.findData('silverstar.algorithm.alignment.external_attitude_source'))
    editor.cancel_button.click()
    assert window._model.alignment == original
    for language in ('zh_CN', 'en_US'):
        window.Language_Apply(language)
        window.resize(1280, 720)
        qapp.processEvents()
        assert not window.title_label.wordWrap()
        assert '(SCG)' not in window.title_label.text()
        assert window.title_label.width() >= window.title_label.fontMetrics().horizontalAdvance(window.title_label.text())
    window.close()


def test_ground_existing_selection_cancel_commit_and_common_page(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=FccgService(workspace_root))
    page = window.ground_target_page
    assert page.prepare_button.isEnabled()
    previous = window._model.Dictionary_Get()
    with patch.object(QInputDialog, 'getItem', return_value=('', False)):
        page.prepare_button.click()
    assert window._model.Dictionary_Get() == previous
    title = next(page.board_combo.itemText(i) for i in range(page.board_combo.count()) if page.board_combo.itemData(i) != '__custom__')
    with patch.object(QInputDialog, 'getItem', return_value=(title, True)):
        page.prepare_button.click()
    assert window._model.ground_target.board == 'silverstar.board.ground_station_0_5'
    assert window._model.ground_target.hardware.resources
    assert not page.isAncestorOf(page.build_group)
    assert not page.isAncestorOf(page.status)
    assert not page.isAncestorOf(page.advanced_section)
    assert not window.board_hardware_page.isAncestorOf(window.board_hardware_page.advanced_section)
    assert window.build_page.isAncestorOf(page.build_group)
    assert window.air_link_page.isAncestorOf(page.advanced_section)
    window.close()


def test_localized_navigation_fits_all_labels_and_preserves_selection(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=FccgService(workspace_root))
    try:
        window.resize(1360, 920)
        window.show()
        window.navigation_list.setCurrentRow(2)
        for language in ('en_US', 'zh_CN', 'en_US'):
            window.Language_Apply(language)
            qapp.processEvents()
            assert window.navigation_list.currentRow() == 2
            for index in range(window.navigation_list.count()):
                item = window.navigation_list.item(index)
                assert window.navigation_list.visualItemRect(item).width() >= (
                    window.navigation_list.fontMetrics().horizontalAdvance(item.text()) + 28
                )
    finally:
        window.close()


def test_classified_pcbs_preserve_legacy_and_conflicts(tmp_path, workspace_root):
    root = tmp_path/'中文 PCB'
    root.mkdir()
    policy = WorkspacePolicy(root)
    installed_root = root/'plugins/installed'
    catalog = PluginCatalog(workspace_root/'plugins/builtin', installed_root)
    catalog.Scan()
    imported = CubeMxImporter(policy).Project_Import(workspace_root/'tests/fixtures/cubemx_minimal',
        expected_mcu='STM32F407VET6', risk_acknowledged=True)
    model = ReferenceProject_Create('Boards', catalog=catalog)
    model.board = ''
    model.hardware = imported.hardware
    model.ground_target = replace(model.ground_target, enabled=True, mcu=model.mcu,
                                  hardware=imported.hardware, board='')
    installer = PluginInstaller(policy, installed_root, catalog)
    exporter = BoardPluginExporter(policy)
    for role, folder in (('flight', 'Flight_Controller'), ('ground', 'Ground_Station')):
        archive = exporter.Plugin_Export(model, imported.snapshot_root, root/(role+'.ssplugin'),
            component_id='local.board.'+role+'.same_name', name='同名板卡', target_role=role, namespace_payload=True)
        result = installer.Install(archive, target_role=role)
        assert result.package_root.is_relative_to(installed_root/'PCB'/folder)
        assert result.version == '0.1.0'
        assert all(path.is_file() for path in result.PayloadFiles_Get())
        assert BoardHardwareInventory_Get(result).Dictionary_Get() == imported.inventory.Dictionary_Get()
        assert all((result.payload_root/path).is_file() for path in result.build.sources)
        with pytest.raises(Exception, match='already installed'):
            installer.Install(archive, target_role=role)
    archive = exporter.Plugin_Export(model, imported.snapshot_root, root/'legacy.ssplugin',
        component_id='local.board.legacy', name='Old mixed directory', target_role='ground')
    legacy = installer.Install(archive)
    assert legacy.package_root.is_relative_to(installed_root/'local.board.legacy')
    catalog.Scan()
    assert catalog.Component_Get(legacy.component_id).metadata['target_role'] == 'ground_station'
    wrong = exporter.Plugin_Export(model, imported.snapshot_root, root/'wrong.ssplugin',
        component_id='local.board.wrong', name='Mismatch', target_role='flight', namespace_payload=True)
    with pytest.raises(Exception, match='target role'):
        installer.Install(wrong, target_role='ground')
    original = model.Dictionary_Get()
    original['project']['firmware_version'] = '0.1.0'
    assert ProjectModel_Parse(original).identity.firmware_version == '0.1.0'


def test_service_save_classifies_archives_and_reload(tmp_path, workspace_root):
    service = FccgService(tmp_path)
    service.catalog = PluginCatalog(workspace_root/'plugins/builtin', tmp_path/'plugins/installed')
    service.catalog.Scan()
    service.installer = PluginInstaller(service.policy, tmp_path/'plugins/installed', service.catalog)
    imported = service.hardware_importer.Project_Import(workspace_root/'tests/fixtures/cubemx_minimal',
        expected_mcu='STM32F407VET6', risk_acknowledged=True)
    # Synthetic clock declaration exercises the save gate; no hardware claim.
    imported.hardware.inventory['clocks']['RCC.HCLKFreq_Value'] = 168000000
    model = ReferenceProject_Create('SaveLocal', catalog=service.catalog)
    model.hardware = imported.hardware
    model.ground_target = replace(model.ground_target, mcu=model.mcu, hardware=imported.hardware)
    for role, folder in (('flight','Flight_Controller'),('ground','Ground_Station')):
        component_id = 'local.board.saved.'+role
        result = service.CustomBoardPlugin_SaveLocal(model, component_id=component_id, name='Shared name', target_role=role)
        archive = tmp_path/'.work/board_exports'/folder/(component_id+'.ssplugin')
        assert archive.is_file()
        saved = archive.read_bytes()
        service.catalog.Scan()
        assert service.catalog.Component_Get(component_id).package_root == result.package_root
        with pytest.raises(ValueError, match='already installed'):
            service.CustomBoardPlugin_SaveLocal(model, component_id=component_id, name='Replacement', target_role=role)
        assert archive.read_bytes() == saved
