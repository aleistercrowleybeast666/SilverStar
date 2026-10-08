from copy import deepcopy
from dataclasses import replace

import pytest

from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse, ProjectModel_Save
from silverstar_fccg.project.model import _ProjectV9_Migrate
from silverstar_fccg.project.protocols import ProtocolProfileAvailabilities_Get
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.storage_binding import StorageBinding_Resolve
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
from test_scg_ui_metadata_hotfix import window


_F4_STORAGE = 'silverstar.device.storage.sd_sdio_fatfs'
_F1_STORAGE = _F4_STORAGE + '_f1'
_MAINTENANCE = ('silverstar.protocol.maintenance.serial_0_0', 'maintenance.serial.0_0')


@pytest.mark.parametrize('storage', [_F4_STORAGE, _F1_STORAGE])
def test_legacy_storage_default_injection_preserves_existing_card(storage):
    old = {'format_version': 9, 'components': {'board': 'silverstar.board.silverstar_0_5',
        'devices': [{'instance_id': 'existing_card', 'plugin': storage}]},
        'resources': {}, 'generated_glue': []}
    original = deepcopy(old)
    migrated = _ProjectV9_Migrate(old)
    assert migrated['components']['devices'] == original['components']['devices']
    assert old == original


@pytest.mark.parametrize('mcu,storage', [
    ('silverstar.mcu.stm32f407vet6', _F4_STORAGE),
    ('silverstar.mcu.stm32f103ret6', _F1_STORAGE),
    ('silverstar.mcu.stm32f103rft6', _F1_STORAGE),
])
def test_storage_platform_candidates_and_repeated_refresh(window, mcu, storage):
    model = window._service.ProjectDraft_Create('StorageCandidates')
    model.mcu = mcu
    window._model = ProjectConfiguration_Reconcile(model, window._service.catalog).model
    original = deepcopy(window._model.device_instances)
    for _ in range(3):
        window._Project_Refresh()
        storage_checks = {key: check for key, check in window.devices_page.device_checks.items()
                          if key in (_F4_STORAGE, _F1_STORAGE)}
        assert set(storage_checks) == {storage}
        assert storage_checks[storage].isChecked()
        assert storage_checks[storage].isEnabled()
        assert window._model.device_instances == original
        assert sum(item.plugin in (_F4_STORAGE, _F1_STORAGE) for item in original) == 1


def test_selected_unavailable_storage_can_be_removed(window):
    window._model = window._service.ProjectDraft_Create('StorageRemoval')
    # A prepared hardware contract with no SDIO makes the selected card unavailable.
    window._model.hardware = replace(window._model.hardware, snapshot_id='missing-sdio',
        mcu='STM32F407VET6', inventory={'mcu_part': 'STM32F407VET6',
            'mcu_family': 'STM32F4', 'package': 'LQFP100', 'core': 'Cortex-M4'})
    window._Project_Refresh()
    check = window.devices_page.device_checks[_F4_STORAGE]
    assert not window._service.DeviceSelectionAvailabilities_Get(window._model)[_F4_STORAGE].available
    assert check.isChecked() and check.isEnabled()
    errors = []
    window._Error_Show = errors.append
    check.click()
    assert not errors
    assert not any(item.plugin in (_F4_STORAGE, _F1_STORAGE) for item in window._model.device_instances)
    window._Project_Refresh()
    assert not window.devices_page.device_checks[_F4_STORAGE].isChecked()
    assert StorageBinding_Resolve(window._model, window._service.catalog).issues[0].code == 'STORAGE_DEVICE_REQUIRED'


def test_switch_save_reopen_keeps_one_storage_and_maintenance_policy(window, tmp_path):
    window._model = ReferenceProject_Create(catalog=window._service.catalog)
    window._Project_Refresh()
    original_maintenance = deepcopy(window._model.protocols['maintenance'])
    errors = []
    window._Error_Show = errors.append
    for tier in ('compact', 'minimal', 'compact', 'full'):
        window._FeatureTier_Change(tier)
        assert sum(item.plugin in (_F4_STORAGE, _F1_STORAGE)
                   for item in window._model.device_instances) == 1
        assert window._model.protocols['maintenance'] == (None if tier == 'minimal' else original_maintenance)
        assert any(item.instance_id == 'maintenance0' for item in window._model.device_instances) == (tier != 'minimal')
        for _ in range(2):
            window._Project_Refresh()
        path = tmp_path / 'SilverStar.ssproject'
        ProjectModel_Save(window._model, path, window._service.policy)
        window._Project_Open(path)
        assert sum(item.plugin in (_F4_STORAGE, _F1_STORAGE)
                   for item in window._model.device_instances) == 1
        SourceGraph_Resolve(window._model, window._service.catalog)
    assert not errors


def test_minimal_maintenance_cannot_be_reenabled_by_gui(window):
    window._model = ReferenceProject_Create(catalog=window._service.catalog)
    window._Project_Refresh()
    window._FeatureTier_Change('minimal')
    availability = ProtocolProfileAvailabilities_Get(window._model, window._service.catalog)
    assert not availability[('maintenance', *_MAINTENANCE)].available
    errors = []
    window._Error_Show = errors.append
    window._ProtocolProfile_Change('maintenance', _MAINTENANCE)
    assert errors
    assert window._model.protocols['maintenance'] is None
    assert window._model.DeviceInstance_Get('maintenance0') is None


def test_storage_direct_entrypoint_rejects_wrong_platform_and_second_card(window):
    window._model = window._service.ProjectDraft_Create('StorageEntryGuard')
    window._Project_Refresh()
    original = deepcopy(window._model.device_instances)
    errors = []
    window._Error_Show = errors.append
    window._OtherDevice_Toggle(_F1_STORAGE, True)
    assert errors and window._model.device_instances == original
    window._DeviceInstance_Change('extra_card', _F4_STORAGE)
    assert len(errors) == 2 and window._model.device_instances == original


def test_duplicate_import_has_individual_storage_removal(window, tmp_path):
    model = ReferenceProject_Create(catalog=window._service.catalog)
    model.device_instances.append(DeviceInstance('extra_card', _F4_STORAGE))
    path = tmp_path / 'SilverStar.ssproject'
    ProjectModel_Save(model, path, window._service.policy)
    errors = []
    window._Error_Show = errors.append
    window._Project_Open(path)
    assert len([item for item in window._model.device_instances if item.plugin == _F4_STORAGE]) == 2
    assert 'storage0' in window.devices_page.remove_buttons
    assert 'extra_card' in window.devices_page.remove_buttons
    window.devices_page.remove_buttons['extra_card'].click()
    assert not errors
    assert window._model.DeviceInstance_Get('extra_card') is None
    assert window._model.DeviceInstance_Get('storage0') is not None
    SourceGraph_Resolve(window._model, window._service.catalog)


def test_old_official_project_open_does_not_inject_storage(window, tmp_path, workspace_root):
    source = workspace_root.parents[1] / 'docs/evidence/logger_health_retest_20261008/generated_config.ssproject'
    original = source.read_bytes()
    path = tmp_path / 'SilverStar.ssproject'
    path.write_bytes(original)
    errors = []
    window._Error_Show = errors.append
    for _ in range(2):
        window._Project_Open(path)
        assert not errors
        assert window._model.identity.firmware_version == '0.1.2'
        assert sum(item.plugin in (_F4_STORAGE, _F1_STORAGE)
                   for item in window._model.device_instances) == 1
        assert set(key for key in window.devices_page.device_checks
                   if key in (_F4_STORAGE, _F1_STORAGE)) == {_F4_STORAGE}
        window._Project_Refresh()
    assert path.read_bytes() == original and source.read_bytes() == original


def test_illegal_import_retained_and_generation_rejected(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    maintenance = model.protocols['maintenance']
    FeatureTier_Apply(model, 'minimal', builtin_catalog)
    model.protocols['maintenance'] = maintenance
    imported = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(imported, builtin_catalog)
    assert reconciled.model.protocols['maintenance'] == maintenance
    with pytest.raises(SourceGraphError, match='maintenance disabled'):
        SourceGraph_Resolve(reconciled.model, builtin_catalog)
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances.append(DeviceInstance('extra_card', _F4_STORAGE))
    imported = ProjectModel_Parse(model.Dictionary_Get())
    reconciled = ProjectConfiguration_Reconcile(imported, builtin_catalog)
    assert len([item for item in reconciled.model.device_instances if item.plugin == _F4_STORAGE]) == 2
    assert StorageBinding_Resolve(reconciled.model, builtin_catalog).issues[0].code == 'STORAGE_DEVICE_AMBIGUOUS'
    validation = Project_Validate(reconciled.model, builtin_catalog)
    assert not validation.valid
    assert any(issue.code == 'STORAGE_DEVICE_AMBIGUOUS' for issue in validation.issues)
