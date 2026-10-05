from pathlib import Path
import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.model import ProjectModel_Load, ProjectModel_Save
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.project.configuration import ModeOptionAvailabilities_Get
from silverstar_fccg.generator.render import _FlightConfigHeader_Render


@pytest.mark.parametrize('replacement', ['silverstar.device.imu.jy901b', 'silverstar.device.imu.bmi088'])
@pytest.mark.parametrize('gnss', [True, False])
def test_gui_imu_remove_restore_selects_legal_defaults_and_roundtrips(qtbot, tmp_path, workspace_root, replacement, gnss):
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=FccgService(workspace_root))
    qtbot.addWidget(window)
    errors = []
    window._Error_Show = errors.append
    window._model = window._service.ReferenceProject_Create('RestoreSelections')
    window._Project_Refresh()
    if not gnss:
        window._DeviceInstance_Change('gnss0', '')
    window._DeviceInstance_Change('imu0', '')
    assert window._model.strategies['ins'] is None
    assert window._model.strategies['alignment'] is None
    window._DeviceInstance_Change('imu0', replacement)
    model = window._model
    assert not errors
    assert model.strategies['ins'] == 'silverstar.algorithm.ins.coning2_sculling2'
    assert model.strategies['alignment'] == 'silverstar.algorithm.alignment.vector_constraints'
    assert model.strategies['estimator'] == ('silverstar.algorithm.estimator.kf6' if gnss or replacement.endswith('jy901b') else None)
    assert 'Tilt' in model.modes['deployment']
    assert ModeOptionAvailabilities_Get(model, window._service.catalog)[('deployment', 'Tilt')].available
    for slot, selected in model.strategies.items():
        assert window.flight_configuration_page.strategy_combos[slot].currentData() == selected
    checked = {str(check.property('selectionOption')) for check in window.flight_configuration_page.mode_checks['deployment'] if check.isChecked()}
    assert checked == set(model.modes['deployment'])
    if replacement.endswith('jy901b'):
        combo = window.devices_page.orientation_combos['imu0']
        assert all('(' not in combo.itemText(i) and '\uff08' not in combo.itemText(i) for i in range(combo.count()))
        assert combo.toolTip()
    path = tmp_path / 'roundtrip.ssproject'
    ProjectModel_Save(model, path, window._service.policy)
    restored = ProjectModel_Load(path)
    assert restored.strategies == model.strategies and restored.modes == model.modes
    assert _FlightConfigHeader_Render(restored, window._service.catalog) == _FlightConfigHeader_Render(model, window._service.catalog)
    before = model.Dictionary_Get()
    window._Project_Refresh()
    assert window._model.Dictionary_Get() == before
    window.close()


def test_explicitly_disabled_legal_options_stay_disabled(qtbot, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=FccgService(workspace_root))
    qtbot.addWidget(window)
    window._model = window._service.ReferenceProject_Create('ExplicitOff')
    window._model.strategies['estimator'] = None
    window._model.modes['deployment'] = []
    window._Project_Refresh()
    window._Jy901bOrientation_Change('imu0', 'vertical')
    assert window._model.strategies['estimator'] is None
    assert window._model.modes['deployment'] == []
    window._DeviceInstance_Change('imu0', '')
    window._DeviceInstance_Change('imu0', 'silverstar.device.imu.bmi088')
    assert window._model.strategies['estimator'] is None
    assert window._model.modes['deployment'] == []
    window.close()
