from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
from test_scg_ui_metadata_hotfix import window


def _Count(window, kind):
    return sum(window._service.Plugin_Get(item.plugin).component_class == kind
               for item in window._model.device_instances)


def test_switch_delete_add_restore_and_minimal_gnss_entrypoints(window, tmp_path):
    window._model = ReferenceProject_Create(catalog=window._service.catalog)
    window._Project_Refresh()
    errors = []
    window._Error_Show = errors.append
    for tier in ('compact', 'minimal'):
        window._FeatureTier_Change(tier)
        for kind in ('imu', 'gnss', 'telemetry'):
            assert not window.devices_page.add_buttons[kind].isEnabled()
            before = _Count(window, kind)
            window._DeviceInstance_Add(kind)
            assert _Count(window, kind) == before
        # The inactive GNSS choice is visible, yet cannot be enabled anew.
        if tier == 'minimal':
            combo = window.devices_page.device_combos['gnss0']
            assert all(not combo.model().item(i).isEnabled() for i in range(1, combo.count()))
            window._DeviceInstance_Change('gnss0', '')
            window._DeviceInstance_Change('gnss0', 'silverstar.device.gnss.neo_m9n')
            assert _Count(window, 'gnss') == 0 and errors
        window._DeviceInstance_Change('imu0', '')
        assert window.devices_page.add_buttons['imu'].isEnabled()
        window._DeviceInstance_Add('imu')
        assert _Count(window, 'imu') == 1
        assert not window.devices_page.add_buttons['imu'].isEnabled()
    for tier in ('full', 'standard'):
        window._FeatureTier_Change(tier)
        assert window.devices_page.add_buttons['imu'].isEnabled()
        assert window.devices_page.add_buttons['gnss'].isEnabled()
        assert window.devices_page.add_buttons['telemetry'].isEnabled()


@pytest.mark.parametrize('tier', ['compact', 'minimal'])
def test_import_save_reopen_retains_conflicts_and_notice(window, tmp_path, tier):
    model = ReferenceProject_Create(catalog=window._service.catalog)
    model.device_instances.append(DeviceInstance('imu_extra', 'silverstar.device.imu.mpu6050'))
    model.build = replace(model.build, feature_tier=tier)
    model.strategies['estimator'] = 'silverstar.algorithm.estimator.sf6'
    if tier == 'minimal':
        model.protocols['maintenance'] = None
    expected = deepcopy([item for item in model.device_instances if item.instance_id != 'maintenance0'])
    path = tmp_path/'SilverStar.ssproject'
    ProjectModel_Save(model, path, window._service.policy)
    errors = []; window._Error_Show = errors.append
    window._Project_Open(path)
    assert not errors
    assert [item for item in window._model.device_instances if item.instance_id != 'maintenance0'] == expected
    assert window.devices_page.feature_tier_notice.text()
    with pytest.raises(SourceGraphError, match='at most one|GNSS'):
        SourceGraph_Resolve(window._model, window._service.catalog)
    ProjectModel_Save(window._model, path, window._service.policy)
    window._Project_Open(path)
    assert [item for item in window._model.device_instances if item.instance_id != 'maintenance0'] == expected
