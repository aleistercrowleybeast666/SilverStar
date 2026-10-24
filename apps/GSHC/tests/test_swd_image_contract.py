"""Image provenance and same-ELF bindings; synthetic targets, never hardware."""
import json
from pathlib import Path
import shutil
import subprocess
import struct

import pytest

from silverstar_diagnostics.contract import Schema_Create,DiagnosticError,Contract_Get
from silverstar_diagnostics.elf import Firmware_Load
from silverstar_diagnostics.elf import ElfReader
from silverstar_diagnostics.targets import Target_Get
from silverstar_diagnostics.bind import Binding_Write,BindingResult
from transport.swd_session import SwdSession,SwdResult as R
from test_swd_firmware import ImageMemory
from test_swd_session import PROBE

TARGET='STM32F407VETx'


@pytest.fixture
def image(tmp_path):
    sources=[]
    for spec in Contract_Get()['entries']:
        path=tmp_path/spec['source'];path.parent.mkdir(parents=True,exist_ok=True)
        fields='\n'.join(('unsigned long long ' if name.endswith('_us') else 'unsigned int ')+name+';' for name in spec['fields'])
        path.write_text('static volatile struct {\n'+fields+'\n} '+spec['symbol']+' __attribute__((used)) = {'+','.join('2' for _ in spec['fields'])+'};\n')
        sources.append(spec['source'])
    (tmp_path/'start.c').write_text('const unsigned int vector_stub[2] __attribute__((section(".isr_vector"),used))={0x20001000,0x08000011};\nconst unsigned long long marker __attribute__((aligned(8),used))=0x12345678;\nvolatile unsigned int zero_data[16];\nvolatile unsigned int zero_ccm[8] __attribute__((section(".ccm_bss")));\nvoid _start(void) __attribute__((aligned(16)));\nvoid _start(void) { for (;;) {} }\n')
    (tmp_path/'fixture.ld').write_text('ENTRY(_start)\nMEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K\nRAM (rw) : ORIGIN = 0x20000000, LENGTH = 20K\nCCM (rw) : ORIGIN = 0x10000000, LENGTH = 64K }\nSECTIONS { .isr_vector : { *(.isr_vector) } > FLASH\n.text : { *(.text*) } > FLASH\n.rodata : { *(.rodata*) } > FLASH\n.data : { *(.data*) } > RAM AT > FLASH\n.bss (NOLOAD) : { *(.bss*) } > RAM\n.ccm_bss (NOLOAD) : { *(.ccm_bss) } > CCM }\n')
    elf=tmp_path/'fixture.elf'
    command=[shutil.which('arm-none-eabi-gcc'),'-mcpu=cortex-m4','-mthumb','-g','-gdwarf-4','-O0','-Wall','-Wextra','-Werror','-nostdlib',
             '-Wl,--build-id=none','-Tfixture.ld',*sources,'start.c','-o',elf.name]
    result=subprocess.run(command,cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    command2=[shutil.which('arm-none-eabi-objcopy'),'-O','ihex',str(elf),str(elf.with_suffix('.hex'))]
    converted=subprocess.run(command2,capture_output=True,text=True,timeout=30)
    assert converted.returncode==0,converted.stderr
    (tmp_path/'tool_commands.json').write_text(json.dumps([{'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},
        {'command':command2,'exit':converted.returncode,'stdout':converted.stdout,'stderr':converted.stderr}],indent=2))
    return elf


def load_v2(elf,*,bound=True):
    value=Schema_Create(TARGET,image_file=elf.with_suffix('.hex').name)
    firmware=Firmware_Load(elf,value,include_watch=True)
    return Firmware_Load(elf,firmware.descriptor,include_watch=True) if bound else firmware


def test_bound_descriptor_v2_still_rejects_elf_tamper(image):
    firmware=load_v2(image)
    raw=bytearray(image.read_bytes());raw[-1]^=1;image.write_bytes(raw)
    with pytest.raises(DiagnosticError):Firmware_Load(image,firmware.descriptor)


def test_unbound_v2_cannot_open_hardware(image):
    firmware=load_v2(image,bound=False)
    created=[]
    session=SwdSession(firmware=firmware,_backend_factory=lambda _:created.append(True))
    reply=session.Swd_Attach(PROBE)
    assert reply.result==R.InvalidRequest and not created


@pytest.mark.parametrize('kind',['code','data','erased_gap'])
def test_every_programmed_byte_and_erased_gap_still_blocks_ram_on_mismatch(image,kind):
    firmware=load_v2(image);backend=ImageMemory(firmware)
    if kind=='erased_gap':address=firmware.image_identity['erased_gaps'][0]['address']
    elif kind=='data':address=firmware.segments[-1][0]
    else:address=firmware.segments[0][0]
    backend.memory[address]^=1
    session=SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    try:
        assert session.Swd_Attach(PROBE).result==R.Ok
        session._last_sample-=1
        assert session.Swd_VerifyFirmware().result==R.FirmwareMismatch
        assert not any(0x10000000<=a<0x10010000 or 0x20000000<=a<0x20020000 for a,_ in backend.reads)
    finally:session.Swd_Detach()


def test_ram_zero_fill_is_metadata_and_not_flash_or_live_ram_zero_claim(image):
    firmware=load_v2(image)
    assert firmware.image_identity['zero_ram']
    assert all(firmware.target.Contains(r['address'],r['size'],'ram') for r in firmware.image_identity['zero_ram'])
    assert sum(len(data) for _,data in firmware.segments)==sum(len(data) for _,data in Firmware_Load(image,target=TARGET).segments)
    backend=ImageMemory(firmware);session=SwdSession(firmware=firmware,_backend_factory=lambda _:backend)
    try:
        assert session.Swd_Attach(PROBE).result==R.Ok
        session._last_sample-=1;assert session.Swd_VerifyFirmware().result==R.Ok
        session._last_sample-=2;assert session.Swd_Diagnostics().result==R.Ok
    finally:session.Swd_Detach()


def _reader(elf):
    return ElfReader(elf,Target_Get(TARGET))


def _record(kind,address=0,data=b''):
    row=bytes([len(data)])+address.to_bytes(2,'big')+bytes([kind])+data
    return ':'+(row+bytes([-sum(row)&255])).hex().upper()


def _hex_write(elf, records):
    elf.with_suffix('.hex').write_text('\n'.join(records)+'\n',encoding='ascii')


def _data_records(elf):
    firmware=Firmware_Load(elf,target=TARGET)
    records=[]
    for address,data in firmware.segments:
        for offset in range(0,len(data),16):
            cursor=address+offset
            records.extend((_record(4,data=(cursor>>16).to_bytes(2,'big')),
                            _record(0,cursor&65535,data[offset:offset+16])))
    return records+[_record(1)]


@pytest.mark.parametrize('damage',['checksum','duplicate','overlap','unmapped','missing_allocated',
    'code_differs','entry','record_type','after_eof','embedded_space','partial_gap','nonpadding_gap'])
def test_hex_negative_contracts(image,damage):
    rows=image.with_suffix('.hex').read_text().splitlines()
    reader=_reader(image)
    if damage=='checksum':rows[1]=rows[1][:-2]+'00'
    elif damage=='duplicate':rows.insert(-1,rows[1])
    elif damage=='overlap':rows.insert(-1,_record(4,data=b'\x08\x00'));rows.insert(-1,_record(0,1,b'\x00'))
    elif damage=='unmapped':rows.insert(-1,_record(4,data=b'\x08\x07'));rows.insert(-1,_record(0,0,b'\x00'))
    elif damage=='missing_allocated':del rows[1]
    elif damage=='code_differs':
        raw=bytes.fromhex(rows[1][1:]);payload=bytearray(raw[4:-1]);payload[0]^=1
        rows[1]=_record(0,int.from_bytes(raw[1:3],'big'),bytes(payload))
    elif damage=='entry':rows.insert(-1,_record(5,data=(reader.elf.header['e_entry']+2).to_bytes(4,'big')))
    elif damage=='record_type':rows.insert(-1,_record(3,data=b'\x00'*4))
    elif damage=='after_eof':rows.append(_record(1))
    elif damage=='embedded_space':rows[1]=rows[1][:3]+'  '+rows[1][3:]
    else:
        firmware=load_v2(image);gap=firmware.image_identity['erased_gaps'][0]
        if damage=='partial_gap':rows.insert(2,_record(0,gap['address']&65535,b'\x00'))
        else:
            load=next(s for s in reader.elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_paddr']<=gap['address']<s['p_paddr']+s['p_filesz'])
            raw=bytearray(image.read_bytes());raw[load['p_offset']+gap['address']-load['p_paddr']]=0x42;image.write_bytes(raw)
    _hex_write(image,rows)
    with pytest.raises(DiagnosticError):load_v2(image)


def test_explicit_hex_gap_contents_remain_exact_elf_bytes(image):
    _hex_write(image,_data_records(image))
    firmware=load_v2(image)
    assert firmware.image_identity['erased_gaps']==[]
    assert firmware.segments==Firmware_Load(image,target=TARGET).segments


@pytest.mark.parametrize('damage',['filesz_gt_mem','file_offset','flash_vma_alias','vma_overlap',
    'lma_overlap','file_overlap','flash_zero_fill','file_load_without_sections','section_lma_mapping','entry_outside'])
def test_load_and_section_negative_contracts(image,damage):
    raw=bytearray(image.read_bytes());reader=_reader(image)
    phoff=struct.unpack_from('<I',raw,28)[0];shoff=struct.unpack_from('<I',raw,32)[0]
    loads=[(i,s) for i,s in enumerate(reader.elf.iter_segments()) if s['p_type']=='PT_LOAD']
    first=loads[0][0];second=loads[1][0]
    def ph(index,field,value):struct.pack_into('<I',raw,phoff+index*32+field*4,value)
    if damage=='filesz_gt_mem':ph(first,5,1)
    elif damage=='file_offset':ph(first,1,len(raw))
    elif damage=='flash_vma_alias':ph(first,2,0x08001000)
    elif damage=='vma_overlap':ph(second,2,loads[0][1]['p_vaddr']);ph(second,7,1)
    elif damage=='lma_overlap':ph(second,3,loads[0][1]['p_paddr'])
    elif damage=='file_overlap':ph(second,1,loads[0][1]['p_offset']);ph(second,7,1)
    elif damage=='flash_zero_fill':ph(first,5,loads[0][1]['p_memsz']+4)
    elif damage=='file_load_without_sections':
        for i,s in enumerate(reader.sections):
            if s['sh_flags']&2 and loads[0][1]['p_vaddr']<=s['sh_addr']<loads[0][1]['p_vaddr']+loads[0][1]['p_memsz']:
                struct.pack_into('<I',raw,shoff+i*40+8,s['sh_flags']&~2)
    elif damage=='section_lma_mapping':
        i=next(i for i,s in enumerate(reader.sections) if s.name=='.data')
        struct.pack_into('<I',raw,shoff+i*40+16,reader.sections[i]['sh_offset']+4)
    elif damage=='entry_outside':struct.pack_into('<I',raw,24,0x20000001)
    image.write_bytes(raw)
    with pytest.raises(DiagnosticError):load_v2(image)


def test_zero_only_ram_load_flash_paddr_is_not_programmed(image):
    reader=_reader(image);raw=bytearray(image.read_bytes());phoff=struct.unpack_from('<I',raw,28)[0]
    zeros=[(i,s) for i,s in enumerate(reader.elf.iter_segments()) if s['p_type']=='PT_LOAD' and s['p_filesz']==0]
    assert zeros
    index,segment=zeros[0]
    struct.pack_into('<I',raw,phoff+index*32+12,0x08070000);image.write_bytes(raw)
    firmware=load_v2(image)
    assert any(r['address']==segment['p_vaddr'] and r['size']==segment['p_memsz'] for r in firmware.image_identity['zero_ram'])
    assert all(not a<=0x08070000<a+len(data) for a,data in firmware.segments)


@pytest.mark.parametrize('damage',['elf_debug','hex','field_address','field_type','image_expectation','image_hash'])
def test_bound_layout_and_both_artifact_hashes_reject_tampering(image,damage):
    firmware=load_v2(image);value=firmware.descriptor
    if damage=='elf_debug':
        reader=_reader(image);section=reader.elf.get_section_by_name('.debug_info')
        raw=bytearray(image.read_bytes());raw[section['sh_offset']+section['sh_size']-1]^=1;image.write_bytes(raw)
    elif damage=='hex':
        rows=image.with_suffix('.hex').read_text().splitlines();_hex_write(image,[r.lower() for r in rows])
    elif damage=='field_address':value['binding']['fields'][0]['fields'][0]['address']+=4
    elif damage=='field_type':value['binding']['fields'][0]['fields'][0]['signed']=True
    elif damage=='image_expectation':value['binding']['image']['erased_gaps'][0]['expected_byte']=0
    elif damage=='image_hash':value['binding']['image']['sha256']='0'*64
    with pytest.raises(DiagnosticError):Firmware_Load(image,value)


def test_same_elf_symbols_must_belong_to_validated_ram_section(image):
    reader=_reader(image);raw=bytearray(image.read_bytes());table=reader.elf.get_section_by_name('.symtab')
    index=next(i for i,s in enumerate(table.iter_symbols()) if s.name=='s_health')
    flash_section=next(i for i,s in enumerate(reader.sections) if s.name=='.text')
    struct.pack_into('<H',raw,table['sh_offset']+16*index+14,flash_section);image.write_bytes(raw)
    firmware=load_v2(image)
    assert firmware.entries[0].unavailable and not firmware.entries[0].fields
    assert all(w.unavailable for w in firmware.watches if w.symbol=='s_health')
    assert any(e.fields for e in firmware.entries[1:])


def test_v2_binder_and_failed_rebinding_cannot_keep_obsolete_identity(image,tmp_path):
    schema=tmp_path/'schema.ssdiag';schema.write_text(json.dumps(Schema_Create(TARGET,image_file=image.with_suffix('.hex').name)))
    result,_,path=Binding_Write(schema,image)
    assert result==BindingResult.Bound
    assert Firmware_Load(image,path).provenance=='build_bound'
    image.with_suffix('.hex').write_text(':00000001FF\n')
    result,_,path=Binding_Write(schema,image)
    assert result==BindingResult.Unbound and json.loads(path.read_text())['binding'] is None
