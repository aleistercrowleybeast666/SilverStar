"""The three-workspace hardware composition keeps unique target/editor ownership."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtGui import QFontDatabase

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.ui.pages.components import DevicesPage, BoardHardwarePage
from silverstar_fccg.ui.pages.targets import GroundTargetPage, AirLinkPage
from silverstar_fccg.ui.pages.hardware_workspace import HardwareWorkspacePage
from silverstar_fccg.ui.pages.build import BuildPage
from silverstar_fccg.ui.theme import Theme_Apply
import pytest


def _Fonts_Register():
    for font in ('msyh.ttc', 'segoeui.ttf'):
        path = Path('C:/Windows/Fonts') / font
        if path.is_file(): QFontDatabase.addApplicationFont(str(path))


def _Editors_Create(translator):
    _Fonts_Register()
    return DevicesPage(translator), BoardHardwarePage(translator), GroundTargetPage(translator), AirLinkPage(translator)


def _Events_Flush(qapp):
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_targets_remain_discoverable_and_configuration_is_read_only(qapp, workspace_root):
    translator = Translator('zh_CN')
    devices, flight, ground, air = _Editors_Create(translator)
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('HardwareWorkspace')
    before = deepcopy(model.Dictionary_Get())
    devices.Configuration_Set(service.ComponentViews_Get(), service.DeviceInstanceViews_Get(model))
    workspace = HardwareWorkspacePage(translator, devices, flight, ground, air)
    try:
        workspace.Configuration_Set(model)
        assert not model.ground_target.enabled
        assert workspace.target_cards['flight'].isAncestorOf(flight.board_combo)
        assert workspace.target_cards['ground'].isAncestorOf(ground.board_combo)
        assert workspace.target_cards['ground'].isAncestorOf(ground.import_directory)
        assert workspace._target_sections['flight'].isAncestorOf(devices.telemetry_group)
        assert workspace._target_sections['ground'].isAncestorOf(ground.pc_interface)
        assert workspace._target_sections['ground'].isAncestorOf(ground.radio_instances_editor)
        assert not air.isAncestorOf(ground.pc_interface)
        assert workspace._sections['flight.platform'].Expanded_Is() is False
        assert workspace._sections['ground.platform'].Expanded_Is() is False
        for language in ('zh_CN', 'en_US'):
            workspace.Language_Apply(Translator(language))
            for theme in ('light', 'dark'):
                Theme_Apply(qapp, theme)
                for width in (900, 1280):
                    workspace.resize(width, 1000); workspace.show(); _Events_Flush(qapp)
                    assert ground.board_combo.isVisible()
                    assert ground.import_directory.isVisible()
                    assert flight.import_directory_button.isVisible()
                    assert workspace.target_cards['ground'].geometry().bottom() < 950
                    assert workspace.target_cards['flight'].geometry().right() <= width
        assert model.Dictionary_Get() == before
    finally:
        workspace.close()


def test_problem_reveal_opens_exact_target_details_and_preserves_fold_state(qapp):
    translator = Translator('en_US')
    devices, flight, ground, air = _Editors_Create(translator)
    workspace = HardwareWorkspacePage(translator, devices, flight, ground, air)
    try:
        workspace.resize(1000, 900); workspace.show(); _Events_Flush(qapp)
        workspace._target_sections['ground'].toggle_button.setChecked(False)
        state = workspace.ExpandedState_Get()
        assert workspace.Reveal(ground.platform_values['part'])
        _Events_Flush(qapp)
        assert workspace._target_sections['ground'].Expanded_Is()
        assert workspace._sections['ground.platform'].Expanded_Is()
        assert not workspace._sections['flight.platform'].Expanded_Is()
        workspace.ExpandedState_Set(state)
        assert workspace.ExpandedState_Get() == state
        assert workspace.Reveal(flight)
        assert not workspace.Reveal(None)
    finally:
        workspace.close()


def test_checks_uses_original_separate_generation_commands(qapp, workspace_root):
    translator = Translator('zh_CN')
    devices, flight, ground, air = _Editors_Create(translator)
    workspace = HardwareWorkspacePage(translator, devices, flight, ground, air)
    checks = BuildPage(translator)
    checks.TargetEditors_Attach(flight, ground)
    checks.TargetEditors_Attach(flight, ground)
    model = FccgService(workspace_root).ReferenceProject_Create('TargetCommands')
    before = deepcopy(model.Dictionary_Get())
    checks.TargetConfiguration_Set(model)
    flight_calls, ground_calls = QSignalSpy(flight.generateRequested), QSignalSpy(ground.generateRequested)
    try:
        checks.resize(740, 900); checks.show(); _Events_Flush(qapp)
        for button, calls in ((flight.generate_button, flight_calls), (ground.generate_button, ground_calls)):
            button.setEnabled(True)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            assert calls.count() == 1
            assert checks.isAncestorOf(button)
            assert button.geometry().width() > 0
        assert checks.advanced_section.isAncestorOf(ground.build_group)
        assert not checks.advanced_section.Expanded_Is()
        assert model.Dictionary_Get() == before
    finally:
        checks.close(); workspace.close()


@pytest.mark.parametrize('width', [900, 1024])
@pytest.mark.parametrize('language,theme', [('zh_CN','light'), ('en_US','dark')])
def test_actual_window_first_screen_contains_both_target_imports(qapp, workspace_root, tmp_path, width, language, theme):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QMessageBox, QScrollArea
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.ui.main_window import MainWindow
    _Fonts_Register()
    previous_font = qapp.font()
    qapp.setFont(QFont('Microsoft YaHei', 9))
    service = FccgService(workspace_root)
    service.policy = WorkspacePolicy(workspace_root.parents[1])
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    window._model = service.ReferenceProject_Create('CompactHardware')
    window._Project_Refresh()
    before = deepcopy(window._model.Dictionary_Get())
    try:
        window.Language_Apply(language)
        window.Theme_Apply(theme)
        window.resize(width, 768); window.show(); _Events_Flush(qapp)
        assert window.width() == width
        workspace = window.hardware_workspace
        viewport = workspace.findChild(QScrollArea).viewport()
        for owner in (window.board_hardware_page, window.ground_target_page):
            for control in (owner.board_combo, owner.import_directory_button):
                bounds = QRect(control.mapTo(viewport, control.rect().topLeft()), control.size())
                assert viewport.rect().contains(bounds), (control.objectName(), bounds, viewport.rect())
        assert workspace.findChild(QScrollArea).widget().width() <= viewport.width()
        project_bounds = QRect(window.current_project_value.mapTo(window, window.current_project_value.rect().topLeft()),
                               window.current_project_value.size())
        assert window.rect().contains(project_bounds)
        for control in (window.language_combo, window.theme_combo):
            bounds = QRect(control.mapTo(window, control.rect().topLeft()), control.size())
            assert window.rect().contains(bounds)
            assert not project_bounds.intersects(bounds)
        rows = workspace._device_rows['flight']
        assert len(rows) == len(set(rows))
        assert len(rows) == len(window._model.device_instances)
        assert len(workspace.device_summaries['flight'].text().splitlines()) <= 4
        assert workspace.device_summaries['flight'].toolTip() == '\n'.join(rows)
        assert window._model.Dictionary_Get() == before
        evidence = workspace_root.parents[1]/'.work/caps3_20261025/hardware/final_en'
        evidence.mkdir(parents=True,exist_ok=True)
        assert window.grab().save(str(evidence/f'hardware_{language}_{theme}_{width}.png'))
    finally:
        window._project_dirty = False
        window.close(); _Events_Flush(qapp)
        qapp.setFont(previous_font)
