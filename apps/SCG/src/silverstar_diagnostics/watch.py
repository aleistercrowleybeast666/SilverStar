"""Bounded ELF-derived RAM scalar catalog. Never evaluate DWARF expressions."""
from dataclasses import dataclass
import math
import re
import struct

from .contract import DiagnosticError, DiagnosticResult as R, Require

MAX_CATALOG = 8192
MAX_WATCH = 16


@dataclass(frozen=True)
class WatchField:
    id: str
    source: str
    symbol: str
    member: str = ''
    type_name: str = ''
    address: int = 0
    size: int = 0
    encoding: int = 0
    unavailable: str = ''


def _Text(attribute):
    if attribute is None:
        return ''
    value = attribute.value.decode('utf-8', 'strict')
    Require(len(value) <= 512 and all(ord(c) >= 32 for c in value), 'Invalid DWARF name')
    return value.replace('\\', '/')


def _Identifier(name):
    Require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,127}', name), 'Unsupported identifier', R.Unsupported)


def _Width(dtype):
    width = dtype.attributes.get('DW_AT_byte_size')
    Require(width is not None and type(width.value) is int and width.value > 0,
            'Missing/invalid DWARF size', R.Unsupported)
    return width.value


def _Location(reader, die, symbol):
    Require(die.get_parent().tag == 'DW_TAG_compile_unit', 'Local variables are unsupported', R.Unsupported)
    location = die.attributes.get('DW_AT_location')
    Require(location is not None and location.form in ('DW_FORM_exprloc', 'DW_FORM_block1', 'DW_FORM_block'),
            'Optimized, missing or dynamic location', R.Unsupported)
    expr = bytes(location.value)
    Require(len(expr) == 5 and expr[0] == 3, 'Only DW_OP_addr is supported', R.Unsupported)
    address = int.from_bytes(expr[1:], 'little')
    dtype = reader._Type(die)
    size = _Width(dtype)
    # Global linker symbols may follow a different STT_FILE. DWARF supplies CU
    # identity; require exactly one allocated symtab object at the same address.
    matches = [item for (_, name), values in reader.symbols.items() if name == symbol
               for item in values if item == (address, size)]
    Require(len(matches) == 1, 'Missing or ambiguous matching symtab object', R.Unsupported)
    Require(reader.target.Contains(address, size, 'ram'), 'Object outside trusted RAM', R.Unsupported)
    allocated = [s for s in reader.sections if s['sh_flags'] & 2 and s['sh_flags'] & 1 and
                 s['sh_addr'] <= address < address + size <= s['sh_addr'] + s['sh_size']]
    Require(len(allocated) == 1, 'Object is not in one allocated writable section', R.Unsupported)
    reader.Object_Validate(address,size,symbol)
    return dtype, address, size


def Catalog_Build(reader):
    if not reader.dwarf:
        return ()
    result = []

    def append(field):
        Require(len(result) < MAX_CATALOG, 'Watch catalog exceeds 8192 entries', R.Unsupported)
        result.append(field)

    for symbol, variables in reader.variables.items():
        for die in variables:
            reader.Check()
            # Locals are never candidates, even a function-local static address.
            if die.get_parent().tag != 'DW_TAG_compile_unit':
                continue
            source = _Text(die.cu.get_top_DIE().attributes.get('DW_AT_name'))
            base = source + '::' + symbol
            try:
                _Identifier(symbol)
                Require(source and '::' not in source, 'Missing/ambiguous compilation unit', R.Unsupported)
                dtype, address, size = _Location(reader, die, symbol)
                pending = [(dtype, '', 0, size, 0)]
                visited = 0
                while pending:
                    reader.Check()
                    dtype, member, offset, extent, depth = pending.pop()
                    visited += 1
                    Require(visited <= MAX_CATALOG, 'Object member budget exceeded', R.Unsupported)
                    identifier = base + ('.' + member if member else '')
                    try:
                        width = _Width(dtype)
                        Require(width <= extent and offset + width <= size, 'Member exceeds containing object', R.Unsupported)
                        if dtype.tag == 'DW_TAG_structure_type':
                            Require(depth < 4, 'Structure depth exceeds four', R.Unsupported)
                            children = []
                            for child in dtype.iter_children():
                                reader.Check()
                                Require(len(children) < 256, 'Structure exceeds 256 members', R.Unsupported)
                                if child.tag == 'DW_TAG_member': children.append(child)
                            Require(children, 'Empty structure', R.Unsupported)
                            for child in reversed(children):
                                name = _Text(child.attributes.get('DW_AT_name'))
                                path = member + '.' + name if member else name
                                try:
                                    _Identifier(name)
                                    loc = child.attributes.get('DW_AT_data_member_location')
                                    Require(loc is not None and type(loc.value) is int and 0 <= loc.value < width and
                                            not any(k in child.attributes for k in ('DW_AT_bit_size','DW_AT_bit_offset','DW_AT_data_bit_offset')),
                                            'Dynamic member offset or bitfield unsupported', R.Unsupported)
                                    pending.append((reader._Type(child),path,offset+loc.value,width-loc.value,depth+1))
                                except DiagnosticError as exc:
                                    if exc.result != R.Unsupported: raise
                                    append(WatchField(base+'.'+path,source,symbol,path,unavailable=str(exc)))
                            continue
                        Require(dtype.tag in ('DW_TAG_base_type','DW_TAG_enumeration_type'),
                                'Arrays, pointers, unions and non-scalar types unsupported', R.Unsupported)
                        encoding = dtype.attributes.get('DW_AT_encoding')
                        if encoding is None and dtype.tag == 'DW_TAG_enumeration_type':
                            encoding = reader._Type(dtype).attributes.get('DW_AT_encoding')
                        Require(encoding is not None and encoding.value in (2,4,5,6,7,8) and width in (1,2,4,8),
                                'Unsupported scalar encoding/size', R.Unsupported)
                        Require(encoding.value != 4 or width in (4,8), 'Unsupported floating-point size', R.Unsupported)
                        typename = _Text(dtype.attributes.get('DW_AT_name')) or ('enum' if dtype.tag == 'DW_TAG_enumeration_type' else 'scalar')
                        append(WatchField(identifier,source,symbol,member,typename,address+offset,width,encoding.value))
                    except DiagnosticError as exc:
                        if exc.result != R.Unsupported: raise
                        append(WatchField(identifier,source,symbol,member,unavailable=str(exc)))
            except DiagnosticError as exc:
                if exc.result != R.Unsupported: raise
                # A global catalog overflow must reject import, not return a
                # truncated table with a successful status.
                if len(result) >= MAX_CATALOG: raise
                append(WatchField(base,source,symbol,unavailable=str(exc)))
    counts = {}
    for item in result: counts[item.id] = counts.get(item.id, 0) + 1
    from dataclasses import replace
    unique = {item.id:replace(item,unavailable='Ambiguous source/symbol/member') if counts[item.id] > 1 else item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def Value_Decode(field, data):
    Require(len(data) == field.size, 'Short watch read')
    if field.encoding == 4:
        value = struct.unpack('<f' if field.size == 4 else '<d', data)[0]
        if not math.isfinite(value):
            return str(value), 'NONFINITE'
        return value, 'OBSERVED'
    value = int.from_bytes(data,'little',signed=field.encoding in (5,6))
    if field.encoding == 2:
        return (bool(value), 'OBSERVED') if value in (0,1) else (value, 'INVALID_BOOLEAN')
    return value, 'OBSERVED'
