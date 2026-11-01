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


def NativeUsbHeapSymbols_Validate(value: object) -> list[str]:
    if type(value) is not list or value not in ([], ['_sbrk']):
        raise ValueError('Native USB heap symbols must be [] or exactly ["_sbrk"]')
    return list(value)


def _HeapPolicy_Validate(manifest: dict, plan, native: Path, output: Path) -> tuple[str | None, list[str]]:
    """A metadata selector cannot assign arbitrary compile/link ownership."""
    heap = manifest.get('heap_policy', {})
    if not isinstance(heap, dict):
        raise ValueError('Native USB heap policy must be an object')
    symbols = NativeUsbHeapSymbols_Validate(heap.get('required_link_symbols', []))
    rows = manifest['replacements']
    if heap.get('allocation') != 'REJECT_ALL_REQUESTS':
        if symbols or any(row.get('derived') == 'Src/native_no_heap.c' for row in rows):
            raise ValueError('Native USB heap replacement requires its explicit policy')
        return None, symbols
    from silverstar_fccg.generator.native_no_heap import NativeNoHeap_FilesRender
    original = heap.get('original')
    if (not isinstance(original, str) or Path(original).name != 'sysmem.c' or
            original not in plan.capabilities['build']['sources'] or symbols != ['_sbrk'] or
            heap.get('derived') != 'Src/native_no_heap.c' or
            heap.get('owner') != 'native_no_heap.NativeNoHeap_FilesRender'):
        raise ValueError('Native USB heap policy differs from the reviewed owner')
    original_bytes = _Relative_Resolve(native, original).read_bytes()
    expected = NativeNoHeap_FilesRender(original_bytes)
    matching = [row for row in rows if row.get('original') == original]
    required = {'original': original, 'derived': 'Src/native_no_heap.c', 'policy': 'first_party',
        'original_sha256': hashlib.sha256(original_bytes).hexdigest(),
        'derived_sha256': hashlib.sha256(expected['Generated/Src/native_no_heap.c']).hexdigest()}
    if (len(matching) != 1 or any(matching[0].get(key) != value or heap.get(key) != value
                                 for key, value in required.items())):
        raise ValueError('Native USB heap replacement policy or identity changed')
    for relative, body in expected.items():
        if _Relative_Resolve(output, relative.removeprefix('Generated/')).read_bytes() != body:
            raise ValueError('Native USB heap source differs from the reviewed rejecting ABI')
    return original, symbols


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
    policies = {}
    heap_owner, required_symbols = _HeapPolicy_Validate(manifest, plan, native, output)
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
        policy = row.get('policy', 'vendor')
        expected_policy = 'first_party' if original == heap_owner else 'vendor'
        if policy != expected_policy:
            raise ValueError('Native USB replacement policy differs from the reviewed heap/source owner')
        policies[original] = policy
    sources = [{"input": p, "compiled": replacements.get(p, str(_Relative_Resolve(native, p))),
                "policy": policies.get(p, 'vendor')} for p in build["sources"]]
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
        "required_link_symbols": required_symbols,
        "configuration_derivation": manifest.get('configuration_derivation'),
        "critical_contracts": "NOT_PROVEN", "hardware": "NOT_TESTED"}
