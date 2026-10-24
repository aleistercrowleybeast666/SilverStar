"""Portable project entry; pure data for GSHC, explicit host build operations only."""
import argparse
from copy import deepcopy
from enum import Enum
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from .contract import DiagnosticError, DiagnosticResult, Json_Read, Require, Schema_Create, Schema_Validate

_contract_path=Path(__file__).with_name('swd_project_descriptor_v1.json')
if not _contract_path.is_file():_contract_path=Path(__file__).parents[4]/'contracts/swd_project_descriptor_v1.json'
_contract=json.loads(_contract_path.read_text(encoding='utf-8'))
FORMAT=_contract['format']
NAMES=_contract['roles']
_UNDECLARED=object()


class ProjectBindingResult(Enum):
    Ready='ready'
    Unavailable='unavailable'


def ProjectDescriptor_Create(project, target, role='flight', *, project_file=None, maintenance=_UNDECLARED):
    Require(role in NAMES, 'Invalid project diagnostic role')
    Require(type(project) is str and 1 <= len(project) <= 128, 'Invalid project name')
    value=dict(format=FORMAT, version=1, role=role, project=project,
                schema=Schema_Create(target), state='pending_build', detail='Compile this project before importing symbols', builds={})
    if project_file is not None:value['project_file']=project_file
    if maintenance is not _UNDECLARED:value['maintenance']=maintenance
    return value


def ProjectDescriptor_Relative(path):
    Require(type(path) is str and 1 <= len(path) <= 512 and '\\' not in path and ':' not in path
            and all(ord(c)>=32 and ord(c)!=127 for c in path),
            'ELF path must be relative to the project root')
    parts=PurePosixPath(path).parts
    Require(parts and not PurePosixPath(path).is_absolute() and all(p not in ('.','..') for p in parts)
            and str(PurePosixPath(path))==path and path.lower().endswith('.elf'), 'Unsafe project ELF path')
    return path


def ProjectDescriptor_Validate(value):
    required={'format','version','role','project','schema','state','detail','builds'}
    Require(type(value) is dict and required<=set(value)<=required|{'project_file','maintenance'}, 'Invalid project descriptor fields')
    Require(value['format']==FORMAT and type(value['version']) is int and value['version']==1, 'Unsupported project descriptor', DiagnosticResult.Unsupported)
    Require(type(value['role']) is str and value['role'] in NAMES, 'Invalid project role')
    Require(type(value['project']) is str and 1 <= len(value['project']) <= 128, 'Invalid project identity')
    if 'project_file' in value:
        Require(value['project_file']=='SilverStar.ssproject','Invalid associated project filename')
    if 'maintenance' in value and value['maintenance'] is not None:
        declaration=value['maintenance']
        Require(type(declaration) is dict and {'component','package_version','profile'} <= set(declaration) <= {'component','package_version','profile','uart'},'Invalid maintenance declaration')
        import re
        Require(all(type(item) is str and 1<=len(item)<=128 and
                    re.fullmatch(r'[A-Za-z0-9_.-]+',declaration[key]) for key in ('component','package_version','profile') for item in (declaration[key],)), 'Invalid maintenance declaration value')
        if 'uart' in declaration:
            uart = declaration['uart']
            keys = {'baudrate','data_bits','parity','stop_bits','block_size','block_deadline_ms','idle_timeout_ms','minimum_wire_ms'}
            Require(type(uart) is dict and set(uart) == keys, 'Invalid maintenance UART fields')
            Require(all(type(uart[k]) is int for k in keys - {'parity'}), 'Invalid maintenance UART integer')
            Require(1200 <= uart['baudrate'] <= 2000000 and uart['data_bits'] == 8 and uart['parity'] == 'none'
                    and uart['stop_bits'] == 1 and uart['block_size'] == 512
                    and uart['block_deadline_ms'] == uart['idle_timeout_ms'] == 30000
                    and uart['minimum_wire_ms'] == (8210000 + uart['baudrate'] - 1) // uart['baudrate'],
                    'Invalid maintenance UART contract')
    schema=Schema_Validate(value['schema'])
    Require(schema['version']==1 and schema['binding'] is None, 'Project schema must be unbound version 1')
    Require(value['state'] in _contract['states'] and type(value['detail']) is str and len(value['detail'])<=600, 'Invalid project build state')
    builds=value['builds']
    Require(type(builds) is dict and len(builds)<=8, 'Too many project build outputs')
    for key, item in builds.items():
        Require(type(key) is str and 1 <= len(key)<=512 and type(item) is dict and set(item)=={'elf','descriptor'}, 'Invalid build output')
        ProjectDescriptor_Relative(item['elf'])
        bound=Schema_Validate(item['descriptor'])
        Require(bound['binding'] is not None and bound['target']==schema['target']
                and bound['entries']==schema['entries'] and bound['diagnostics']==schema['diagnostics'], 'Build target/diagnostic contract mismatch')
        Require(bound['binding']['elf']==PurePosixPath(item['elf']).name, 'Build ELF basename mismatch')
    Require(value['state']!='ready' or bool(builds), 'Ready project has no bound ELF')
    Require(len(json.dumps(value,ensure_ascii=False).encode('utf-8'))<=65536, 'Project descriptor exceeds size limit')
    return value


def ProjectDescriptor_Path(project_file, relative):
    relative=ProjectDescriptor_Relative(relative)
    root=Path(project_file).absolute().parent.resolve()
    path=root.joinpath(*PurePosixPath(relative).parts)
    Require(not path.is_symlink() and path.resolve().is_relative_to(root), 'Project ELF escaped its root')
    return path


def ProjectDescriptor_Resolve(project_file, explicit_elf=None, cancel=None):
    """Select an output without guessing configuration, then verify its actual ELF."""
    from .elf import Firmware_Load
    path=Path(project_file).absolute()
    value=ProjectDescriptor_Validate(Json_Read(path))
    Require(value['state']=='ready', 'Project diagnostics '+value['state']+': '+value['detail'], DiagnosticResult.Unsupported)
    outputs=list(value['builds'].values())
    if explicit_elf is None:
        Require(len(outputs)==1, 'Multiple Debug/Release outputs; explicitly relocate/select the intended ELF: '+', '.join(value['builds']))
        selected=outputs[0]
        elf=ProjectDescriptor_Path(path, selected['elf'])
    else:
        elf=Path(explicit_elf).absolute()
        # A moved individual ELF is allowed only with explicit user selection
        # and the same recorded content hash. No file is copied or rewritten.
        Require(not elf.is_symlink() and elf.is_file(), 'Relocated ELF must be a regular file')
        exact=[item for item in outputs if ProjectDescriptor_Path(path,item['elf']).resolve()==elf.resolve()]
        if len(exact)==1:selected=exact[0]
        else:
            from .contract import Sha256
            Require(elf.stat().st_size<=33554432, 'ELF exceeds the 32 MiB limit')
            with elf.open('rb') as stream:data=stream.read(33554433)
            Require(len(data)<=33554432, 'ELF exceeds the 32 MiB limit')
            digest=Sha256(data)
            matching=[item for item in outputs if item['descriptor']['binding']['sha256']==digest]
            Require(bool(matching), 'Relocated ELF hash does not match any successful project build')
            Require(len({json.dumps(item['descriptor'],sort_keys=True) for item in matching})==1,
                    'Ambiguous relocated ELF; select a recorded configuration path')
            selected=matching[0]
    Require(elf.is_file(), 'Recorded ELF is missing; compile again or explicitly relocate it')
    return Firmware_Load(elf,selected['descriptor'],cancel=cancel,include_watch=True)


def _ProjectDescriptor_Write(path, value):
    path=Path(path).absolute();root=path.parent.resolve()
    Require(path.name==NAMES[value['role']] and not path.is_symlink() and path.resolve().parent==root,
            'Unsafe generated project descriptor output')
    ProjectDescriptor_Validate(value)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=root,prefix='.ssdiag-project-',suffix='.tmp',delete=False) as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary=Path(stream.name)
    os.replace(temporary,path)


def ProjectDescriptor_Begin(project_file):
    value=deepcopy(ProjectDescriptor_Validate(Json_Read(project_file)))
    value.update(state='pending_build',detail='Build started; no new successful ELF binding has been published')
    _ProjectDescriptor_Write(project_file,value)


def ProjectDescriptor_Bind(project_file, elf, cancel=None, *, image_file=None):
    from .elf import Firmware_Load
    path=Path(project_file).absolute();elf=Path(elf).absolute()
    value=deepcopy(ProjectDescriptor_Validate(Json_Read(path)))
    root=path.parent.resolve()
    Require(not elf.is_symlink() and elf.resolve().is_relative_to(root), 'Build ELF escaped project root')
    relative=ProjectDescriptor_Relative(elf.resolve().relative_to(root).as_posix())
    key=str(PurePosixPath(relative).parent)
    value['builds'].pop(key,None)
    try:
        schema=deepcopy(value['schema'])
        if image_file is not None:
            # Strict ELF+HEX identity; the HEX is an explicit safe sibling,
            # never a guessed newest build output.
            from .contract import Schema_Create
            image_schema=Schema_Create(schema['target'],image_file=image_file)
            schema.update(version=2,image=image_schema['image'])
        firmware=Firmware_Load(elf,schema,cancel=cancel)
        Require(len(value['builds'])<8, 'Too many diagnostic configurations; regenerate metadata')
        value['builds'][key]=dict(elf=relative,descriptor=firmware.descriptor)
        value.update(state='ready',detail='Bound to successfully linked ELF; live flash matching remains required')
    except (DiagnosticError,OSError) as exc:
        value.update(state='unavailable',detail=str(exc)[:600])
    _ProjectDescriptor_Write(path,value)
    return ProjectBindingResult(value['state']),value['detail']


def ProjectDescriptor_GeneratedMatch(current, expected):
    """Only build-owned fields may differ in a generated root descriptor."""
    a=deepcopy(ProjectDescriptor_Validate(current));b=deepcopy(ProjectDescriptor_Validate(expected))
    # Earlier generated v1 entries lacked these declarations. Only ordinary
    # SCG regeneration may supply newly declared fields from its actual model.
    for field in ('project_file','maintenance'):
        if field not in a and field in b:a[field]=deepcopy(b[field])
    for item in (a,b):item.update(builds={},state='pending_build',detail='')
    return a==b


def main(argv=None):
    parser=argparse.ArgumentParser(description='Update generated project diagnostics after a successful host build')
    parser.add_argument('operation',choices=('begin','bind'))
    parser.add_argument('--project',required=True);parser.add_argument('--elf')
    parser.add_argument('--image-file',help='Explicit HEX sibling basename for strict v2 image binding')
    args=parser.parse_args(argv)
    if args.operation=='begin':
        ProjectDescriptor_Begin(args.project);state,detail='pending_build','Build started'
    else:
        Require(bool(args.elf), 'An explicitly linked ELF is required')
        state,detail=ProjectDescriptor_Bind(args.project,args.elf,image_file=args.image_file)
        state=state.value
    print(json.dumps(dict(diagnostics=state,detail=detail),ensure_ascii=False))
    # Missing symbols/dependencies are explicit unavailable metadata, not a
    # fictitious hash or a failed firmware link. Unsafe writes still raise.
    return 0


if __name__=='__main__':raise SystemExit(main())
