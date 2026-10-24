"""Reproducible host/native ABI evidence for the experimental CDC kit.

Never accesses serial/DAP, executes an imported Makefile, or installs firmware.
All outputs go to one NEW task directory. No cleanup of existing data occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import difflib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[4]
SCG = REPO / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))


def Integrated_Validate(reference, output, run, *, baseline=False, f407_reference=None):
    """Build the delivered replacements, without executing native build scripts.

    Reviewed controller/ABI bindings constrain the two compiler configurations.
    This is a USB integration graph, not normal Ground admission/architecture.
    """
    from silverstar_fccg.app.usb_transport import UsbTransport_Export, UsbTransport_Plan, _Project_Read
    from silverstar_fccg.generator.multi_target import _Makefile_Render
    from silverstar_fccg.hardware.native_machine_contract import (
        NativeArmAttributes_Validate, NativeIndependentVectors_Validate)
    from silverstar_fccg.hardware.usb_transport_profiles import CONTROLLER_CONTRACTS

    strict = ["-Wall", "-Wextra", "-Wpedantic", "-Werror", "-Wconversion", "-Wsign-conversion",
        "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion", "-Wcast-align", "-Wcast-qual",
        "-Wstrict-prototypes", "-Wmissing-prototypes", "-Wswitch-enum", "-Wvla"]
    vendor = ["-Wall", "-Werror=implicit-function-declaration", "-Werror=incompatible-pointer-types",
              "-Werror=return-type", "-Wvla", "-Werror=vla"]
    symbols_required = ["UsbCdc_Service", "UsbCdc_Configure", "UsbCdc_Quiesced", "UsbCdc_Receive",
        "UsbCdc_Read", "UsbCdc_Write", "UsbCdc_LinkDown", "UsbCdc_SessionGet", "UsbCdcRetire_Endpoint",
        "UsbCdcRetire_ConfigurationCheck"]
    if baseline:
        symbols_required = ["USBD_Init", "USBD_CDC_TransmitPacket"]
    profiles = (
        ("f103", "cortex-m3", "", {"USB_LP_CAN1_RX0_IRQHandler": 20}),
        ("f407", "cortex-m4", "fpv4-sp-d16", {"OTG_FS_IRQHandler": 67}),
    )
    receipts = []
    for part, core, fpu, slots in profiles:
        native = reference / ("cube-" + part + "-usb")
        if part == "f407" and f407_reference is not None:
            native = f407_reference
        root = output / "native" / part
        if baseline:
            plan = UsbTransport_Plan(native)
            from silverstar_fccg.generator.usb_cdc_integration import UsbIntegrationProfile_Get
            profile = UsbIntegrationProfile_Get(_Project_Read(native))
            root.mkdir(parents=True)
            manifest = {"replacements": [], "additional_sources": [], "profile": profile}
        else:
            plan = UsbTransport_Export(native, root, integrate=True)
            manifest = json.loads((root / "lifecycle-integration.json").read_text())
        build = plan.capabilities["build"]
        contract = CONTROLLER_CONTRACTS[manifest['profile']['controller_contract']]
        if contract['compiler'] != {'core': core, 'fpu': fpu,
                'float_abi': 'hard' if fpu else 'soft', 'independent_irq_slots': slots}:
            raise ValueError('Controller contract differs from independent compiler/IRQ validation binding')
        flags = ["-mcpu=" + core, "-mthumb", "-mfloat-abi=" + ("hard" if fpu else "soft")]
        if fpu:
            flags += ["-mfpu=" + fpu]
        if build["cpu"] != ["-mcpu=" + core]:
            raise ValueError("reviewed compiler CPU differs from native inventory")
        replacements = {entry["original"]: entry["derived"] for entry in manifest["replacements"]}
        sources = []
        for source in build["sources"]:
            sources.append({"input": source, "compiled": str(root / replacements[source]) if source in replacements
                            else str(native / source), "policy": "vendor"})
        for source in manifest["additional_sources"]:
            dest = root / "Generated/UsbTransport" / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((root / source).read_bytes())
            sources.append({"input": "Generated/UsbTransport/" + source, "compiled": str(dest), "policy": "first_party"})
        for header in (root / "Inc").glob("*.h"):
            dest = root / "Generated/UsbTransport/Inc" / header.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(header.read_bytes())
        if not baseline:
            sources.append({"input": "Common/Src/silverstar_assert.c",
                            "compiled": str(root / "Common/Src/silverstar_assert.c"), "policy": "first_party"})
        includes = [] if baseline else [root / "Generated/UsbTransport/Inc", root / "Common/Inc"]
        includes += [root / entry["derived"] / ".." for entry in manifest["replacements"]
                     if entry["original"].endswith(".h")]
        includes += [native / token[2:] for token in build["include_dirs"]]
        includes = [path.resolve() for path in includes]
        defines = build["defines"]
        graph = {"scope": "UNMODIFIED_NATIVE_BASELINE" if baseline else "USB_ONLY_NATIVE_CALLBACK_REPLACEMENTS_NOT_GROUND_ADMISSION",
            "sources": sources, "assembly": [str(native / p) for p in build["asm_sources"]],
            "includes": list(map(str, includes)), "defines": defines, "mcu_flags": flags,
            "linker": str(native / build["linker_script"][0]), "required_symbols": symbols_required,
            "independent_irq_slots": slots, "input_hashes": plan.files_sha256,
            "profile": manifest["profile"], "critical_contracts": "NOT_PROVEN"}
        graph['controller_contract'] = contract
        (root / "Generated").mkdir(exist_ok=True)
        (root / "Generated/usb_transport_source_graph.json").write_text(json.dumps(graph, indent=2))
        if len(set(entry["input"] for entry in sources)) != len(sources):
            raise ValueError("duplicate source owner")
        # Every replacement must be compiled exactly once; no original callback
        # source may remain in the graph. Native input is referenced read-only.
        for old, derived in replacements.items():
            if old.endswith(".c"):
                assert sum(entry["compiled"] == str(root / derived) for entry in sources) == 1
                assert all(entry["compiled"] != str(native / old) for entry in sources)
        receipt = {"graph_sha256": hashlib.sha256((root / "Generated/usb_transport_source_graph.json").read_bytes()).hexdigest(),
                   "part": part, "builds": [], "critical_contracts": "NOT_PROVEN",
                   "stack_wcet_hardware": "NOT_PROVEN", "warning_logs": [], "linked_library_files": {},
                   "native_root": str(native), "native_configuration": plan.capabilities["native_configuration"],
                   "configuration_findings": plan.capabilities["configuration_findings"]}
        receipt['controller_contract'] = contract
        sdk_facts = {}
        for library in ("libc_nano.a", "libm.a", "libnosys.a", "libgcc.a"):
            path = Path(run(part + "-locate-" + library, ["arm-none-eabi-gcc", *flags,
                "-print-file-name=" + library], root).strip()).resolve()
            receipt["linked_library_files"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        for mode in ("normal", "analyzer"):
            build_dir = root / "build" / mode
            build_dir.mkdir(parents=True)
            objects = []
            for index, entry in enumerate(sources):
                obj = build_dir / (str(index).zfill(2) + "-" + Path(entry["input"]).stem + ".o")
                command = ["arm-none-eabi-gcc", *flags, "-std=c11", "-Os", "-ffunction-sections",
                    "-fdata-sections", "-fstack-usage", *("-I" + str(p) for p in includes), *defines,
                    *(strict if entry["policy"] == "first_party" else vendor)]
                if mode == "analyzer":
                    command.append("-fanalyzer")
                command += ["-MD", "-MF", str(obj.with_suffix(".d")), "-c", entry["compiled"], "-o", str(obj)]
                diagnostics = run(part + "-" + mode + "-" + obj.stem, command, root)
                if re.search(r"\bwarning:", diagnostics):
                    receipt["warning_logs"].append(part + "-" + mode + "-" + obj.stem + ".log")
                objects.append(str(obj))
                if mode == "normal" and Path(entry["input"]).name.endswith(('_hal_pcd.c', '_hal_pcd_ex.c', '_ll_usb.c')):
                    selected = obj.with_suffix('.i')
                    run(part + '-preprocessed-' + obj.stem, command[:command.index('-MD')] +
                        ['-E', entry['compiled'], '-o', str(selected)], root)
                    from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
                    text = selected.read_text(encoding='utf8')
                    names = ('HAL_PCD_Init', 'HAL_PCD_EP_Open', 'HAL_PCD_EP_Close', 'HAL_PCD_EP_Abort',
                        'HAL_PCD_EP_Transmit', 'HAL_PCD_EP_Receive', 'HAL_PCD_IRQHandler',
                        'USB_EPStopXfer', 'USB_DeactivateEndpoint', 'USB_ActivateEndpoint', 'USB_EPStartXfer',
                        'USB_FlushTxFifo', 'USB_FlushRxFifo', 'HAL_PCDEx_PMAConfig',
                        'HAL_PCDEx_SetRxFiFo', 'HAL_PCDEx_SetTxFiFo')
                    for name in names:
                        try:
                            start, _opening, end = NativeC_FunctionSpanGet(text, name)
                        except ValueError:
                            continue
                        sdk_facts[name] = {'source': entry['compiled'], 'source_sha256': hashlib.sha256(Path(entry['compiled']).read_bytes()).hexdigest(),
                            'effective_translation_unit': str(selected), 'preprocessed_sha256': hashlib.sha256(selected.read_bytes()).hexdigest(),
                            'function': text[start:end], 'semantic_acceptance': 'MANUAL_REVIEW_REQUIRED'}
            for index, source in enumerate(graph["assembly"]):
                obj = build_dir / ("asm-" + str(index) + ".o")
                run(part + "-" + mode + "-asm", ["arm-none-eabi-gcc", *flags, *defines,
                    "-x", "assembler-with-cpp", "-MD", "-MF", str(obj.with_suffix(".d")),
                    "-c", source, "-o", str(obj)], root)
                objects.append(str(obj))
            elf = build_dir / "usb-transport-integrated.elf"
            link = run(part + "-" + mode + "-link", ["arm-none-eabi-gcc", *objects, *flags,
                *("-Wl,-u," + name for name in symbols_required),
                "-Wl,--gc-sections,-Map=" + str(elf.with_suffix(".map")), "-T" + graph["linker"],
                "-specs=nano.specs", "-lc", "-lm", "-lnosys", "-o", str(elf)], root)
            if re.search(r"\bwarning:", link):
                receipt["warning_logs"].append(part + "-" + mode + "-link.log")
            attributes = run(part + "-" + mode + "-attributes", ["arm-none-eabi-readelf", "-A", str(elf)], root)
            NativeArmAttributes_Validate(attributes, core=core, fpu=fpu, hard_float=bool(fpu))
            symbols = run(part + "-" + mode + "-symbols", ["arm-none-eabi-nm", "-n", str(elf)], root)
            assert all(" " + symbol + "\n" in symbols for symbol in symbols_required)
            vector = build_dir / "vectors.bin"
            run(part + "-" + mode + "-vectors", ["arm-none-eabi-objcopy", "--dump-section", ".isr_vector=" + str(vector), str(elf)], root)
            NativeIndependentVectors_Validate(vector.read_bytes(), symbols, slots)
            run(part + "-" + mode + "-size", ["arm-none-eabi-size", str(elf)], root)
            # Exact input hashing covers compiler dependency content in the
            # native tree; manifests retain effective include resolution too.
            deps = "\n".join(p.read_text() for p in build_dir.glob("*.d"))
            for entry in manifest["replacements"]:
                if entry["original"].endswith(".h"):
                    effective = str(root / entry["derived"]).replace("\\", "/")
                    assert effective in deps.replace("\\", "/"), "derived configuration header missing from dependencies"
            receipt["builds"].append({"mode": mode, "elf": str(elf),
                "sha256": hashlib.sha256(elf.read_bytes()).hexdigest(), "status": "COMPILED_LINKED_ANALYZER_EXECUTED" if mode == "analyzer" else "COMPILED_LINKED"})
        gate = SCG / "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1"
        (root / "Tools").mkdir()
        (root / "Tools/check_power_of_ten.ps1").write_bytes(gate.read_bytes())
        # The unchanged checker joins linker paths to its project root. Supply
        # a byte-identical projection, not a Windows absolute path that Join-Path
        # would incorrectly concatenate. Actual ARM commands retain the native
        # authoritative linker path and both hashes are checked here.
        gate_linker = "Native/" + build["linker_script"][0]
        (root / gate_linker).parent.mkdir(parents=True, exist_ok=True)
        (root / gate_linker).write_bytes(Path(graph["linker"]).read_bytes())
        assert hashlib.sha256((root / gate_linker).read_bytes()).hexdigest() == plan.files_sha256[build["linker_script"][0]]
        # Checker projection of the actual explicit graph. The imported Make
        # is never executed; this projection is not a runnable Ground project.
        emitted_make = _Makefile_Render(tuple(entry["compiled"] for entry in sources), tuple(graph["assembly"]),
            tuple(map(str, includes)), tuple(value[2:] for value in defines),
            SimpleNamespace(mcu_flags=flags, linker_script=gate_linker), "arm-none-eabi-")
        (root / "Tools/owning-template-Makefile.txt").write_text(emitted_make)
        (root / "Makefile").write_text("# CHECKER PROJECTION ONLY; compiled by the recorded direct commands.\n" + emitted_make)
        emitted = emitted_make.split("power10-check:\n", 1)[1].splitlines()[0].strip()
        # Include complete vendor derivatives in the review scan as well: owned
        # edits inside them must not disappear behind the third-party boundary.
        # This deliberately also exposes retained upstream violations. It is a
        # review over-approximation, not an authorization to enlarge exceptions.
        for entry in manifest["replacements"]:
            if entry["original"].endswith(".c"):
                dest = root / "Generated/UsbVendorReview" / entry["original"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((root / entry["derived"]).read_bytes())
        if baseline:
            for name in ("main.c", "usbd_core.c", "usbd_cdc.c", "usbd_cdc_if.c", "usbd_conf.c"):
                original = plan.owners[name]
                dest = root / "Generated/UsbVendorReview" / original
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((native / original).read_bytes())
        gate_log = run(part + "-power10", shlex.split(emitted), root, expected=None)
        receipt["power10"] = ("FAIL" if "Power of Ten check FAILED" in gate_log else
            "PASS_TEXT_ONLY" if "Power of Ten project text checks passed" in gate_log else "ERROR_SEE_LOG")
        receipt["gate_sha256"] = hashlib.sha256(gate.read_bytes()).hexdigest()
        if {p: hashlib.sha256(b).hexdigest() for p, b in _Project_Read(native).items()} != plan.files_sha256:
            raise ValueError("native input changed during validation")
        receipt["input_preserved"] = True
        (root / 'sdk-function-facts.json').write_text(json.dumps(sdk_facts, indent=2), encoding='utf8')
        (root / "receipt.json").write_text(json.dumps(receipt, indent=2))
        receipts.append(receipt)
    (output / "summary.json").write_text(json.dumps({"baseline": baseline, "receipts": receipts,
        "limits": "Host models plus exact integrated ARM builds only. Vendor callbacks, EP0, physical cancellation, clock/IRQ timing, stack and hardware acceptance NOT PROVEN."}, indent=2))
    return all(not row["warning_logs"] and row["power10"] == "PASS_TEXT_ONLY" for row in receipts)


def _Power10_SourceProvenance(baseline: Path, current: Path, part: str, text: str) -> list[dict]:
    """Locate added/moved failing source lines; text matching is not ownership."""
    tail = text.split('Power of Ten check FAILED', 1)[-1]
    rows = []
    cache = {}
    for filename, number in re.findall(r'(?m)^\s*(?:-\s*)?([^\r\n:]+\.c):(\d+):', tail):
        relative = Path(filename.strip().replace('\\', '/'))
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe reported checker source path')
        old, new = baseline/'native'/part/relative, current/'native'/part/relative
        line = int(number)
        if relative not in cache:
            if old.is_file() and new.is_file():
                a, b = old.read_text().splitlines(), new.read_text().splitlines()
                mapping = {j+offset+1: i+offset+1
                    for tag, i, end_i, j, end_j in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
                    if tag == 'equal' for offset in range(end_i-i)}
                cache[relative] = (mapping, b)
            else:
                cache[relative] = ({}, new.read_text().splitlines() if new.is_file() else [])
        mapping, source = cache[relative]
        rows.append({'source': str(relative), 'line': line, 'baseline_line': mapping.get(line),
            'text': source[line-1] if 0 < line <= len(source) else None,
            'classification': 'VERBATIM_BASELINE_LINE' if line in mapping else 'ADDED_OR_MOVED_REQUIRES_REVIEW',
            'semantic_contracts': 'NOT_PROVEN_BY_LINE_MAPPING'})
    return rows


def UsbEvidence_Compare(baseline: Path, current: Path):
    """Attribute unchanged diagnostics; never convert the failed gate to PASS."""
    previous = json.loads((baseline / 'summary.json').read_text())
    actual = json.loads((current / 'summary.json').read_text())
    if not previous.get('baseline') or actual.get('baseline'):
        raise ValueError('comparison requires an unchanged native baseline and an integrated run')
    rows = []
    def failures(text):
        if 'Power of Ten check FAILED' not in text:
            if 'Power of Ten project text checks passed' in text:
                return []
            raise ValueError('Gate output has no recognized completion status')
        tail = text.split('Power of Ten check FAILED', 1)[1]
        lines = [line.strip() for line in tail.splitlines()[1:] if line.strip()]
        return [re.sub(r'has \d+ non-comment code lines', 'has LENGTH non-comment code lines',
            re.sub(r':\d+:', ':LINE:', line)) for line in lines]
    for now, before in zip(actual['receipts'], previous['receipts'], strict=True):
        assert now['part'] == before['part']
        part = now['part']
        a = json.loads((current/'native'/part/'Generated/usb_transport_source_graph.json').read_text())
        b = json.loads((baseline/'native'/part/'Generated/usb_transport_source_graph.json').read_text())
        assert a['input_hashes'] == b['input_hashes'], 'baseline input revision differs'
        warning_rows = []
        for label in now['warning_logs']:
            prior = baseline / label
            identical = prior.is_file() and prior.read_bytes() == (current/label).read_bytes()
            warning_rows.append({'log': label, 'unchanged_native_baseline_identical': identical,
                'classification': 'EXISTING_VENDOR_DIAGNOSTIC' if identical else 'NEW_OR_CHANGED_REQUIRES_REVIEW'})
        old_text = (baseline/(part+'-power10.log')).read_text()
        new_text = (current/(part+'-power10.log')).read_text()
        old_failures = failures(old_text)
        new_failures = failures(new_text)
        def lengths(text):
            return {name: int(count) for name, count in re.findall(
                r'function (\w+) has (\d+) non-comment code lines', text)}
        old_lengths, new_lengths = lengths(old_text), lengths(new_text)
        old_count, new_count = Counter(old_failures), Counter(new_failures)
        provenance = _Power10_SourceProvenance(baseline, current, part, new_text)
        rows.append({'part': part, 'input_revision_identical': True, 'analyzer': warning_rows,
            'power10_existing_items': list((new_count & old_count).elements()),
            'power10_new_or_changed_items': list((new_count - old_count).elements()),
            'power10_baseline_only_items': list((old_count - new_count).elements()),
            'source_line_provenance': provenance,
            'unmapped_failure_locations': [row for row in provenance if row['classification'] != 'VERBATIM_BASELINE_LINE'],
            'overlong_function_line_changes': [{'function': name, 'baseline_lines': old_lengths[name],
                'current_lines': count, 'acceptance': 'FAIL_REMAINS_NO_EXCEPTION_GRANTED'}
                for name, count in new_lengths.items() if name in old_lengths and count != old_lengths[name]],
            'qualification': 'Text multiplicity is not source ownership: removed old and added new identical directives can cancel. Inspect source_line_provenance/unmapped locations and modified function bodies. Equal lines do not prove semantics; no baseline exception is granted.',
            'acceptance': 'FAIL / CRITICAL_CONTRACTS_NOT_PROVEN'})
    (current/'baseline-attribution.json').write_text(json.dumps({'baseline': str(baseline), 'rows': rows}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--f407-reference", type=Path,
                        help="Separate complete native F407 input; never modifies the original reference or configuration")
    parser.add_argument("--integrated", action="store_true", help="Validate the two source-bound callback integrations")
    parser.add_argument("--baseline", action="store_true", help="Compile/analyze unchanged native inputs and scan the matching original vendor files")
    parser.add_argument("--baseline-evidence", type=Path, help="Attribute diagnostics against a previously executed unchanged native baseline")
    parser.add_argument("--host-only", action="store_true",
                        help="Recheck host/export changes without repeating unchanged target builds")
    args = parser.parse_args()
    if args.integrated and args.baseline:
        parser.error("choose --integrated or --baseline")
    if args.f407_reference is not None and not (args.integrated or args.baseline or args.host_only):
        parser.error("--f407-reference requires --integrated, --baseline or --host-only")
    if not args.integrated and not args.baseline and not args.host_only and args.config is None:
        parser.error("--config is required for the historical native Ground ABI workflow")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf8", PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen",
        SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT=str(args.reference.resolve()),
        SILVERSTAR_NATIVE_BACKEND_ARM="1",
        SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX=str(output / "native-index.jsonl"))
    temporary = output / "tmp"
    temporary.mkdir()
    env.update(TEMP=str(temporary), TMP=str(temporary))
    env.pop("SILVERSTAR_USB_NATIVE_F407_REFERENCE", None)
    if args.f407_reference is not None:
        env["SILVERSTAR_USB_NATIVE_F407_REFERENCE"] = str(args.f407_reference.resolve())
    if args.config is not None:
        env["SILVERSTAR_NATIVE_BACKEND_CONFIG"] = str(args.config.resolve())
    for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "DEPENDENCIES_OUTPUT",
                 "SUNPRO_DEPENDENCIES", "GCC_EXEC_PREFIX", "COMPILER_PATH"):
        env.pop(name, None)
    records = []

    def run(label, command, cwd=REPO, expected=0):
        record = {"label": label, "command": command, "cwd": str(cwd),
                  "started_utc": datetime.now(timezone.utc).isoformat(), "expected_exit": expected}
        log = output / (label + ".log")
        with log.open("w", encoding="utf8") as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=900)
        record.update(exit=result.returncode, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
                      finished_utc=datetime.now(timezone.utc).isoformat())
        records.append(record)
        (output / "commands.json").write_text(json.dumps(records, indent=2), encoding="utf8")
        print(label, result.returncode, flush=True)
        if expected is not None and result.returncode != expected:
            print(log.read_text(encoding="utf8")[-16000:], flush=True)
            raise RuntimeError("validation failed: " + label)
        return log.read_text(encoding="utf8")

    sources = [SCG / p for p in (
        "src/silverstar_fccg/app/usb_transport.py",
        "src/silverstar_fccg/generator/usb_cdc_transport.py", "src/silverstar_fccg/generator/usb_cdc_integration.py",
        "src/silverstar_fccg/hardware/usb_transport_capabilities.py", "src/silverstar_fccg/hardware/usb_transport_profiles.py",
        "src/silverstar_fccg/generator/native_usb_data.py", "src/silverstar_fccg/generator/native_usb_indexed.py",
        "src/silverstar_fccg/generator/native_hal.py", "src/silverstar_fccg/generator/multi_target.py",
        "src/silverstar_fccg/hardware/native_machine_contract.py",
        "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1",
        "tests/test_usb_transport.py", "tests/test_usb_transport_capabilities.py", "tests/test_usb_transport_integration.py",
        "tests/test_ground_usb_cdc_ring.py", "tools/validation/usb_transport_validate.py")]
    snapshot = {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_files": {str(p.relative_to(REPO)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "source": p.read_text(encoding="utf8")} for p in sources},
        "environment": {k: env[k] for k in env if k.startswith(("SILVERSTAR_NATIVE_", "SILVERSTAR_USB_"))},
        "limits": "Integrated native callbacks; complete critical contracts and physical cancellation NOT PROVEN." if args.integrated else
                  "Unchanged selected native input; no transport hooks added. Hardware, full critical contracts and stack NOT PROVEN." if args.baseline else
                  "Kit ABI link only; native callbacks still belong to existing private Ground candidate. "
                  "New kit has no automatically installed hooks. Hardware, full critical contracts and stack NOT PROVEN."}
    (output / "source-snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf8")
    for tool in (sys.executable, "gcc", "arm-none-eabi-gcc"):
        run(Path(tool).stem + "-version", [tool, "--version"])
    runner = SCG / "docs/evidence/native_usb_local_merge_20261010/runners/daily_backend_pytest.py"
    run("host-tests", [sys.executable, "-B", str(runner),
        str(SCG / "tests/test_usb_transport.py"), str(SCG / "tests/test_ground_usb_cdc_ring.py"),
        str(SCG / "tests/test_usb_transport_capabilities.py"), str(SCG / "tests/test_usb_transport_integration.py"),
        "-p", "no:cacheprovider", "--basetemp=" + str(output / "host"), "-q"])
    if args.host_only:
        print("Host/export checks complete; no target build requested in this run", flush=True)
        return
    if args.integrated or args.baseline:
        clean = Integrated_Validate(args.reference.resolve(), output, run, baseline=args.baseline,
            f407_reference=args.f407_reference.resolve() if args.f407_reference is not None else None)
        if args.baseline_evidence is not None:
            UsbEvidence_Compare(args.baseline_evidence.resolve(), output)
        inventory = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in output.rglob("*") if p.is_file()}
        (output / "inventory.json").write_text(json.dumps(inventory, indent=2))
        print("Integrated evidence collected; critical contracts and hardware NOT PROVEN; clean gates=" + str(clean), flush=True)
        if not clean:
            raise SystemExit(1)
        return
    run("native-tests", [sys.executable, "-B", str(runner),
        str(SCG / "tests/test_native_ground_backend.py"), "-k", "real_backend_bound_build_receipt",
        "-p", "no:cacheprovider", "--basetemp=" + str(output / "native"), "-q"])

    from silverstar_fccg.generator.usb_cdc_transport import UsbCdcTransport_Render
    from silverstar_fccg.hardware.native_machine_contract import NativeArmAttributes_Validate, NativeIndependentVectors_Validate
    for row in (json.loads(line) for line in (output / "native-index.jsonl").read_text().splitlines()):
        root = Path(row["output"])
        part = row["part"]
        receipt = json.loads((root / "receipt.json").read_text())
        graph = receipt["graph"]
        assert receipt["status"] == "NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED"
        assert not receipt["warning_diagnostics"]
        # Separate additive ABI graph: original Ground hooks and source graph are
        # unchanged. Added files stay in Generated so the unmodified gate sees them.
        generated = []
        for relative, body in UsbCdcTransport_Render(indexed=part == "STM32F407VET6").items():
            dest = root / "Generated/UsbTransport" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            if relative.endswith(".c"):
                generated.append(dest.relative_to(root).as_posix())
        flags = [*graph["mcu_flags"], *("-I" + p for p in graph["include_dirs"]),
                 "-IGenerated/UsbTransport/Inc", *("-D" + p for p in graph["defines"])]
        strict = ["-std=c11", "-Os", "-ffunction-sections", "-fdata-sections", "-fstack-usage",
            "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-Wconversion", "-Wsign-conversion",
            "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion", "-Wcast-align",
            "-Wcast-qual", "-Wstrict-prototypes", "-Wmissing-prototypes", "-Wswitch-enum", "-Wvla"]
        addon = {**graph, "sources": graph["sources"] + generated,
            "include_dirs": graph["include_dirs"] + ["Generated/UsbTransport/Inc"],
            "required_link_symbols": graph["required_link_symbols"] + ["UsbCdc_Service", "UsbCdc_Configure",
                "UsbCdc_Quiesced", "UsbCdc_Receive", "UsbCdc_Read", "UsbCdc_Write", "UsbCdc_LinkDown", "UsbCdc_SessionGet"],
            "scope": "ABI_ONLY_NOT_HOOKED_TO_NATIVE_CALLBACKS"}
        (root / "Generated/usb_transport_abi_graph.json").write_text(json.dumps(addon, indent=2))
        for build_dir, analyzer in (("build", False), ("build/analysis", True)):
            objects = [(Path(build_dir) / Path(p).with_suffix(".o")).as_posix()
                       for p in graph["sources"] + graph["asm_sources"]]
            for source in generated:
                obj = (Path(build_dir) / Path(source).with_suffix(".o")).as_posix()
                (root / obj).parent.mkdir(parents=True, exist_ok=True)
                command = ["arm-none-eabi-gcc", *flags, *strict]
                if analyzer:
                    command.append("-fanalyzer")
                command += ["-MD", "-MF", str(Path(obj).with_suffix(".d")), "-c", source, "-o", obj]
                run(part + ("-analyzer-" if analyzer else "-compile-") + Path(source).stem, command, root)
                objects.append(obj)
            name = part + ("-analyzer" if analyzer else "-normal")
            elf = build_dir + "/usb-transport-abi.elf"
            command = ["arm-none-eabi-gcc", *objects, *graph["mcu_flags"],
                *("-Wl,-u," + symbol for symbol in addon["required_link_symbols"]),
                "-Wl,--gc-sections,-Map=" + build_dir + "/usb-transport-abi.map",
                "-T" + graph["linker_script"], "-specs=nano.specs", "-lc", "-lm", "-lnosys", "-o", elf]
            run(name + "-link", command, root)
            attributes = run(name + "-attributes", ["arm-none-eabi-readelf", "-A", elf], root)
            NativeArmAttributes_Validate(attributes, core=receipt["facts"]["core"],
                fpu=receipt["facts"]["fpu"], hard_float="-mfloat-abi=hard" in graph["mcu_flags"])
            symbols = run(name + "-symbols", ["arm-none-eabi-nm", "-n", elf], root)
            assert all(" " + symbol + "\n" in symbols for symbol in addon["required_link_symbols"])
            vectors = build_dir + "/usb-transport-abi-vectors.bin"
            run(name + "-vectors", ["arm-none-eabi-objcopy", "--dump-section", ".isr_vector=" + vectors, elf], root)
            NativeIndependentVectors_Validate((root / vectors).read_bytes(), symbols,
                                             receipt["contract"]["independent_irq_slots"])
            run(name + "-size", ["arm-none-eabi-size", elf], root)
        for mode, command in (
            ("architecture", [sys.executable, "Tools/check_native_ground.py"]),
            ("host", [sys.executable, "Tools/check_native_ground.py", "host", "--host-cc", "gcc"]),
            ("artifact", [sys.executable, "Tools/check_native_ground.py", "artifact", "--prefix", "arm-none-eabi-"]),
        ):
            run(part + "-" + mode, command, root)
        make = (root / "Makefile").read_text()
        emitted = make.split("power10-check:\n", 1)[1].splitlines()[0].strip()
        run(part + "-power10", shlex.split(emitted), root)
        # Full retained source/license hashes and linked .su/map/ELF are inventoried.
        inventory = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.rglob("*") if p.is_file()}
        (output / (part + "-inventory.json")).write_text(json.dumps(inventory, indent=2))
    print("Software checks complete; hardware and full critical-contract acceptance NOT PROVEN", flush=True)


if __name__ == "__main__":
    main()
