"""Explicit native-source replacements for the experimental USB workflow."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy


def NativeUsbDigest_Get(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def NativeUsbJson_Read(path: Path) -> object:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Native USB metadata exceeds 4 MiB")
    with path.open("rb") as stream:
        body = stream.read(4 * 1024 * 1024 + 1)
    if len(body) > 4 * 1024 * 1024:
        raise ValueError("Native USB metadata grew beyond its bound")
    return json.loads(body)


def _Relative_Resolve(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", relative)
            or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise ValueError("Invalid native USB graph path")
    return WorkspacePolicy(root).Path_Resolve(root / relative, allow_root=False)


def NativeUsbKit_Verify(output: Path, expected: str) -> dict:
    policy = WorkspacePolicy(output)
    path = policy.Path_Resolve(output / "kit-sha256.json")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Native USB kit inventory changed; regenerate to a new directory")
    manifest = NativeUsbJson_Read(path)
    if not isinstance(manifest, dict) or not 1 <= len(manifest) <= 256:
        raise ValueError("Native USB kit inventory is invalid")
    for relative, digest in manifest.items():
        entry = _Relative_Resolve(output, relative)
        if entry.stat().st_size > 4 * 1024 * 1024 or hashlib.sha256(entry.read_bytes()).hexdigest() != digest:
            raise ValueError("Native USB kit content changed: " + relative)
    # An unlisted header can shadow native headers through our include order.
    # Compiler outputs live in sibling compile-/analysis- directories, never here.
    visited = 0
    for relative_root in ("Inc", "Common", "Native", "Src"):
        for directory, folders, names in os.walk(output / relative_root, followlinks=False):
            for name in folders + names:
                visited += 1
                if visited > 2048:
                    raise ValueError("Native USB kit tree exceeds its bound")
                entry = Path(directory) / name
                if entry.is_symlink() or entry.is_junction():
                    raise ValueError("Native USB kit contains an alias")
                entry = policy.Path_Resolve(entry)
                if entry.is_file() and entry.relative_to(output).as_posix() not in manifest:
                    raise ValueError("Native USB kit has an unlisted input: " + str(entry))
    return manifest


def NativeUsbGraph_Resolve(plan, native: Path, output: Path) -> dict:
    """Consume source-bound derivatives; never execute the imported build script."""
    manifest = NativeUsbJson_Read(output / "lifecycle-integration.json")
    profile = manifest["profile"]
    # These are reviewed controller/compiler bindings, not MCU-family admission.
    configurations = {
        "hpcd_USB_FS": ("cortex-m3", "", {"USB_LP_CAN1_RX0_IRQHandler": 20}),
        "hpcd_USB_OTG_FS": ("cortex-m4", "fpv4-sp-d16", {"OTG_FS_IRQHandler": 67}),
    }
    if profile["pcd"] not in configurations:
        raise ValueError("Native USB compiler/IRQ binding requires review")
    core, fpu, slots = configurations[profile["pcd"]]
    build = plan.capabilities["build"]
    if build["cpu"] != ["-mcpu=" + core]:
        raise ValueError("Native USB CPU differs from the reviewed compiler binding")
    if any(not re.fullmatch(r"-D[A-Za-z_]\w*(?:=[A-Za-z0-9_]+)?", d) for d in build["defines"]):
        raise ValueError("Native USB preprocessor definitions must be literal -D values")
    replacements = {}
    for row in manifest["replacements"]:
        original, derived = row["original"], row["derived"]
        _Relative_Resolve(native, original)
        replacement = _Relative_Resolve(output, derived)
        if original in replacements or str(replacement) in replacements.values():
            raise ValueError("Native USB replacement has duplicate ownership")
        if original not in plan.files_sha256:
            raise ValueError("Native USB replacement lacks its inspected source")
        if original.endswith(".c") and original not in build["sources"]:
            raise ValueError("Native USB replacement is absent from the native build")
        replacements[original] = str(replacement)
    sources = [{"input": p, "compiled": replacements.get(p, str(_Relative_Resolve(native, p))),
                "policy": "vendor"} for p in build["sources"]]
    for relative in [*manifest["additional_sources"], "Common/Src/silverstar_assert.c"]:
        path = _Relative_Resolve(output, relative)
        if not path.is_file():
            raise ValueError("Native USB additional source is missing")
        sources.append({"input": relative, "compiled": str(path), "policy": "first_party"})
    if len({s["compiled"].casefold() for s in sources}) != len(sources):
        raise ValueError("Native USB source is compiled more than once")
    if sum(Path(s["compiled"]).name == "silverstar_assert.c" for s in sources) != 1:
        raise ValueError("Native USB requires exactly one assertion owner")
    includes = [output / "Inc", output / "Common/Inc"]
    includes += [Path(new).parent for old, new in replacements.items() if old.endswith(".h")]
    includes += [_Relative_Resolve(native, token[2:]) for token in build["include_dirs"]]
    flags = ["-mcpu=" + core, "-mthumb", "-mfloat-abi=" + ("hard" if fpu else "soft")]
    if fpu:
        flags.append("-mfpu=" + fpu)
    return {"format": "silverstar.usb.native-source-graph", "version": 1,
        "scope": "EXPERIMENTAL_NATIVE_USB_ONLY", "source_sha256": NativeUsbDigest_Get(plan.files_sha256),
        "sources": sources, "assembly": [str(_Relative_Resolve(native, p)) for p in build["asm_sources"]],
        "includes": list(dict.fromkeys(str(p) for p in includes)), "defines": build["defines"],
        "mcu_flags": flags, "core": core, "fpu": fpu, "independent_irq_slots": slots,
        "linker": str(_Relative_Resolve(native, build["linker_script"][0])),
        "native_root": str(native), "native_files_sha256": plan.files_sha256,
        "replacements": replacements, "profile": profile,
        "critical_contracts": "NOT_PROVEN", "hardware": "NOT_TESTED"}
