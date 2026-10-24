"""Explicit HEX programming identity, derived and bounded by the same ELF.

This is not the ELF process loader. v1 remains strict. No target I/O, process
invocation or user-provided address/type expressions occur here.
"""
import re
from pathlib import Path

from .contract import Bytes_Read, Require, Sha256
from .contract import DiagnosticResult as R

IMAGE_MODE='gnu-ihex-elf-erased-alignment/1'


def _Disjoint(regions,detail):
    end=-1
    for start,stop in sorted(regions):
        Require(start<stop and start>=end,detail)
        end=stop


def _Loads(reader):
    loads=[];total=0
    for index,segment in enumerate(reader.elf.iter_segments()):
        reader.Check()
        Require(segment['p_type'] not in ('PT_DYNAMIC','PT_INTERP','PT_TLS'),'Dynamic/TLS loading unsupported',R.Unsupported)
        if segment['p_type']!='PT_LOAD':continue
        vma,lma,size,mem,offset,flags,align=(segment[k] for k in ('p_vaddr','p_paddr','p_filesz','p_memsz','p_offset','p_flags','p_align'))
        Require(0<=size<=mem and mem>0 and offset+size<=len(reader.data) and flags&~7==0,'Invalid load size/flags')
        Require(vma+mem<=0x100000000 and 0<=lma<=0xFFFFFFFF,'Load address overflow')
        Require(align in (0,1) or align&(align-1)==0 and vma%align==offset%align,'Invalid load alignment')
        ram=reader.target.Contains(vma,mem,'ram')
        Require(ram or reader.target.Contains(vma,mem,'flash') and lma==vma,'Load VMA outside supported direct Flash/RAM',R.Unsupported)
        if size:Require(reader.target.Contains(lma,size,'flash'),'File load outside trusted Flash',R.Unsupported)
        Require(mem==size or ram,'ELF zero-fill in Flash is unsupported',R.Unsupported)
        Require(size or not flags&1,'Zero-only executable segment unsupported',R.Unsupported)
        total+=size;Require(total<=2097152,'Image exceeds 2 MiB',R.Unsupported)
        loads.append({'index':index,'vma':vma,'lma':lma,'size':size,'mem':mem,'offset':offset,'flags':flags,'align':align})
    Require(loads and total>0,'No nonempty Flash file image')
    _Disjoint([(s['vma'],s['vma']+s['mem']) for s in loads],'Overlapping load memory extents')
    _Disjoint([(s['lma'],s['lma']+s['size']) for s in loads if s['size']],'Overlapping Flash file loads')
    _Disjoint([(s['offset'],s['offset']+s['size']) for s in loads if s['size']],'Overlapping file load extents')
    return loads


def _Sections(reader,loads):
    sections=[]
    for index,section in enumerate(reader.sections):
        reader.Check()
        if not section['sh_flags']&2 or not section['sh_size']:continue
        Require(len(sections)<64,'Allocated section budget exceeded',R.Unsupported)
        vma,size,offset,align=(section[k] for k in ('sh_addr','sh_size','sh_offset','sh_addralign'))
        align=max(1,align)
        Require(align<=4096 and align&(align-1)==0 and vma%align==0,'Invalid/unsupported section alignment',R.Unsupported)
        Require(not section['sh_flags']&0x400,'TLS section unsupported',R.Unsupported)
        owners=[s for s in loads if s['vma']<=vma<vma+size<=s['vma']+s['mem']]
        Require(len(owners)==1,'Allocated section has no unique load owner')
        owner=owners[0];nobits=section['sh_type']=='SHT_NOBITS'
        if nobits:
            Require(reader.target.Contains(vma,size,'ram') and vma>=owner['vma']+owner['size'],
                    'NOBITS must be in the RAM zero-fill tail',R.Unsupported)
            lma=None
        else:
            Require(vma+size<=owner['vma']+owner['size'] and offset-owner['offset']==vma-owner['vma'],
                    'Section file/VMA mapping disagrees with PT_LOAD')
            lma=owner['lma']+vma-owner['vma']
        sections.append({'index':index,'name':section.name,'vma':vma,'lma':lma,'size':size,'offset':offset,
            'align':align,'flags':section['sh_flags'],'type':section['sh_type'],'load':owner['index']})
    _Disjoint([(s['vma'],s['vma']+s['size']) for s in sections],'Overlapping allocated sections')
    _Disjoint([(s['lma'],s['lma']+s['size']) for s in sections if s['lma'] is not None],'Overlapping allocated Flash contents')
    executable=[s for s in sections if s['lma'] is not None and s['flags']&4]
    entry=reader.elf.header['e_entry']
    Require(entry&1 and any(s['vma']<=entry&~1<s['vma']+s['size'] for s in executable),
            'Thumb entry is not in allocated executable file contents',R.Unsupported)
    for load in loads:
        if load['size']:
            Require(any(s['load']==load['index'] and s['lma'] is not None for s in sections),
                    'File-backed segment cannot be dropped for lack of sections',R.Unsupported)
        if load['flags']&1:
            Require(any(s['load']==load['index'] for s in executable),'Executable load lacks executable file contents')
    return sections


def _Hex(reader,path):
    raw=Bytes_Read(path,8388608);records=[];base=0;eof=False;entry=False;total=0
    try:lines=raw.decode('ascii').splitlines()
    except UnicodeError:Require(False,'HEX must be ASCII')
    Require(0<len(lines)<=262144,'HEX record count exceeds bound',R.Unsupported)
    for line in lines:
        reader.Check()
        Require(not eof and line.startswith(':') and len(line)<=521 and len(line)%2==1
                and re.fullmatch('[0-9a-fA-F]+',line[1:]),'Invalid HEX line')
        try:data=bytes.fromhex(line[1:])
        except ValueError:Require(False,'Invalid HEX encoding')
        Require(len(data)>=5 and len(data)==data[0]+5 and sum(data)&255==0,'Invalid HEX length/checksum')
        size=data[0];offset=int.from_bytes(data[1:3],'big');kind=data[3];payload=data[4:-1]
        if kind==0:
            Require(size>0 and offset+size<=65536 and reader.target.Contains(base+offset,size,'flash'),
                    'HEX data outside trusted Flash/window',R.Unsupported)
            total+=size;Require(total<=2097152,'HEX byte budget exceeded',R.Unsupported)
            records.append((base+offset,payload))
        elif kind==1:
            Require(size==0 and offset==0,'Invalid HEX EOF');eof=True
        elif kind in (2,4):
            Require(size==2 and offset==0,'Invalid HEX address record')
            base=int.from_bytes(payload,'big')<<(4 if kind==2 else 16)
        elif kind==5:
            Require(not entry and size==4 and offset==0 and int.from_bytes(payload,'big')==reader.elf.header['e_entry'],
                    'Conflicting HEX entry point');entry=True
        else:Require(False,'Unsupported HEX record type',R.Unsupported)
    Require(eof and records,'Incomplete HEX image')
    _Disjoint([(a,a+len(data)) for a,data in records],'Overlapping/duplicate HEX data records')
    return raw,tuple(sorted(records))


def _Populate(reader,loads,records):
    expected={s['index']:bytearray(reader.data[s['offset']:s['offset']+s['size']]) for s in loads if s['size']}
    provided={index:bytearray(len(data)) for index,data in expected.items()}
    for address,data in records:
        reader.Check();position=0
        while position<len(data):
            reader.Check();cursor=address+position
            owners=[s for s in loads if s['size'] and s['lma']<=cursor<s['lma']+s['size']]
            Require(len(owners)==1,'HEX has bytes not owned by a file-backed ELF load')
            owner=owners[0];count=min(len(data)-position,owner['lma']+owner['size']-cursor)
            offset=cursor-owner['lma'];index=owner['index']
            Require(expected[index][offset:offset+count]==data[position:position+count],
                    'HEX bytes disagree with the same ELF',R.Mismatch)
            provided[index][offset:offset+count]=b'\x01'*count;position+=count
    return expected,provided


def _Gap(reader,load,start,stop,previous,next_section,expected,provided):
    offset=start-load['lma'];size=stop-start;index=load['index']
    present=provided[index][offset:offset+size]
    if all(present):return None
    Require(not any(present) and previous is not None and next_section is not None,
            'Omitted file bytes are not a complete interior alignment gap',R.Unsupported)
    align=next_section['align']
    Require(size<align and stop==(start+align-1)//align*align,'Unproven omitted alignment span',R.Unsupported)
    original=bytes(expected[index][offset:offset+size])
    Require(all(value in (0,255) for value in original),'Omitted file contents are not supported padding',R.Unsupported)
    table=reader.elf.get_section_by_name('.symtab')
    if table is not None:
        for symbol in table.iter_symbols():
            reader.Check();address=symbol['st_value'];extent=symbol['st_size'];kind=symbol['st_info']['type']
            if not isinstance(symbol['st_shndx'],int):continue
            if kind=='STT_FUNC':address &= ~1
            # Symbols carry runtime VMA; initialized RAM contents are compared
            # at their Flash LMA. A described object in a RAM gap is not padding.
            if load['vma']<=address<load['vma']+load['size']:
                address=load['lma']+address-load['vma']
            if kind in ('STT_FUNC','STT_OBJECT'):
                Require(not (address<stop and address+max(extent,1)>start),'Omitted gap contains a function/object symbol',R.Unsupported)
            elif start<=address<stop:
                Require(extent==0 and address==start and symbol['st_shndx']==previous['index'],
                        'Omitted gap has an interior symbol',R.Unsupported)
    expected[index][offset:offset+size]=b'\xFF'*size
    return {'address':start,'size':size,'elf_bytes_sha256':Sha256(original),'expected_byte':255}


def Image_Build(reader,elf_path,description):
    Require(description['mode']==IMAGE_MODE,'Unsupported image mode',R.Unsupported)
    folder=Path(elf_path).absolute().parent
    path=folder/description['file']
    Require(not path.is_symlink() and path.is_file() and path.resolve().parent==folder.resolve(),
            'HEX must be a regular sibling of the selected ELF')
    loads=_Loads(reader);sections=_Sections(reader,loads)
    raw,records=_Hex(reader,path);expected,provided=_Populate(reader,loads,records)
    gaps=[]
    for load in loads:
        if not load['size']:continue
        allocated=sorted((s for s in sections if s['load']==load['index'] and s['lma'] is not None),key=lambda s:s['lma'])
        cursor=load['lma'];previous=None
        for section in allocated:
            reader.Check()
            if cursor<section['lma']:
                gap=_Gap(reader,load,cursor,section['lma'],previous,section,expected,provided)
                if gap:gaps.append(gap)
            offset=section['lma']-load['lma']
            Require(all(provided[load['index']][offset:offset+section['size']]),'HEX omits allocated file contents')
            cursor=section['lma']+section['size'];previous=section
        if cursor<load['lma']+load['size']:
            _Gap(reader,load,cursor,load['lma']+load['size'],previous,None,expected,provided)
    zero_ram=[{'address':s['vma']+s['size'],'size':s['mem']-s['size'],'load':s['index']} for s in loads if s['mem']>s['size']]
    manifest={'mode':IMAGE_MODE,'file':description['file'],'sha256':Sha256(raw),'loads':loads,'sections':sections,
              'erased_gaps':gaps,'zero_ram':zero_ram,'programmed_bytes':sum(len(data) for _,data in records)}
    ram=tuple((s['vma'],s['vma']+s['size'],s['index']) for s in sections if reader.target.Contains(s['vma'],s['size'],'ram'))
    return tuple(sorted((s['lma'],bytes(expected[s['index']])) for s in loads if s['size'])),manifest,ram
