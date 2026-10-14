"""Post-build binding; failure replaces any obsolete binding with an unbound schema."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from enum import Enum
from .contract import Json_Read, Schema_Validate, DiagnosticError
from .elf import Firmware_Load


class BindingResult(Enum):
    Bound = 'bound'
    Unbound = 'unbound'


def Binding_Write(schema, elf, cancel=None):
    elf = Path(elf).absolute()
    root = elf.parent.resolve()
    output = elf.with_suffix('.ssdiag')
    if output.is_symlink() or output.resolve().parent != root:
        raise ValueError('Unsafe diagnostic output path')
    value = Schema_Validate(Json_Read(schema))
    value['binding'] = None
    result, detail = BindingResult.Unbound, ''
    try:
        firmware = Firmware_Load(elf,value,cancel=cancel)
        value = firmware.descriptor
        result = BindingResult.Bound
        detail = '; '.join(e.id+': '+e.unavailable for e in firmware.entries if e.unavailable)
    except DiagnosticError as exc:
        detail = str(exc)
    data = json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    # Same-directory atomic replacement, no user payload or source writes.
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=root,prefix='.ssdiag-',suffix='.tmp',delete=False) as stream:
        stream.write(data)
        temp = Path(stream.name)
    os.replace(temp,output)
    return result, detail, output


def main(argv=None):
    parser = argparse.ArgumentParser(description='Bind generated diagnostics to the actual successfully linked ELF')
    parser.add_argument('--schema',required=True)
    parser.add_argument('--elf',required=True)
    args = parser.parse_args(argv)
    result, detail, output = Binding_Write(args.schema,args.elf)
    print(json.dumps(dict(diagnostics=result.value,detail=detail,output=str(output)),ensure_ascii=False))
    return 0 if result == BindingResult.Bound else 2


if __name__ == '__main__': raise SystemExit(main())
