"""Shared SCG/GSHC artifact importer, with no probe or target I/O."""
from dataclasses import dataclass
from pathlib import Path
import sys

try:
    import silverstar_diagnostics
except ImportError:
    # Fixed first-party monorepo location, never an imported file's directory.
    sys.path.insert(0,str(Path(__file__).absolute().parents[2]/'SCG/src'))
from silverstar_diagnostics.contract import (DiagnosticError, DiagnosticResult, Json_Read,
                                            Schema_Validate, Require, Contract_Get)
from silverstar_diagnostics.elf import Firmware_Load
from silverstar_diagnostics.targets import Target_Get, Targets_List


@dataclass(frozen=True)
class FirmwareReply:
    result: DiagnosticResult
    detail: str = ''
    firmware: object = None
    project_metadata: object = None
    elf_selection_required: bool = False


def Firmware_Import(paths, *, target=None, cancel=None):
    """Select one .ssdiag (safe sibling ELF), one ELF, or an explicit pair."""
    metadata=None
    selection_required=False
    try:
        Require(type(paths) in (list,tuple) and 1 <= len(paths) <= 2, 'Select one descriptor/ELF or a descriptor + ELF pair')
        selected = [Path(p).absolute() for p in paths]
        Require(all(p.suffix.lower() in ('.ssdiag','.elf') for p in selected), 'Only .ssdiag and .elf files are accepted')
        descriptors = [p for p in selected if p.suffix.lower()=='.ssdiag']
        elfs = [p for p in selected if p.suffix.lower()=='.elf']
        Require(len(descriptors) <= 1 and len(elfs) <= 1, 'Duplicate input type')
        raw=Json_Read(descriptors[0]) if descriptors else None
        from silverstar_diagnostics.project_descriptor import FORMAT, ProjectDescriptor_Resolve
        if raw is not None and raw.get('format')==FORMAT:
            from silverstar_diagnostics.project_descriptor import ProjectDescriptor_Validate,ProjectDescriptor_Path
            ProjectDescriptor_Validate(raw)
            metadata={key:raw[key] for key in ('project','project_file','maintenance') if key in raw}
            outputs=list(raw['builds'].values())
            selection_required=(raw['state']=='ready' and (len(outputs)>1 or
                len(outputs)==1 and not ProjectDescriptor_Path(descriptors[0],outputs[0]['elf']).is_file()))
            firmware=ProjectDescriptor_Resolve(descriptors[0],elfs[0] if elfs else None,cancel)
            available=sum(not entry.unavailable for entry in firmware.entries)
            return FirmwareReply(DiagnosticResult.Ok,
                f'{firmware.target.name}; project ssdiag; ELF {firmware.sha256[:12]}; fields={available}/{len(firmware.entries)}; live flash verification required',firmware,metadata,False)
        descriptor = Schema_Validate(raw) if raw is not None else None
        if not elfs:
            Require(descriptor['binding'] is not None, 'Unbound schema requires an explicitly selected ELF')
            elf = descriptors[0].parent / descriptor['binding']['elf']
            Require(not elf.is_symlink() and elf.resolve().parent == descriptors[0].resolve().parent,
                    'Sibling ELF path escaped descriptor directory')
        else: elf = elfs[0]
        firmware = Firmware_Load(elf,descriptor,target=target,cancel=cancel,include_watch=True)
        available = sum(not entry.unavailable for entry in firmware.entries)
        return FirmwareReply(DiagnosticResult.Ok,
            f'{firmware.target.name}; ELF {firmware.sha256[:12]}; DWARF={firmware.dwarf}; fields={available}/{len(firmware.entries)}; each connection requires live flash verification',firmware)
    except DiagnosticError as exc:
        return FirmwareReply(exc.result,str(exc)[:600],None,metadata,selection_required)
    except Exception as exc:
        return FirmwareReply(DiagnosticResult.InvalidFile,str(exc)[:600])
