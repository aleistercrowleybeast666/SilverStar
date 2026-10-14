"""Trusted metadata, separate from untrusted .ssdiag. Never load target code."""
from dataclasses import dataclass
from pathlib import Path
import re
from .contract import Json_Read, Require, DiagnosticResult


@dataclass(frozen=True)
class TargetProfile:
    name: str
    core: str
    ram: tuple
    flash: tuple
    source: str
    ap: int = 0

    def Contains(self, address, length, kind):
        return (type(address) is int and type(length) is int and length > 0 and
                any(lo <= address < address + length <= hi for lo, hi in getattr(self, kind)))

    def CoreMatches(self, cpuid):
        part = {'Cortex-M0':0xC20, 'Cortex-M0+':0xC60, 'Cortex-M3':0xC23, 'Cortex-M4':0xC24}[self.core]
        return cpuid >> 24 == 0x41 and (cpuid >> 4) & 0xFFF == part


def Targets_List():
    data = Json_Read(Path(__file__).with_name('stm32_targets.json'), 1048576)
    return tuple(sorted(data['targets']))


def Target_Get(name):
    data = Json_Read(Path(__file__).with_name('stm32_targets.json'), 1048576)
    names = {key.casefold():key for key in data['targets']}
    if isinstance(name, str) and name.casefold() not in names:
        # Official PDSC uses literal x for package temperature/speed suffixes.
        # Exact package selection is user input, not silicon identification.
        matches = [key for key in data['targets'] if re.fullmatch(re.escape(key).replace('x','[A-Za-z0-9]'),name,re.I)]
        if not matches:
            matches = [key for key in data['targets'] if re.fullmatch(re.escape(key)+r'[A-Z][0-9]',name,re.I)]
        if len(matches) == 1: name = matches[0]
    Require(isinstance(name, str) and name.casefold() in names,
            'Target not in installed trusted metadata catalog', DiagnosticResult.Unsupported)
    canonical = names[name.casefold()]
    value = data['targets'][canonical]
    Require(value['core'] in ('Cortex-M0','Cortex-M0+','Cortex-M3','Cortex-M4') and value['ap'] == 0,
            'Core/AP capability requires a separately reviewed read-only adapter', DiagnosticResult.Unsupported)
    ram, flash = [], []
    for kind, start, size in value['memory']:
        end = start + size
        # Exclude aliases, OTP, peripherals, system ROM, external RAM/flash.
        if kind == 'ram' and (0x20000000 <= start < end <= 0x20100000 or 0x10000000 <= start < end <= 0x10040000):
            ram.append((start, end))
        elif kind == 'flash' and 0x08000000 <= start < end <= 0x08200000:
            flash.append((start, end))
    Require(ram and flash, 'Target has no approved internal RAM/flash regions', DiagnosticResult.Unsupported)
    return TargetProfile(canonical, value['core'], tuple(ram), tuple(flash), value['source'])
