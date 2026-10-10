"""Effective ARM attribute and independent vector-slot checks, separate from text ownership."""
from __future__ import annotations

import re
import struct


def NativeAssemblyDirectives_Validate(text: str, *, core: str, fpu: str,
                                     reviewed_assert_trap: bool = False) -> None:
    arch = {"cortex-m0": "armv6-m", "cortex-m0plus": "armv6s-m",
            "cortex-m3": "armv7-m", "cortex-m4": "armv7e-m"}[core]
    clean = re.sub(r"/\*.*?\*/|//[^\r\n]*|^[ \t]*@[^\r\n]*", "", text, flags=re.S | re.M)
    for kind, value in re.findall(r"(?<!\w)\.(cpu|arch|arch_extension|fpu)\s+([A-Za-z0-9_.+-]+)", clean):
        value = value.lower()
        allowed = {"cpu": {core}, "arch": {arch}, "arch_extension": set(),
                   "fpu": {"softvfp", *([fpu] if fpu else [])}}[kind]
        if value not in allowed:
            raise ValueError("Native CPU directive contradicts independent device facts: ." + kind + " " + value)
    raw = list(re.finditer(r"(?<!\w)\.inst(?:\.[nw])?\b[^\r\n]*", clean))
    if raw:
        # GCC emits the established __builtin_trap as Thumb UDF #255 (0xdeff).
        # This exact opcode is available on all admitted M profiles. Only the
        # unchanged owned assertion unit can request this check; native startup
        # and arbitrary inline assembly cannot use it to bypass ISA validation.
        trap = re.search(r"(?ms)^SilverStarAssert_Fail:\s*\n(.*?)^[ \t]*\.size\s+"
                         r"SilverStarAssert_Fail\s*,", clean)
        if (not reviewed_assert_trap or trap is None or len(raw) != 1 or
                not trap.start(1) <= raw[0].start() < trap.end(1) or
                not re.fullmatch(r"\s*\.inst\s+0xdeff\s*", raw[0][0])):
            raise ValueError("Native raw instruction encoding requires a separately reviewed instruction contract")


def NativeArmAttributes_Validate(attributes: str, *, core: str, fpu: str, hard_float: bool,
                                 assembly: bool = False) -> None:
    tags = dict(re.findall(r"(?m)^\s*(Tag_\w+):\s*([^\r\n]+)", attributes))
    arch, thumb = {"cortex-m0": ("v6S-M", "Thumb-1"),
                   "cortex-m0plus": ("v6S-M", "Thumb-1"),
                   "cortex-m3": ("v7", "Thumb-2"),
                   "cortex-m4": ("v7E-M", "Thumb-2")}[core]
    profile = tags.get("Tag_CPU_arch_profile", "Microcontroller" if core in {"cortex-m0","cortex-m0plus"} else "")
    if (tags.get("Tag_CPU_arch") != arch or tags.get("Tag_THUMB_ISA_use") != thumb or
            profile != "Microcontroller"):
        raise ValueError("Actual ARM architecture attributes contradict independent core facts")
    if "Tag_ARM_ISA_use" in tags or "Tag_Advanced_SIMD_arch" in tags:
        raise ValueError("Actual ARM object requires an unsupported instruction profile")
    if "Tag_FP_arch" in tags and (fpu != "fpv4-sp-d16" or tags["Tag_FP_arch"] != "VFPv4-D16"):
        raise ValueError("Actual ARM floating attributes contradict independent FPU facts")
    if "Tag_ABI_HardFP_use" in tags and tags["Tag_ABI_HardFP_use"] != "SP only":
        raise ValueError("Actual ARM object requires unsupported floating instructions")
    arguments = tags.get("Tag_ABI_VFP_args")
    if (arguments is not None and arguments != "VFP registers") or (arguments is not None and not hard_float):
        raise ValueError("Actual ARM floating calling ABI contradicts native contract")
    if hard_float and not assembly and arguments != "VFP registers":
        raise ValueError("Actual ARM C/ELF lacks its required hard-float calling ABI")


def NativeIndependentVectors_Validate(vector: bytes, symbols: str, slots: dict[str, int]) -> None:
    entries = {name: (int(address, 16), kind) for address, kind, name in
               re.findall(r"(?m)^([0-9a-fA-F]+)\s+(\w)\s+(\w+)$", symbols)}
    if not slots:
        raise ValueError("Independent IRQn slots are missing")
    for handler, irqn in slots.items():
        if handler not in entries or entries[handler][1] != "T":
            raise ValueError("Independent IRQn has no strong compiled handler: " + handler)
        offset = (irqn + 16) * 4
        if (offset < 0 or offset + 4 > len(vector) or
                struct.unpack_from("<I", vector, offset)[0] != (entries[handler][0] | 1)):
            raise ValueError("Actual vector contradicts independent IRQn binding: " + handler)
