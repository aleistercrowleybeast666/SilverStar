from copy import deepcopy

import pytest

from silverstar_fccg.project.model import ProjectModel_Save
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import _FlightConfigHeader_Render
from test_scg_ui_metadata_hotfix import window


STORAGE = 'silverstar.device.storage.sd_sdio_fatfs'


@pytest.mark.parametrize('origin', ['draft', 'reference', 'import'])
def test_compact_default_keeps_logging_and_storage_without_delete_buttons(window, tmp_path, workspace_root, origin):
    if origin == 'draft':
        window._model = window._service.ProjectDraft_Create('CompactDefault')
    elif origin == 'reference':
        window._model = ReferenceProject_Create(catalog=window._service.catalog)
    else:
        source = workspace_root.parents[1] / 'docs/evidence/logger_health_retest_20261008/generated_config.ssproject'
        window._model = window._service.Project_Open(source)
    window._Project_Refresh()
    for tier in ('standard', 'compact', 'minimal', 'compact'):
        window._FeatureTier_Change(tier)
        assert window._model.protocols['logging'] is not None
        assert window._model.DeviceInstance_Get('storage0') is not None
        assert 'storage0' not in window.devices_page.remove_buttons
        assert window.flight_configuration_page.logging_table.isEnabled()
        if tier == 'compact':
            import re
            header = _FlightConfigHeader_Render(window._model, window._service.catalog)
            assert re.search(r'SYSTEM_LOG_RECORD_QUEUE_DEPTH\s+56U', header)
            assert re.search(r'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH\s+16U', header)


def test_compact_restores_only_transport_cleared_logging_choice(window):
    window._model = window._service.ProjectDraft_Create('RestoreLogTransport')
    window._Project_Refresh()
    choice = deepcopy(window._model.protocols['logging'])
    window.devices_page.device_checks[STORAGE].click()
    assert window._model.protocols['logging'] is None
    window.devices_page.device_checks[STORAGE].click()
    assert window._model.DeviceInstance_Get('storage0') is not None
    assert window._model.protocols['logging'] is None
    window._FeatureTier_Change('compact')
    assert window._model.protocols['logging'] == choice
    assert window.flight_configuration_page.logging_table.isEnabled()
    assert all(stream.enabled for stream in window._model.logging_streams
               if stream.record in ('FLIGHT_LOG_RECORD_SF6_STATE', 'FLIGHT_LOG_RECORD_SF6_MEASUREMENT'))


def test_explicit_disabled_logging_survives_tier_switch_and_import(window, tmp_path):
    window._model = window._service.ProjectDraft_Create('ExplicitNoLog')
    window._Project_Refresh()
    window.devices_page.device_checks[STORAGE].click()
    window.devices_page.device_checks[STORAGE].click()
    window._ProtocolProfile_Change('logging', None)
    for tier in ('standard', 'compact', 'minimal', 'compact'):
        window._FeatureTier_Change(tier)
        assert (window._model.protocols['logging'] is None) == (tier != 'minimal')
    path = tmp_path / 'ExplicitNoLog.ssproject'
    ProjectModel_Save(window._model, path, window._service.policy)
    original = path.read_bytes()
    window._Project_Open(path)
    window._Project_Refresh()
    assert window._model.protocols['logging'] is None
    assert path.read_bytes() == original


def test_compact_does_not_restore_logging_without_storage(window):
    window._model = window._service.ProjectDraft_Create('NoLogStorage')
    window._Project_Refresh()
    window.devices_page.device_checks[STORAGE].click()
    window._FeatureTier_Change('compact')
    assert window._model.protocols['logging'] is None
    assert window._model.DeviceInstance_Get('storage0') is None


def test_reopen_does_not_inherit_session_transport_restore(window, tmp_path):
    window._model = window._service.ProjectDraft_Create('SessionLog')
    path = tmp_path / 'SilverStar.ssproject'
    ProjectModel_Save(window._model, path, window._service.policy)
    window._Project_Open(path)
    window.devices_page.device_checks[STORAGE].click()
    window.devices_page.device_checks[STORAGE].click()
    ProjectModel_Save(window._model, path, window._service.policy)
    original = path.read_bytes()
    window._Project_Open(path)
    window._FeatureTier_Change('compact')
    assert window._model.protocols['logging'] is None
    assert path.read_bytes() == original
