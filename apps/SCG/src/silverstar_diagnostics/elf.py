"""ELF32/ARM load identity and a deliberately small, bounded DWARF reader.

No process invocation, debug-link following, code loading or expression evaluation.
The only supported location is DW_OP_addr. Members must have constant offsets and
integer/enum scalar types; arrays, bitfields and pointers are explicitly unavailable.
"""
from dataclasses import dataclass, asdict
import io
from pathlib import Path
import struct
import time
from .contract import (Bytes_Read, Contract_Get, DiagnosticError, DiagnosticResult as R,
                       Require, Schema_Create, Schema_Validate, Sha256)
from .targets import Target_Get


@dataclass(frozen=True)
class Field:
    name: str
    address: int
    size: int
    signed: bool


@dataclass(frozen=True)
class Entry:
    id: str
    fields: tuple
    unavailable: str = ''


@dataclass(frozen=True)
class Firmware:
    target: object
    sha256: str
    segments: tuple
    entries: tuple
    descriptor: dict
    dwarf: bool
    provenance: str
    watches: tuple = ()


class ElfReader:
    MAX_DIES = 250000

    def __init__(self, path, target, cancel=None):
        self.cancel = cancel
        self.deadline = time.monotonic() + 20
        self.target = target
        self.Check()
        self.data = Bytes_Read(path, 33554432)
        Require(self.data[:7] == b'\x7fELF\x01\x01\x01', 'Only little-endian ELF32 is supported', R.Unsupported)
        Require(len(self.data) >= 52, 'Truncated ELF header')
        header = struct.unpack_from('<HHIIIIIHHHHHH', self.data, 16)
        kind, machine, _, _, phoff, shoff, _, ehsize, phsize, phnum, shsize, shnum, shstr = header
        Require(kind == 2 and machine == 40, 'ELF must be a linked ARM executable', R.Unsupported)
        Require(ehsize == 52 and phsize == 32 and 1 <= phnum <= 32 and shsize == 40 and
                1 <= shnum <= 2048 and shstr < shnum, 'Invalid or oversized ELF tables')
        Require(phoff + phsize*phnum <= len(self.data) and shoff+shsize*shnum <= len(self.data), 'ELF table outside file')
        from .dependencies import ElfTools_Ensure
        ElfTools_Ensure()
        from elftools.elf.elffile import ELFFile
        self.elf = ELFFile(io.BytesIO(self.data))
        self.sections = list(self.elf.iter_sections())
        for section in self.sections:
            self.Check()
            Require(section['sh_type'] == 'SHT_NOBITS' or section['sh_offset']+section['sh_size'] <= len(self.data),
                    'Section outside ELF')
            Require(not section['sh_flags'] & 0x800 and not section.name.startswith('.zdebug'),
                    'Compressed debug sections are unsupported', R.Unsupported)
        attributes = self.elf.get_section_by_name('.ARM.attributes')
        Require(attributes is not None and attributes['sh_size'] <= 4096,
                'Bounded ARM build attributes required to check target architecture', R.Unsupported)
        arch = []
        for sub in attributes.iter_subsections('aeabi'):
            self.Check()
            for scope in sub.iter_subsubsections():
                self.Check()
                for attr in scope.iter_attributes():
                    self.Check()
                    if attr.tag == 'TAG_CPU_ARCH': arch.append(attr.value)
        expected_arch = {'Cortex-M0':12,'Cortex-M0+':12,'Cortex-M3':10,'Cortex-M4':13}[target.core]
        Require(arch == [expected_arch], 'ELF CPU architecture disagrees with selected target', R.Mismatch)
        self.symbols = self._Symbols()
        self.variables = {}
        self.dwarf = self.elf.has_dwarf_info(strict=True)
        if self.dwarf:
            count = 0
            for index, cu in enumerate(self.elf.get_dwarf_info().iter_CUs()):
                self.Check()
                Require(index < 4096 and cu['address_size'] == 4, 'Unsupported DWARF compilation units', R.Unsupported)
                for die in cu.iter_DIEs():
                    count += 1
                    self.Check()
                    Require(count <= self.MAX_DIES, 'DWARF DIE budget exceeded', R.Unsupported)
                    if die.tag == 'DW_TAG_variable' and 'DW_AT_name' in die.attributes:
                        name = die.attributes['DW_AT_name'].value.decode('utf-8', 'strict')
                        self.variables.setdefault(name, []).append(die)

    def Check(self):
        if self.cancel is not None and self.cancel.is_set():
            raise DiagnosticError(R.Cancelled, 'ELF import cancelled')
        if time.monotonic() >= self.deadline:
            raise DiagnosticError(R.Timeout, 'ELF import deadline exceeded')

    def _Symbols(self):
        tables = [s for s in self.sections if s['sh_type'] == 'SHT_SYMTAB']
        Require(len(tables) <= 1, 'Ambiguous ELF symbol tables')
        result = {}
        if not tables:
            return result
        table = tables[0]
        Require(table['sh_entsize'] == 16 and table.num_symbols() <= 200000, 'Invalid/oversized symbol table')
        filename = ''
        for symbol in table.iter_symbols():
            self.Check()
            if symbol['st_info']['type'] == 'STT_FILE': filename = symbol.name.replace('\\','/').split('/')[-1]
            if symbol['st_info']['type'] == 'STT_OBJECT' and isinstance(symbol['st_shndx'], int):
                result.setdefault((filename, symbol.name), []).append((symbol['st_value'],symbol['st_size']))
        return result

    def Segments(self):
        result = []
        total = 0
        executable = False
        for segment in self.elf.iter_segments():
            self.Check()
            if segment['p_type'] != 'PT_LOAD' or segment['p_filesz'] == 0: continue
            # p_paddr is the flash load address, including RAM .data initializers.
            # p_vaddr is its runtime address; SHT_NOBITS/.bss has no file bytes.
            address, length, offset = segment['p_paddr'], segment['p_filesz'], segment['p_offset']
            Require(length <= segment['p_memsz'] and offset + length <= len(self.data), 'Invalid PT_LOAD size')
            Require(self.target.Contains(address, length, 'flash'), 'Load segment outside trusted internal flash', R.Unsupported)
            Require(all(address+length <= a or a+len(data) <= address for a,data in result), 'Overlapping flash load segments')
            total += length
            executable |= bool(segment['p_flags'] & 1)
            Require(total <= 2097152, 'Flash verification exceeds 2 MiB budget', R.Unsupported)
            result.append((address, self.data[offset:offset+length]))
        Require(result and executable,
                'No executable flash image')
        return tuple(sorted(result))

    @staticmethod
    def _Type(die):
        for _ in range(8):
            Require('DW_AT_type' in die.attributes, 'Missing DWARF type', R.Unsupported)
            die = die.get_DIE_from_attribute('DW_AT_type')
            if die.tag not in ('DW_TAG_typedef','DW_TAG_const_type','DW_TAG_volatile_type','DW_TAG_restrict_type'):
                return die
        raise DiagnosticError(R.Unsupported, 'DWARF type chain exceeds 8')

    def _Variable(self, spec):
        filename = spec['source'].split('/')[-1]
        symbols = self.symbols.get((filename,spec['symbol']), [])
        Require(len(symbols) == 1, 'Missing or ambiguous symtab object', R.Unsupported)
        address, size = symbols[0]
        Require(self.target.Contains(address,size,'ram'), 'Object outside trusted RAM', R.Unsupported)
        candidates = []
        for die in self.variables.get(spec['symbol'], []):
            self.Check()
            name = die.cu.get_top_DIE().attributes.get('DW_AT_name')
            if name is None: continue
            source = name.value.decode('utf-8').replace('\\','/')
            if not (source == spec['source'] or source.endswith('/'+spec['source'])): continue
            location = die.attributes.get('DW_AT_location')
            if location is not None and location.form in ('DW_FORM_exprloc','DW_FORM_block1','DW_FORM_block'):
                expr = bytes(location.value)
                if len(expr) == 5 and expr[0] == 3 and int.from_bytes(expr[1:],'little') == address:
                    candidates.append(die)
        Require(len(candidates) == 1, 'Missing/optimized/ambiguous DWARF object location', R.Unsupported)
        return candidates[0], address, size

    def Entry(self, spec):
        try:
            Require(self.dwarf, 'DWARF unavailable; symtab addresses do not establish member types', R.Unsupported)
            variable, address, size = self._Variable(spec)
            fields = []
            for name in spec['fields']:
                self.Check()
                node, offset = variable, 0
                parts = name.split('.')
                Require(len(parts) <= 4, 'Member nesting exceeds four', R.Unsupported)
                for part in parts:
                    dtype = self._Type(node)
                    Require(dtype.tag == 'DW_TAG_structure_type', 'Only fixed structure members supported', R.Unsupported)
                    members = [child for child in dtype.iter_children() if child.tag == 'DW_TAG_member' and
                               child.attributes.get('DW_AT_name') and child.attributes['DW_AT_name'].value.decode('utf-8') == part]
                    Require(len(members) == 1, 'Missing or ambiguous member', R.Unsupported)
                    node = members[0]
                    location = node.attributes.get('DW_AT_data_member_location')
                    Require(location is not None and type(location.value) is int and location.value >= 0 and
                            not any(k in node.attributes for k in ('DW_AT_bit_size','DW_AT_bit_offset','DW_AT_data_bit_offset')),
                            'Dynamic member offset or bitfield unsupported', R.Unsupported)
                    offset += location.value
                dtype = self._Type(node)
                Require(dtype.tag in ('DW_TAG_base_type','DW_TAG_enumeration_type'), 'Pointer/array/non-scalar field unsupported', R.Unsupported)
                width = dtype.attributes.get('DW_AT_byte_size')
                encoding = dtype.attributes.get('DW_AT_encoding')
                Require(width is not None and width.value in (1,2,4,8), 'Unsupported scalar size', R.Unsupported)
                if encoding is None and dtype.tag == 'DW_TAG_enumeration_type':
                    enum_type = self._Type(dtype)
                    encoding = enum_type.attributes.get('DW_AT_encoding')
                Require(encoding is not None and encoding.value in (2,5,6,7,8), 'Unknown/noninteger scalar encoding', R.Unsupported)
                Require(offset+width.value <= size, 'Member exceeds symtab object size', R.Unsupported)
                fields.append(Field(name,address+offset,width.value,encoding.value in (5,6)))
            if spec['consistency'] == 'sequence_even':
                sequence = next((f for f in fields if f.name == 'sequence'), None)
                Require(sequence is not None and sequence.size == 4 and not sequence.signed and sequence.address % 4 == 0,
                        'Sequence protocol requires an aligned uint32 field', R.Unsupported)
            Require(max(f.address+f.size for f in fields)-min(f.address for f in fields) <= 1024,
                    'Diagnostic row exceeds 1024 bytes', R.Unsupported)
            return Entry(spec['id'],tuple(fields))
        except DiagnosticError as exc:
            if exc.result != R.Unsupported: raise
            return Entry(spec['id'],(),str(exc))


def Firmware_Load(elf_path, descriptor=None, *, target=None, cancel=None, include_watch=False):
    """Import through one path shared by build binder, GUI and CLI. No target I/O."""
    from .contract import Json_Read
    value = Schema_Validate(Json_Read(descriptor) if isinstance(descriptor,(str,Path)) else descriptor) if descriptor is not None else Schema_Create(target)
    profile = Target_Get(value['target'])
    if target is not None:
        Require(Target_Get(target).name == profile.name, 'Selected target disagrees with descriptor', R.Mismatch)
    try:
        reader = ElfReader(elf_path,profile,cancel)
        segments = reader.Segments()
        entries = tuple(reader.Entry(spec) for spec in Contract_Get()['entries'] if spec['id'] in value['entries'])
        binding = dict(elf=Path(elf_path).name,sha256=Sha256(reader.data),
                       segments=[dict(address=a,size=len(data),sha256=Sha256(data)) for a,data in segments],
                       fields=[asdict(entry) for entry in entries])
        # JSON normalization changes immutable tuples into arrays for exact comparison.
        import json
        binding = json.loads(json.dumps(binding))
        if value['binding'] is not None:
            expected = dict(value['binding']); expected['elf'] = binding['elf']
            Require(expected == binding, 'Descriptor does not match actual ELF/layout', R.Mismatch)
        resolved = dict(value,binding=binding)
        Schema_Validate(resolved)
        from .watch import Catalog_Build
        watches = Catalog_Build(reader) if include_watch else ()
        return Firmware(profile,binding['sha256'],segments,entries,resolved,reader.dwarf,
                        'build_bound' if value['binding'] else 'manual_elf_unbound', watches)
    except DiagnosticError: raise
    except Exception as exc:
        raise DiagnosticError(R.InvalidFile, f'ELF parsing failed: {str(exc)[:180]}') from exc
