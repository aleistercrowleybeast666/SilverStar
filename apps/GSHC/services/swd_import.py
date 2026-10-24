"""Offline target provenance for the GUI; never guess a part from an ELF/core."""
import hashlib
from pathlib import Path

from transport.swd_firmware import DiagnosticResult, Firmware_Import, FirmwareReply


def Firmware_ImportAuto(paths, *, target_cache=None, cancel=None):
    """Use an explicit/adjacent descriptor or a descriptor-bound exact ELF hash."""
    try:
        if cancel is not None and cancel.is_set():
            return FirmwareReply(DiagnosticResult.Cancelled, 'Firmware import cancelled')
        if type(paths) not in (tuple,list) or not 1 <= len(paths) <= 2:
            return FirmwareReply(DiagnosticResult.InvalidFile, 'Select one ELF/descriptor or an explicit pair')
        if target_cache is not None and (type(target_cache) is not dict or len(target_cache)>8 or
                any(type(key) is not str or len(key)!=64 or any(c not in '0123456789abcdef' for c in key) or
                    type(value) is not str or not 1<=len(value)<=128 for key,value in target_cache.items())):
            return FirmwareReply(DiagnosticResult.InvalidFile, 'Invalid descriptor-bound target cache')
        selected = [Path(path).absolute() for path in paths]
        if any(path.suffix.lower()=='.ssdiag' for path in selected):
            return Firmware_Import(selected,cancel=cancel)
        if len(selected)!=1 or selected[0].suffix.lower()!='.elf':
            return Firmware_Import(selected,cancel=cancel)
        elf = selected[0]
        if elf.is_symlink() or not elf.is_file():
            return FirmwareReply(DiagnosticResult.InvalidFile, 'ELF must be a regular file')
        companions = [path for path in (elf.with_suffix('.ssdiag'),elf.with_name(elf.name+'.ssdiag')) if path.exists()]
        if len(companions)>1:
            return FirmwareReply(DiagnosticResult.InvalidFile, 'Ambiguous adjacent diagnostic descriptors; select the intended descriptor explicitly')
        if companions:
            companion = companions[0]
            if companion.is_symlink() or companion.resolve().parent!=elf.resolve().parent:
                return FirmwareReply(DiagnosticResult.InvalidFile, 'Adjacent descriptor must be a regular sibling of the selected ELF')
            return Firmware_Import([companion,elf],cancel=cancel)
        if elf.stat().st_size>33554432:
            return FirmwareReply(DiagnosticResult.InvalidFile, 'ELF exceeds the 32 MiB limit')
        with elf.open('rb') as stream:
            data = stream.read(33554433)
        if len(data)>33554432:
            return FirmwareReply(DiagnosticResult.InvalidFile, 'ELF exceeds the 32 MiB limit')
        if cancel is not None and cancel.is_set():
            return FirmwareReply(DiagnosticResult.Cancelled, 'Firmware import cancelled')
        digest = hashlib.sha256(data).hexdigest()
        target = (target_cache or {}).get(digest)
        if target:
            reply = Firmware_Import([elf],target=target,cancel=cancel)
            if reply.result==DiagnosticResult.Ok and reply.firmware.sha256!=digest:
                return FirmwareReply(DiagnosticResult.InvalidFile, 'ELF changed during target provenance validation')
            return reply
        return FirmwareReply(DiagnosticResult.Unsupported,
            'A bare ELF and a core/family ID cannot uniquely identify the MCU part. '
            'Import the matching .ssdiag together with the ELF; no target was guessed.')
    except (OSError,ValueError,TypeError) as exc:
        return FirmwareReply(DiagnosticResult.InvalidFile,str(exc)[:400])
