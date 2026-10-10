"""Ordinary new-project UI selections; never load a private candidate model."""
from pathlib import Path
from copy import deepcopy
import json,time
import pytest
from conftest import qapp,builtin_catalog,workspace_root
from PySide6.QtWidgets import QFileDialog,QMessageBox
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.app.usb_ground_flow import UsbGroundOutput_Get
from silverstar_fccg.project.model import ProjectModel_Load


@pytest.fixture(params=['F103','C071'])
def usb_window(request,qapp,tmp_path_factory,builtin_catalog,monkeypatch):
    root=tmp_path_factory.mktemp('ordinary_window')
    service=FccgService(root);service.catalog=builtin_catalog;service.assembler.catalog=builtin_catalog
    service.hardware_importer=CubeMxImporter(service.policy,root/'imports')
    current=MainWindow(SettingsStore(root/'settings.ini'),service=service)
    current._MessageBox_Exec=lambda *a,**k:QMessageBox.StandardButton.Discard
    errors=[];monkeypatch.setattr(current,'_Error_Show',lambda *a:errors.append(a))
    source=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-08\task\usb-validation\cube-f103-usb' if request.param=='F103' else
                r'C:\Users\chdxm\Documents\Codex\2026-10-08\task\c071-cubemx-input\full-native-clean\C071FBP6_PCD_TEST')
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a:str(source))
    try:yield current,source,errors,request.param
    finally:current.close();qapp.processEvents()


def test_new_draft_existing_usb_user_entry(usb_window,qapp,tmp_path_factory):
    current,source,errors,part=usb_window
    current._model=current._service.ProjectDraft_Create('USB existing user entry '+part)
    current._project_root=tmp_path_factory.mktemp('ordinary_project')
    current._Project_Refresh()
    assert current._model.ground_target.enabled
    assert current._model.ground_target.pc_interface=='uart'
    assert current._model.ground_target.hardware.inventory.get('native_ground_backend') is None
    previous=deepcopy(current._model.Dictionary_Get())
    combo=current.ground_target_page.pc_interface
    assert combo.isEnabled()
    index=combo.findData('usb_cdc');assert index>=0
    combo.setCurrentIndex(index)
    assert current._model.ground_target.pc_interface=='usb_cdc'
    assert current._model.ground_target.radio_plugin==previous['ground_target']['radio_plugin']
    assert current._model.air_link.radio_family=='sx128x'
    # Existing button signal, not a backend API or injected bound model.
    current.ground_target_page.import_directory_button.click()
    deadline=time.monotonic()+60
    while current._active_worker is not None and time.monotonic()<deadline:
        qapp.processEvents();time.sleep(0.01)
    assert current._active_worker is None
    assert not errors,errors
    assert current._model.ground_target.hardware.mcu==('STM32F103C8T6' if part=='F103' else 'STM32C071FBP6')
    assert all(view.fixed and not view.validation_error for view in current.ground_target_page._resources)
    current._Project_Save();assert not errors,errors
    saved=deepcopy(current._model.Dictionary_Get())
    current._Project_Open(current._project_root);assert not errors,errors
    assert json.dumps(current._model.Dictionary_Get(),sort_keys=True)==json.dumps(saved,sort_keys=True)
    assert current.ground_target_page.generate_button.isEnabled()
    current.ground_target_page.generate_button.click()
    deadline=time.monotonic()+60
    while current._active_worker is not None and time.monotonic()<deadline:
        qapp.processEvents();time.sleep(0.01)
    assert current._active_worker is None
    assert not errors,errors
    assert current.progress_bar.property('taskState')=='success'
    output=UsbGroundOutput_Get(current._service,current._model,current._project_root)
    assert (output/'Makefile').is_file()
    assert 'BLOCKED' in current.status_label.text()
    (current._project_root/'ordinary-user-entry.json').write_text(json.dumps({
        'part':part,'scope':'ProjectDraft_Create default, existing USB combo/import-directory button/save/reload/generate button',
        'source':str(source),'output':str(output),'backend_loaded_private_model':False,
        'formal_release':False,'build_route':'Same existing ground Build handler exercised by ug08; no new ARM build claimed here'
    },indent=2),encoding='utf8')
