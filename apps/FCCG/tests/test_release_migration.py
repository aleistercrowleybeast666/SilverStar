from pathlib import Path
import hashlib
import json

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.alignment import AlignmentConfiguration, AlignmentConstraint
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Load
from silverstar_fccg.project.release_policy import (
    ReleaseCompatibilityIssues_Get, ReleaseMigrationModel_Create, ReleaseMigrationCopy_Save,
)
from silverstar_fccg.ui.main_window import MainWindow


def _Legacy_Create(service):
    model = service.ReferenceProject_Create('Legacy')
    model.device_instances.append(DeviceInstance('mag0','silverstar.device.magnetometer.lis3mdl'))
    model.capability_source_overrides['magnetometer.field'] = 'mag0'
    model.resource_assignments['mag0:bus'] = 'PLATFORM_I2C_0'
    model.alignment = AlignmentConfiguration(constraints=(AlignmentConstraint('gravity',2),
        AlignmentConstraint('magnetic_field',1.5,-7.25),
        AlignmentConstraint('reference_direction',0.75,body_axis='-Y',nav_azimuth_deg=235)))
    return model


def test_explicit_copy_preserves_all_old_settings_and_blocks_occupied_destination(tmp_path,workspace_root):
    service = FccgService(workspace_root)
    original = _Legacy_Create(service)
    before = original.Dictionary_Get()
    candidate = ReleaseMigrationModel_Create(original)
    assert not ReleaseCompatibilityIssues_Get(candidate)
    assert original.Dictionary_Get() == before
    assert candidate.alignment.constraints[1] == original.alignment.constraints[2]
    assert candidate.strategies['estimator'].endswith('.kf6')
    assert not candidate.log_decoder_profile.relative_path
    original_bytes = json.dumps(before,ensure_ascii=False).encode('utf-8')
    copy_root = tmp_path/'新工程_α'
    ReleaseMigrationCopy_Save(original,candidate,copy_root,original_bytes)
    assert (copy_root/'Compatibility/Legacy_Original.ssproject').read_bytes() == original_bytes
    assert json.loads((copy_root/'Compatibility/Legacy_Loaded.ssproject').read_text(encoding='utf-8')) == before
    saved = ProjectModel_Load(copy_root/'SilverStar.ssproject')
    assert saved.Dictionary_Get() == candidate.Dictionary_Get()
    assert all((copy_root/name).is_dir() for name in ('Flight_Controller','Ground_Station','Log'))
    with pytest.raises(ValueError,match='empty'):
        ReleaseMigrationCopy_Save(original,candidate,copy_root,original_bytes)
    with pytest.raises(ValueError,match='outside'):
        ReleaseMigrationCopy_Save(original,candidate,copy_root/'Log/new',original_bytes,copy_root)
    assert not (copy_root/'Log/new').exists()


def test_gui_legacy_open_cancel_failure_copy_and_reopen_are_transactional(qapp,tmp_path,workspace_root,monkeypatch):
    service = FccgService(workspace_root)
    original = _Legacy_Create(service)
    original_root = tmp_path/'original'
    service.ProjectRoot_Save(original,original_root,create_new=True)
    (original_root/'Log/old.BIN').write_bytes(b'immutable log')
    (original_root/'old.ssdecoder').write_bytes(b'unchanged original package')
    originals = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in original_root.rglob('*') if p.is_file()}
    window = MainWindow(SettingsStore(tmp_path/'migration.ini'),service=service)
    boxes=[]
    answer = [QMessageBox.StandardButton.Cancel]
    monkeypatch.setattr(window,'_MessageBox_Exec',lambda *a,**k: boxes.append((a,k)) or answer[0])
    window._Project_Open(original_root)
    assert window._model.Dictionary_Get() == original.Dictionary_Get()
    assert boxes[-1][0][0] == QMessageBox.Icon.Warning
    window._ReleaseMigration_Request()
    assert window._project_root == original_root
    answer[0] = QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:'')
    window._ReleaseMigration_Request()
    assert window._project_root == original_root
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(original_root))
    window._ReleaseMigration_Request()
    assert window._project_root == original_root
    assert boxes[-1][0][0] == QMessageBox.Icon.Critical
    copied = tmp_path/'supported_copy'
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(copied))
    window._ReleaseMigration_Request()
    assert window._project_root == copied
    assert not ReleaseCompatibilityIssues_Get(window._model)
    assert window._model.strategies['estimator'].endswith('.kf6')
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path,digest in originals.items())
    window._Project_Open(copied)
    assert not ReleaseCompatibilityIssues_Get(window._model)
    window.close()
