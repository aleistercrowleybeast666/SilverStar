"""Actual ordinary UI handlers and exact first-batch backend, no hardware."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Event
import hashlib,json,os,time
import pytest
from PySide6.QtWidgets import QFileDialog,QMessageBox,QWidget
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.usb_ground_flow import UsbGroundOutput_Get,UsbGroundOptions_Get,UsbGroundFlow_Run
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.task import TaskContext,TaskCancelledError
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.build.runner import BuildAction
from test_task_progress_busy import _Wait

@pytest.fixture(params=['F103','C071'])
def usb_window(request,qapp,tmp_path_factory,builtin_catalog,monkeypatch):
    root=tmp_path_factory.mktemp('w')
    service=FccgService(root)
    service.catalog=builtin_catalog
    service.assembler.catalog=builtin_catalog
    service.hardware_importer=CubeMxImporter(service.policy,root/'i')
    current=MainWindow(SettingsStore(root/'s.ini'),service=service)
    current._MessageBox_Exec=lambda *a,**k:QMessageBox.StandardButton.Discard
    current._model=ProjectModel_Load(Path(os.environ['SILVERSTAR_NATIVE_BACKEND_CONFIG']))
    source=(Path(os.environ['SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT'])/'cube-f103-usb' if request.param=='F103'
            else Path(os.environ['SILVERSTAR_C071_NATIVE']))
    errors=[]
    monkeypatch.setattr(current,'_Error_Show',lambda *a:errors.append(a))
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a: str(source))
    try:yield current,source,errors,request.param
    finally:current.close();qapp.processEvents()

def _Import(qapp,window):
    current,source,errors,part=window
    current._GroundCubeMxImport_Request(True)
    _Wait(qapp,lambda:current._active_worker is None)
    assert not errors,errors
    assert current._model.ground_target.mcu==''
    assert current._model.ground_target.resource_assignments['radio0:spi']=='SPI1'
    assert {view.key:view.assignment for view in current.ground_target_page._resources}==current._model.ground_target.resource_assignments
    assert all(view.fixed and not view.validation_error for view in current.ground_target_page._resources)
    assert current._model.ground_target.hardware.mcu==('STM32F103C8T6' if part=='F103' else 'STM32C071FBP6')
    assert current.progress_bar.property('taskState')=='success'
    return deepcopy(current._model.Dictionary_Get())

def test_real_gui_import_save_reload_export_and_artifact_state(usb_window,qapp,tmp_path_factory):
    current,source,errors,part=usb_window
    before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    model=_Import(qapp,usb_window)
    project=tmp_path_factory.mktemp('p')
    current._project_root=project
    current._Project_Save()
    assert not errors,errors
    (project/'before-save.json').write_text(json.dumps(model,indent=2),encoding='utf8')
    assert json.dumps(ProjectModel_Load(project/'SilverStar.ssproject').Dictionary_Get(),sort_keys=True)==json.dumps(model,sort_keys=True)
    current._Project_Open(project)
    assert not errors,errors
    assert json.dumps(current._model.Dictionary_Get(),sort_keys=True)==json.dumps(model,sort_keys=True)
    assert current.ground_target_page.generate_button.isEnabled()
    current.ground_target_page.generate_button.click()
    _Wait(qapp,lambda:current._active_worker is None)
    assert not errors,errors
    output=UsbGroundOutput_Get(current._service,current._model,project)
    assert output.is_dir() and not output.is_relative_to(project)
    assert current.progress_bar.property('taskState')=='success'
    assert 'BLOCKED' in current.status_label.text()
    assert current.build_page.action_buttons['ground_build'].isEnabled() is False  # tools not detected yet
    assert current.build_page.action_buttons['ground_open_folder'].isEnabled()
    current._TargetAction_Request('ground_artifact_check')
    assert errors and 'not compiled' in str(errors[-1])
    assert before=={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    (project/'gui-flow-test-receipt.json').write_text(json.dumps({'part':part,'source':str(source),'project':str(project),'output':str(output),'model':model,'result':'Actual import/save/reload/private export handlers executed; rendered output correctly refuses compiled artifact claim'},indent=2),encoding='utf8')

@pytest.mark.parametrize('operation',['generate','build'])
def test_real_gui_build_progress_and_cancel(usb_window,qapp,tmp_path_factory,monkeypatch,operation):
    current,source,errors,part=usb_window
    _Import(qapp,usb_window)
    current._project_root=tmp_path_factory.mktemp('p')
    observed=[]
    original=current._Task_Progress
    def progress(value,code):observed.append(value);original(value,code)
    monkeypatch.setattr(current,'_Task_Progress',progress)
    current._UsbGroundOperation_Request(operation)
    _Wait(qapp,lambda:len(observed)>3 or current._active_worker is None)
    assert current._active_worker is not None,errors
    current._Task_Cancel()
    _Wait(qapp,lambda:current._active_worker is None)
    assert not errors,errors
    assert current.progress_bar.property('taskState')=='cancelled'
    assert current.progress_bar.value()<1000
    assert not (current._project_root/'.fccg/usb-candidate.json').exists()
    outputs=[p for p in current._project_root.parent.glob('usb-*') if (p/'backend-receipt.json').exists()]
    assert outputs
    last=max(outputs,key=lambda p:p.stat().st_mtime_ns)
    backend=json.loads((last/'backend-receipt.json').read_text())
    if operation=='build':
        receipt=json.loads((last/'receipt.json').read_text())
        assert receipt['status']=='CANCELLED'
        assert 0<len(receipt['commands'])<receipt['planned_command_total']
        assert backend['status']=='FailedCandidate'
    else:
        assert backend['status']=='FAILED_RENDER'

def test_real_gui_success_build_and_quality(usb_window,qapp,tmp_path_factory,monkeypatch):
    assert os.environ.get('SILVERSTAR_USB_BACKEND_ARM')=='1'
    current,source,errors,part=usb_window
    _Import(qapp,usb_window)
    current._project_root=tmp_path_factory.mktemp('p')
    compiler='D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe'
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(compiler,''))
    assert current._ToolchainBrowse('compiler')
    assert not errors,errors
    current.build_page.actionRequested.emit('ground_build')
    deadline=time.monotonic()+240
    while current._active_worker is not None and time.monotonic()<deadline:
        qapp.processEvents();time.sleep(0.01)
    assert current._active_worker is None
    assert not errors,errors
    assert current.progress_bar.property('taskState')=='success'
    output=UsbGroundOutput_Get(current._service,current._model,current._project_root,compiled=True)
    compiler=json.loads((output/'receipt.json').read_text())
    assert len(compiler['commands'])==compiler['planned_command_total']
    assert compiler['warning_diagnostics']==[]
    assert (output/'build/native.elf').is_file() and (output/'build/analysis/native.elf').is_file()
    current._TargetAction_Request('ground_artifact_check')
    assert not errors,errors
    with Path(os.environ['SILVERSTAR_USB_BACKEND_BUILD_INDEX']).open('a',encoding='utf8') as f:
        f.write(json.dumps({'part':current._model.ground_target.hardware.mcu,'output':str(output),'project_root':str(current._project_root),'backend_receipt_sha256':hashlib.sha256((output/'backend-receipt.json').read_bytes()).hexdigest()})+'\n')
    monkeypatch.setattr(current.build_page,'QualityTargets_Get',lambda:('ground',))
    for action in (BuildAction.ARCHITECTURE_CHECK,BuildAction.ARTIFACT_CHECK):
        current._QualityChecks_Request(action)
        # Real artifact audits run ARM tools over both links; the generic UI
        # helper's ten-second budget is for short tasks, not compiler audits.
        deadline=time.monotonic()+120
        while current._active_worker is not None and time.monotonic()<deadline:
            qapp.processEvents();time.sleep(0.01)
        assert current._active_worker is None, 'bounded real quality audit wait expired'
        assert not errors,errors
        assert current.progress_bar.property('taskState')=='success'
        assert 'BLOCKED' in current.build_page.target_quality_status['ground'].text()
    elf=output/'build/native.elf';original=elf.read_bytes()
    try:
        elf.write_bytes(original+b'ordinary-stale-artifact')
        current._TargetAction_Request('ground_artifact_check')
        assert errors and 'changed' in str(errors[-1])
        (current._project_root/'stale-artifact-test.json').write_text(json.dumps({'part':part,'detected':str(errors[-1]),'original_elf_sha256':hashlib.sha256(original).hexdigest()}),encoding='utf8')
    finally:
        elf.write_bytes(original)
    assert UsbGroundOutput_Get(current._service,current._model,current._project_root,compiled=True)==output

def test_gui_import_unknown_configuration_preserves_model(usb_window,qapp,tmp_path_factory,monkeypatch):
    current,source,errors,part=usb_window
    root=tmp_path_factory.mktemp('x');ioc=root/'unknown.ioc'
    ioc.write_text('Mcu.CPN=STM32F103CBT6\nMcu.Name=STM32F103CBTx\n',encoding='utf8')
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a:str(root))
    before=deepcopy(current._model.Dictionary_Get())
    current._GroundCubeMxImport_Request(True)
    _Wait(qapp,lambda:current._active_worker is None)
    assert errors and current._model.Dictionary_Get()==before
    assert current.progress_bar.property('taskState')=='error'


def test_tool_location_change_preserves_native_bindings(usb_window,qapp,monkeypatch):
    current,source,errors,part=usb_window
    _Import(qapp,usb_window)
    before=deepcopy(current._model.ground_target)
    compiler='D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe'
    assert Path(compiler).is_file()
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(compiler,''))
    assert current._ToolchainBrowse('compiler')
    assert not errors,errors
    assert current._model.ground_target==before
    assert current._model.build.tool_paths['compiler']==compiler
    current._service.UsbGroundCandidate_Plan(current._model,**UsbGroundOptions_Get(current._model.ground_target.hardware.mcu))
