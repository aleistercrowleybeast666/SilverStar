"""ARM compiler-produced synthetic ELF, hostile files, and RAM-only target model.

These tests execute no target firmware and never open a probe. They are not
hardware evidence. The separate SCG fresh-project build tests real firmware.
"""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import struct
import subprocess
from threading import Event
from unittest.mock import Mock

import pytest
from transport.swd_firmware import (Firmware_Import, Target_Get, Targets_List,
    DiagnosticResult, Contract_Get)
from silverstar_diagnostics.contract import Schema_Create, Json_Read, DiagnosticError
from silverstar_diagnostics.bind import Binding_Write, BindingResult
from silverstar_diagnostics.elf import Firmware_Load
from transport.swd_session import SwdSession, SwdResult as R, SwdError
from test_swd_session import PROBE, FakeMemory, tick
from test_probe_ui import panel
from test_swd_ui import swd_panel, wait_for


@pytest.fixture(scope='module')
def arm_elf(tmp_path_factory):
    root = tmp_path_factory.mktemp('arm_diagnostic_fixture')
    sources = []
    for spec in Contract_Get()['entries']:
        path = root/spec['source']; path.parent.mkdir(parents=True,exist_ok=True)
        members = '\n'.join(('unsigned long long ' if name.endswith('_us') else 'unsigned int ')+name+';' for name in spec['fields'])
        path.write_text('static volatile struct {\n'+members+'\n} '+spec['symbol']+' __attribute__((used)) = {2};\n')
        sources.append(spec['source'])
    (root/'start.c').write_text('volatile unsigned int zero_data[16];\nvoid _start(void) { for (;;) {} }\n')
    (root/'fixture.ld').write_text('ENTRY(_start)\nMEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K\nRAM (rw) : ORIGIN = 0x20000000, LENGTH = 20K }\nSECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH\n.data : { *(.data*) } > RAM AT > FLASH\n.bss : { *(.bss*) } > RAM }\n')
    compiler = shutil.which('arm-none-eabi-gcc')
    assert compiler, 'Actual ARM compiler is required for this integration test'
    command = [compiler,'-mcpu=cortex-m4','-mthumb','-g','-gdwarf-4','-O0','-nostdlib',
               '-Wl,--build-id=none','-Tfixture.ld',*sources,'start.c','-o','fixture.elf']
    result = subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=30)
    (root/'compile.json').write_text(json.dumps(dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr)))
    assert result.returncode == 0, result.stderr
    return root/'fixture.elf'


def load(elf):
    return Firmware_Load(elf,target='STM32F407VET6')


def test_real_symtab_dwarf_fields_and_binding(arm_elf,tmp_path):
    firmware = load(arm_elf)
    assert firmware.dwarf and all(e.fields and not e.unavailable for e in firmware.entries)
    assert firmware.entries[0].fields[0].size == 8
    schema = tmp_path/'schema.ssdiag'
    schema.write_text(json.dumps(Schema_Create('STM32F407VET6')))
    result, _, path = Binding_Write(schema,arm_elf)
    assert result == BindingResult.Bound
    imported = Firmware_Import([path])
    assert imported.result == DiagnosticResult.Ok and imported.firmware.provenance == 'build_bound'
    assert imported.firmware.sha256 == firmware.sha256


@pytest.mark.parametrize('part,core', [('STM32F103C8','Cortex-M3'),('STM32F407VET6','Cortex-M4'),('STM32C071FBP6','Cortex-M0+')])
def test_official_metadata_not_descriptor_memory(part,core):
    profile = Target_Get(part)
    assert profile.core == core and profile.source.startswith('Keil.')
    assert profile.Contains(0x20000000,4,'ram')
    assert not profile.Contains(0x40000000,4,'ram')
    assert not profile.Contains(0x1FFF0000,4,'flash')
    assert not profile.Contains(0x90000000,4,'flash')


def test_catalog_and_unknown_target():
    assert len(Targets_List()) >= 400
    for name in Targets_List():
        target = Target_Get(name)
        assert target.ram and target.flash
    with pytest.raises(DiagnosticError): Target_Get('STM32Anything')


@pytest.mark.parametrize('part,cpu', [('STM32F103C8','cortex-m3'),('STM32C071FBP6','cortex-m0plus')])
def test_actual_arm_compiler_architecture_for_other_cores(arm_elf,tmp_path,part,cpu):
    source=tmp_path/'start.c';source.write_text('void _start(void) { for (;;) {} }\n')
    elf=tmp_path/'core.elf'
    result=subprocess.run([shutil.which('arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-g','-nostdlib',
                           '-Wl,--build-id=none','-T'+str(arm_elf.parent/'fixture.ld'),str(source),'-o',str(elf)],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    imported=Firmware_Import([elf],target=part)
    assert imported.result==DiagnosticResult.Ok,imported.detail
    assert all(entry.unavailable for entry in imported.firmware.entries)


@pytest.mark.parametrize('change', ['version','extra','target','entries','hash','address','path','type'])
def test_descriptor_cannot_override_layout_or_policy(arm_elf,tmp_path,change):
    descriptor = load(arm_elf).descriptor
    if change=='version': descriptor['version']=2
    elif change=='extra': descriptor['memory']=[[0x40000000,0x50000000]]
    elif change=='target': descriptor['target']='STM32H99999'
    elif change=='entries': descriptor['entries']=['arbitrary.watch']
    elif change=='hash': descriptor['binding']['sha256']='0'*64
    elif change=='address': descriptor['binding']['fields'][0]['fields'][0]['address']=0x40000000
    elif change=='path': descriptor['binding']['elf']='../fixture.elf'
    elif change=='type': descriptor['version']=True
    path=tmp_path/'bad.ssdiag'; path.write_text(json.dumps(descriptor))
    assert Firmware_Import([path,arm_elf]).result != DiagnosticResult.Ok


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'['*13+b']'*13, b'\xff', b'{', b'x'*65537],
                         ids=['duplicate','depth','encoding','truncated','size'])
def test_json_damage_limits(tmp_path,raw):
    path=tmp_path/'bad.ssdiag';path.write_bytes(raw)
    assert Firmware_Import([path]).result != DiagnosticResult.Ok


@pytest.mark.parametrize('damage', ['truncated','machine','big_endian','section_count','flash_address','compressed'])
def test_elf_damage_and_memory_refusal(arm_elf,tmp_path,damage):
    data=bytearray(arm_elf.read_bytes())
    if damage=='truncated': data=data[:51]
    elif damage=='machine': struct.pack_into('<H',data,18,62)
    elif damage=='big_endian': data[5]=2
    elif damage=='section_count': struct.pack_into('<H',data,48,0xFFFF)
    elif damage=='flash_address':
        phoff=struct.unpack_from('<I',data,28)[0]; struct.pack_into('<I',data,phoff+12,0x40000000)
    elif damage=='compressed':
        shoff=struct.unpack_from('<I',data,32)[0]; struct.pack_into('<I',data,shoff+40+8,0x800)
    path=tmp_path/'bad.elf';path.write_bytes(data)
    assert Firmware_Import([path],target='STM32F407VET6').result != DiagnosticResult.Ok


def test_no_dwarf_keeps_identity_but_never_guesses_types(arm_elf,tmp_path):
    path=tmp_path/'nodebug.elf'
    result=subprocess.run([shutil.which('arm-none-eabi-objcopy'),'--strip-debug',str(arm_elf),str(path)],capture_output=True)
    assert result.returncode==0
    firmware=load(path)
    assert not firmware.dwarf and all(not entry.fields and 'DWARF unavailable' in entry.unavailable for entry in firmware.entries)


def test_cancel_import_and_wrong_selected_target(arm_elf):
    cancel=Event();cancel.set()
    assert Firmware_Import([arm_elf],target='STM32F407VET6',cancel=cancel).result==DiagnosticResult.Cancelled
    firmware=load(arm_elf)
    with pytest.raises(DiagnosticError): Firmware_Load(arm_elf,firmware.descriptor,target='STM32F103C8')
    assert Firmware_Import([arm_elf],target='STM32F103C8').result==DiagnosticResult.Mismatch


class ImageMemory(FakeMemory):
    def __init__(self,firmware):
        super().__init__(Event())
        self.firmware=firmware; self.memory={};self.bad_flash=False
        for address,data in firmware.segments:
            self.memory.update({address+i:v for i,v in enumerate(data)})
        for entry in firmware.entries:
            for field in entry.fields:
                self.memory.update({field.address+i:v for i,v in enumerate((2).to_bytes(field.size,'little'))})
    def configure(self,profile): self.profile=Target_Get(profile.name)
    def read(self,address,length):
        if address in self.words: return super().read(address,length)
        self.reads.append((address,length))
        if self.failure: raise self.failure
        data=bytes(self.memory.get(address+i,0) for i in range(length))
        return bytes([data[0]^1])+data[1:] if self.bad_flash and address>=0x08000000 and address<0x10000000 else data


def connected_image(arm_elf):
    firmware=load(arm_elf); backend=ImageMemory(firmware)
    session=SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    assert session.Swd_Attach(PROBE).result==R.Ok
    tick(session)
    return session,backend


def test_complete_image_before_diagnostics_and_release_invalidation(arm_elf):
    session,backend=connected_image(arm_elf)
    try:
        assert session.Swd_Diagnostics().result==R.FirmwareMismatch
        assert session.Swd_VerifyFirmware().result==R.Ok
        tick(session)
        reply=session.Swd_Diagnostics()
        assert reply.result==R.Ok and reply.snapshot.symbols=='matched' and len(reply.diagnostics)==4
        assert all(row['fields'] for row in reply.diagnostics)
        assert sum(length for address,length in backend.reads if 0x08000000<=address<0x10000000)==sum(len(data) for _,data in backend.firmware.segments)
    finally: assert session.Swd_Detach().result==R.Ok
    assert session.Swd_Diagnostics().result==R.FirmwareMismatch


def test_mismatch_does_not_read_ram_and_cannot_retry(arm_elf):
    session,backend=connected_image(arm_elf)
    try:
        backend.bad_flash=True
        assert session.Swd_VerifyFirmware().result==R.FirmwareMismatch
        assert session.Swd_Diagnostics().result==R.FirmwareMismatch
        assert session.Swd_VerifyFirmware().result==R.InvalidRequest
        assert all(a<0x20000000 or a>=0xE0000000 for a,_ in backend.reads)
    finally: session.Swd_Detach()


def test_disconnect_and_cancellation_invalidate_match(arm_elf):
    session,backend=connected_image(arm_elf)
    backend.failure=SwdError(R.TransportError,'unplugged')
    assert session.Swd_VerifyFirmware().result==R.TransportError and backend.closed==1
    session,backend=connected_image(arm_elf)
    session.cancel.set()
    assert session.Swd_VerifyFirmware().result==R.Cancelled and backend.closed==1


def test_wrong_core_refuses_before_flash(arm_elf):
    firmware=load(arm_elf);backend=ImageMemory(firmware);backend.words[0xE000ED00]=0x410CC200
    session=SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    assert session.Swd_Attach(PROBE).result==R.TargetMismatch
    assert backend.reads==[(0xE000ED00,4)] and backend.closed==1


def test_sequence_guard_discards_active_writer(arm_elf):
    session,backend=connected_image(arm_elf)
    try:
        assert session.Swd_VerifyFirmware().result==R.Ok
        field=next(e for e in backend.firmware.entries if e.id=='thread.estimator').fields[0]
        backend.memory[field.address]=3
        tick(session);reply=session.Swd_Diagnostics()
        row=next(r for r in reply.diagnostics if r['id']=='thread.estimator')
        assert not row['fields'] and row['state']=='UNKNOWN'
    finally: session.Swd_Detach()


def test_cli_offline_inspect_never_enumerates(arm_elf,capsys):
    from swd_cli import SwdCli_Run
    inventory=Mock(side_effect=AssertionError('offline import accessed probes'))
    assert SwdCli_Run(['inspect','--elf',str(arm_elf),'--target','STM32F407VET6'],_inventory=inventory)==0
    assert json.loads(capsys.readouterr().out)['firmware_status']=='unmatched'
    inventory.assert_not_called()


def test_gui_import_match_read_detach_and_reimport(arm_elf,swd_panel,tmp_path):
    window,probes,create=swd_panel
    def factory(**kwargs):
        backend=ImageMemory(kwargs['firmware'])
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory)
    page=window.maintenance_page
    descriptor=tmp_path/'fixture.ssdiag'
    descriptor.write_text(json.dumps(load(arm_elf).descriptor),encoding='utf-8')
    assert manager.import_files([descriptor,arm_elf])
    assert not manager.import_files([arm_elf]) and not manager.attach()
    wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is not None
    assert manager.attach()
    wait_for(lambda:bool(manager.rows))
    assert manager.snapshot.symbols=='matched' and page.swd_diagnostics.topLevelItemCount()==4
    assert page.btn_swd_variables.isEnabled()
    assert manager.import_files([arm_elf])  # Validated exact-hash provenance permits reimport.
    assert manager.snapshot is None and not page.btn_swd_variables.isEnabled()
    wait_for(lambda:manager.import_worker is None and bool(manager.rows))
    assert manager.snapshot.symbols=='matched'
    manager.detach();wait_for(lambda:manager.worker is None)
    assert not manager.rows and not page.swd_diagnostics.isVisible()
    assert manager.import_files([arm_elf.with_suffix('.missing')])
    wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is None  # Failed replacement cannot keep a previous matching ELF.


def test_gui_cancel_import_and_close_wait_for_worker(arm_elf,swd_panel,monkeypatch):
    from transport.swd_firmware import FirmwareReply
    entered=Event()
    def slow(paths,*,target_cache,cancel):
        entered.set();cancel.wait(2)
        return FirmwareReply(DiagnosticResult.Cancelled,'cancelled')
    monkeypatch.setattr('ui.swd_connection.Firmware_ImportAuto',slow)
    window,probes,create=swd_panel
    manager=create(Mock())
    assert manager.import_files([arm_elf])
    wait_for(entered.is_set)
    assert not manager.request_close()
    wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is None and not manager.rows


def test_flash_verification_uses_data_lma_excludes_bss_and_covers_every_byte(arm_elf):
    from elftools.elf.elffile import ELFFile
    with arm_elf.open('rb') as stream:
        elf = ELFFile(stream)
        data, bss = elf.get_section_by_name('.data'), elf.get_section_by_name('.bss')
        assert data['sh_addr'] >= 0x20000000 and data['sh_size'] > 0
        assert bss['sh_type'] == 'SHT_NOBITS' and bss['sh_size'] == 64
        loads = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and s['p_filesz']]
        ram_load = next(s for s in loads if s['p_vaddr'] == data['sh_addr'])
        assert 0x08000000 <= ram_load['p_paddr'] < 0x10000000
        assert ram_load['p_memsz'] > ram_load['p_filesz']  # bss contributes no comparison bytes
        expected = {s['p_paddr']+i for s in loads for i in range(s['p_filesz'])}
    session, backend = connected_image(arm_elf)
    try:
        reply = session.Swd_VerifyFirmware()
        assert reply.result == R.Ok and 'flash LMA ranges' in reply.detail
        reads = [(a,n) for a,n in backend.reads if a < 0xE0000000]
        actual = [a+i for a,n in reads for i in range(n)]
        assert set(actual) == expected and len(actual) == len(expected)
        assert not any(a >= 0x20000000 for a in actual)
    finally: session.Swd_Detach()


def test_empty_image_or_empty_executable_segment_cannot_match(arm_elf,tmp_path):
    original = arm_elf.read_bytes()
    phoff = struct.unpack_from('<I', original, 28)[0]
    count = struct.unpack_from('<H', original, 44)[0]
    for executable_only in (False, True):
        data = bytearray(original)
        for index in range(count):
            offset = phoff+index*32
            kind, flags = struct.unpack_from('<I',data,offset)[0], struct.unpack_from('<I',data,offset+24)[0]
            if kind == 1 and (not executable_only or flags & 1):
                struct.pack_into('<I',data,offset+16,0)
        path = tmp_path/('empty_exec.elf' if executable_only else 'empty.elf')
        path.write_bytes(data)
        assert Firmware_Import([path],target='STM32F407VET6').result != DiagnosticResult.Ok


def test_mismatch_reports_exact_byte_in_data_flash_lma(arm_elf):
    session, backend = connected_image(arm_elf)
    address, data = backend.firmware.segments[-1]
    mismatch = address+len(data)-1
    expected = backend.memory[mismatch]
    backend.memory[mismatch] ^= 1
    try:
        reply = session.Swd_VerifyFirmware()
        assert reply.result == R.FirmwareMismatch and reply.address == mismatch
        assert f'ELF {expected:02X}, target {expected^1:02X}' in reply.detail
        assert not any(0x20000000 <= a < 0xE0000000 for a,n in backend.reads)
    finally: session.Swd_Detach()


def test_old_import_and_swd_signals_cannot_modify_new_job(swd_panel):
    from transport.swd_firmware import FirmwareReply
    from transport.swd_session import SwdReply
    from ui.swd_connection import FirmwareWorker, SwdWorker
    window,probes,create = swd_panel
    manager = create(Mock())
    old_import = FirmwareWorker([],{},manager)
    current_import = FirmwareWorker([],{},manager)
    old_import.update.connect(manager._imported)
    old_import.finished.connect(manager._import_finished)
    manager.import_worker = current_import
    old_import.update.emit(FirmwareReply(DiagnosticResult.InvalidFile,'stale'))
    old_import.finished.emit()
    assert manager.import_worker is current_import and manager.import_detail == ''
    manager.import_worker = None
    old_swd = SwdWorker(PROBE,Mock(),manager)
    current_swd = SwdWorker(PROBE,Mock(),manager)
    old_swd.update.connect(manager._updated)
    old_swd.finished.connect(manager._finished)
    manager.worker = current_swd
    old_swd.update.emit(SwdReply(R.TransportError,'stale'))
    old_swd.finished.emit()
    assert manager.worker is current_swd and manager.detail == ''
    manager.worker = None


def test_reset_invalidates_matched_firmware_before_diagnostic_ram(arm_elf):
    session,backend = connected_image(arm_elf)
    try:
        assert session.Swd_VerifyFirmware().result == R.Ok
        backend.words[0xE000EDF0] = 1 << 25
        backend.reads.clear(); tick(session)
        assert session.Swd_Diagnostics().result == R.FirmwareMismatch
        assert not any(0x20000000 <= a < 0xE0000000 for a,n in backend.reads)
    finally: session.Swd_Detach()
