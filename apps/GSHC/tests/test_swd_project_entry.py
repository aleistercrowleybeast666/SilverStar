"""Fresh synthetic ARM ELF end-to-end; no device/probe access and no MCU execution."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event
from types import SimpleNamespace
import pytest
from test_swd_firmware import arm_elf as arm_elf_fixture
from test_swd_firmware import ImageMemory
from test_swd_ui import swd_panel,wait_for
from test_probe_ui import panel
from transport.swd_session import SwdSession
from transport.swd_firmware import DiagnosticResult as R
from services.swd_import import Firmware_ImportAuto
from silverstar_diagnostics.project_descriptor import (ProjectDescriptor_Create,
    ProjectDescriptor_Begin,ProjectDescriptor_Bind,ProjectBindingResult)

arm_elf=arm_elf_fixture


def project(root,arm_elf):
    root.mkdir();elf=root/'build/Release/fixture.elf';elf.parent.mkdir(parents=True)
    shutil.copyfile(arm_elf,elf)
    path=root/'Flight.ssdiag';path.write_text(json.dumps(ProjectDescriptor_Create('Test','STM32F407VET6')))
    assert ProjectDescriptor_Bind(path,elf)[0]==ProjectBindingResult.Ready
    return path,elf


def test_root_entry_finds_relative_elf_and_survives_project_move(arm_elf,tmp_path):
    path,elf=project(tmp_path/'original',arm_elf)
    reply=Firmware_ImportAuto([path]);assert reply.result==R.Ok,reply.detail
    assert reply.firmware.provenance=='build_bound' and all(not e.unavailable for e in reply.firmware.entries)
    moved=tmp_path/'moved';(tmp_path/'original').rename(moved)
    again=Firmware_ImportAuto([moved/'Flight.ssdiag'])
    assert again.result==R.Ok and again.firmware.sha256==reply.firmware.sha256
    assert json.loads((moved/'Flight.ssdiag').read_text())['builds']['build/Release']['elf']=='build/Release/fixture.elf'


def test_optional_protocol_metadata_is_explicit_and_old_root_stays_undeclared(arm_elf,tmp_path):
    path,elf=project(tmp_path/'project',arm_elf)
    old=Firmware_ImportAuto([path]);assert old.result==R.Ok
    assert 'maintenance' not in old.project_metadata
    doc=json.loads(path.read_text());declaration=dict(component='silverstar.protocol.maintenance.serial',package_version='0.1.0',profile='maintenance.serial.0_1')
    doc.update(project_file='SilverStar.ssproject',maintenance=declaration);path.write_text(json.dumps(doc))
    reply=Firmware_ImportAuto([path]);assert reply.result==R.Ok
    assert reply.firmware.sha256==old.firmware.sha256 and reply.project_metadata['maintenance']==declaration
    assert reply.project_metadata['project_file']=='SilverStar.ssproject' and doc['version']==1
    doc['maintenance']['profile']='invalid\nprofile';path.write_text(json.dumps(doc))
    rejected=Firmware_ImportAuto([path]);assert rejected.result!=R.Ok and rejected.project_metadata is None


def test_gui_reimport_clears_old_protocol_declaration_but_picker_cancel_preserves_it(arm_elf,tmp_path,swd_panel,monkeypatch):
    window,probes,create=swd_panel;opened=[];manager=create(lambda **kw:opened.append(kw))
    path,_=project(tmp_path/'project',arm_elf);doc=json.loads(path.read_text())
    doc['maintenance']=dict(component='silverstar.protocol.maintenance.serial',package_version='0.1.0',profile='maintenance.serial.0_1')
    path.write_text(json.dumps(doc));assert manager.import_files([path])
    wait_for(lambda:manager.import_worker is None)
    panel=window.maintenance_page.console
    assert manager.firmware is not None and '声明 0.1' in panel.protocol_status.text()
    monkeypatch.setattr('ui.swd_connection.QFileDialog.getOpenFileNames',lambda *a:([],''))
    assert not manager.import_files() and '声明 0.1' in panel.protocol_status.text()
    assert manager.import_files([tmp_path/'missing.ssdiag'])
    assert '未声明' in panel.protocol_status.text()
    wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is None and '未声明' in panel.protocol_status.text() and opened==[]


def test_missing_and_changed_elf_disable_symbols_then_explicit_relocation_recovers(arm_elf,tmp_path):
    path,elf=project(tmp_path/'project',arm_elf)
    moved=tmp_path/'renamed.elf';elf.rename(moved)
    missing=Firmware_ImportAuto([path]);assert missing.result!=R.Ok and missing.firmware is None
    assert Firmware_ImportAuto([path,moved]).result==R.Ok
    elf.write_bytes(b'not an ELF')
    changed=Firmware_ImportAuto([path]);assert changed.result!=R.Ok and changed.firmware is None
    assert Firmware_ImportAuto([path,moved]).result==R.Ok
    assert Firmware_ImportAuto([path,elf]).firmware is None


def test_multiple_debug_release_outputs_require_explicit_choice(arm_elf,tmp_path):
    path,release=project(tmp_path/'project',arm_elf)
    debug=path.parent/'build/Debug/fixture.elf';debug.parent.mkdir();shutil.copyfile(arm_elf,debug)
    assert ProjectDescriptor_Bind(path,debug)[0]==ProjectBindingResult.Ready
    reply=Firmware_ImportAuto([path]);assert reply.result!=R.Ok and reply.firmware is None and 'Multiple' in reply.detail
    for elf in (release,debug):assert Firmware_ImportAuto([path,elf]).result==R.Ok


def test_failed_or_pending_build_cannot_publish_old_success(arm_elf,tmp_path):
    path,elf=project(tmp_path/'project',arm_elf)
    ProjectDescriptor_Begin(path)
    reply=Firmware_ImportAuto([path]);assert reply.result==R.Unsupported and reply.firmware is None and 'pending_build' in reply.detail
    elf.write_bytes(b'failed link output')
    assert ProjectDescriptor_Bind(path,elf)[0]==ProjectBindingResult.Unavailable
    doc=json.loads(path.read_text());assert doc['builds']=={} and doc['state']=='unavailable'
    assert Firmware_ImportAuto([path]).firmware is None


@pytest.mark.parametrize('change',['target','hash','path','extra'])
def test_untrusted_root_data_cannot_override_target_or_binding(arm_elf,tmp_path,change):
    path,elf=project(tmp_path/'project',arm_elf);doc=json.loads(path.read_text())
    item=doc['builds']['build/Release']
    if change=='target':doc['schema']['target']='STM32F103C8'
    elif change=='hash':item['descriptor']['binding']['sha256']='0'*64
    elif change=='path':item['elf']='../fixture.elf'
    else:doc['memory']=[[0x40000000,4096]]
    path.write_text(json.dumps(doc));reply=Firmware_ImportAuto([path])
    assert reply.result!=R.Ok and reply.firmware is None


def test_project_cancel_precedes_file_access(tmp_path):
    cancel=Event();cancel.set()
    assert Firmware_ImportAuto([tmp_path/'missing.ssdiag'],cancel=cancel).result==R.Cancelled


@pytest.mark.parametrize('entry',['Run','Target_Run'])
def test_scg_host_binds_actual_debug_output_and_invalidates_before_failure(arm_elf,tmp_path,monkeypatch,entry):
    from silverstar_fccg.generator.swd_diagnostics import SwdDiagnostics_Render
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.build.runner import BuildAction,BuildRunner
    from silverstar_fccg.core.workspace import WorkspacePolicy
    root=tmp_path/'make_project';root.mkdir()
    make=shutil.which('mingw32-make') or shutil.which('make');assert make
    model=ReferenceProject_Create('BuildFixture')
    text='# SilverStar authoritative build entry\nCONFIG ?= Release\nBUILD_ROOT := build/$(CONFIG)\nTARGET := fixture\nall: $(BUILD_ROOT)/$(TARGET).elf\n'
    files=SwdDiagnostics_Render(model,None,text)
    for name,data in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    (root/'SilverStar.ssproject').write_text('{}')
    elf=root/'build/Debug/fixture.elf';elf.parent.mkdir(parents=True);shutil.copyfile(arm_elf,elf)
    runner=BuildRunner(WorkspacePolicy(root))
    command=(make,'CONFIG=Debug','all')
    monkeypatch.setattr(runner,'Command_Get',lambda *_:command)
    def run():
        return runner.Run(model,root,BuildAction.BUILD) if entry=='Run' else runner.Target_Run(model,root)
    first=run()
    assert first.succeeded and first.diagnostic_status=='bound',first.output+first.diagnostic_detail
    reply=Firmware_ImportAuto([root/'Flight.ssdiag']);assert reply.result==R.Ok,first.output+reply.detail
    doc=json.loads((root/'Flight.ssdiag').read_text())
    assert set(doc['builds'])=={'build/Debug'}
    assert doc['builds']['build/Debug']['elf']=='build/Debug/fixture.elf'
    # A direct Make build reports an artifact, but cannot publish host metadata.
    ProjectDescriptor_Begin(root/'Flight.ssdiag')
    direct=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=40)
    assert direct.returncode==0 and 'FCCG_BUILD_ARTIFACT|ELF|build/Debug/fixture.elf' in direct.stdout
    assert Firmware_ImportAuto([root/'Flight.ssdiag']).result!=R.Ok
    assert run().diagnostic_status=='bound'
    # Failed compile prerequisite: host begin invalidates the earlier success.
    elf.unlink()
    second=run()
    assert not second.succeeded
    pending=Firmware_ImportAuto([root/'Flight.ssdiag'])
    assert pending.result!=R.Ok and pending.firmware is None
    (tmp_path/'make_runs.json').write_text(json.dumps(dict(command=command,first_exit=first.return_code,first_output=first.output,failed_exit=second.return_code,failed_output=second.output)))


@pytest.mark.parametrize('case',['missing','ambiguous','outside','cancelled'])
def test_host_build_receipt_cannot_publish_stale_or_unsafe_elf(arm_elf,tmp_path,monkeypatch,case):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.build.runner import BuildAction,BuildRunner
    from silverstar_fccg.core.workspace import WorkspacePolicy
    path,elf=project(tmp_path/'project',arm_elf)
    root=path.parent
    (root/'Makefile').write_text('# SilverStar authoritative build entry\nall:\n')
    (root/'SilverStar.ssproject').write_text('{}')
    lines={
        'missing':[],
        'ambiguous':['FCCG_BUILD_ARTIFACT|ELF|build/Release/fixture.elf\n','FCCG_BUILD_ARTIFACT|ELF|build/Other/fixture.elf\n'],
        'outside':['FCCG_BUILD_ARTIFACT|ELF|../outside.elf\n'],
        'cancelled':['FCCG_BUILD_ARTIFACT|ELF|build/Release/fixture.elf\n'],
    }[case]
    token=SimpleNamespace(cancelled=False)
    def process(command,*args,**kwargs):
        if '-n' not in command and case=='cancelled':token.cancelled=True
        return 0,list(lines)
    monkeypatch.setattr(BuildRunner,'_Process_Run',staticmethod(process))
    result=BuildRunner(WorkspacePolicy(root)).Run(ReferenceProject_Create('Test'),root,BuildAction.BUILD,token)
    assert result.succeeded and result.diagnostic_status!='bound'
    assert Firmware_ImportAuto([path]).result!=R.Ok


def test_analyzer_does_not_invalidate_runtime_descriptor(arm_elf,tmp_path,monkeypatch):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.build.runner import BuildAction,BuildRunner
    from silverstar_fccg.core.workspace import WorkspacePolicy
    path,_=project(tmp_path/'project',arm_elf);root=path.parent;before=path.read_bytes()
    (root/'Makefile').write_text('# SilverStar authoritative build entry\nstatic-analysis:\n')
    (root/'SilverStar.ssproject').write_text('{}')
    monkeypatch.setattr(BuildRunner,'_Process_Run',staticmethod(lambda *a,**k:(0,['FCCG_BUILD_ARTIFACT|ELF|build/analysis.elf\n'])))
    result=BuildRunner(WorkspacePolicy(root)).Run(ReferenceProject_Create('Test'),root,BuildAction.STATIC_ANALYSIS)
    assert result.succeeded and result.diagnostic_status=='not_requested' and path.read_bytes()==before


def test_gui_primary_descriptor_pending_then_relocation_without_automatic_attach(arm_elf,tmp_path,swd_panel,monkeypatch):
    window,probes,create=swd_panel;opened=[]
    manager=create(lambda **kw:opened.append(kw))
    path,elf=project(tmp_path/'project',arm_elf);ProjectDescriptor_Begin(path)
    filters=[]
    def pick(*args):filters.append(args[3]);return [str(path)],'Project / R04 diagnostics (*.ssdiag)'
    monkeypatch.setattr('ui.swd_connection.QFileDialog.getOpenFileNames',pick)
    assert manager.import_files();wait_for(lambda:manager.import_worker is None)
    page=window.maintenance_page
    assert filters[0].split(';;')[0].endswith('(*.ssdiag)')
    assert '待编译' in page.swd_import_status.text()
    assert manager.firmware is None and not page.btn_swd_variables.isEnabled()
    assert page.btn_swd_relocate.isEnabled()
    assert ProjectDescriptor_Bind(path,elf)[0]==ProjectBindingResult.Ready
    moved=tmp_path/'renamed.elf';elf.rename(moved)
    assert manager.relocate_elf(moved);wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is not None and not page.btn_swd_variables.isEnabled()
    assert manager.worker is None and opened==[]


def test_gui_root_entry_mismatch_disables_variables_and_reads_no_ram(arm_elf,tmp_path,swd_panel):
    window,probes,create=swd_panel;backends=[]
    def factory(**kwargs):
        backend=ImageMemory(kwargs['firmware']);backend.bad_flash=True;backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory);path,_=project(tmp_path/'project',arm_elf)
    assert manager.import_files([path]);wait_for(lambda:manager.import_worker is None)
    page=window.maintenance_page
    assert manager.firmware is not None and not page.btn_swd_variables.isEnabled()
    assert window.probe_group.isAncestorOf(page.btn_swd_attach)
    page.btn_swd_attach.click();wait_for(lambda:manager.status=='swd.firmware_mismatch')
    assert window.header_swd_status.text()=='异常'
    assert window.i18n.tr('swd.firmware_mismatch') in window.header_swd_status.toolTip()
    assert not page.btn_swd_variables.isEnabled() and not page.swd_watch.isEnabled()
    assert not any(0x20000000<=address<0xE0000000 for address,_ in backends[0].reads)
    page.btn_swd_detach.click();wait_for(lambda:manager.worker is None)
