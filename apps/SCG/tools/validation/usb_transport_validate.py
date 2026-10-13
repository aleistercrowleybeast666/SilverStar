"""Reproducible host/native ABI evidence for the experimental CDC kit.

Never accesses serial/DAP, executes an imported Makefile, or installs firmware.
All outputs go to one NEW task directory. No cleanup of existing data occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

REPO = Path(__file__).resolve().parents[4]
SCG = REPO / "apps/SCG"
sys.path.insert(0, str(SCG / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--host-only", action="store_true",
                        help="Recheck host/export changes without repeating unchanged target builds")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf8", PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen",
        SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT=str(args.reference.resolve()),
        SILVERSTAR_NATIVE_BACKEND_CONFIG=str(args.config.resolve()),
        SILVERSTAR_NATIVE_BACKEND_ARM="1",
        SILVERSTAR_NATIVE_BACKEND_BUILD_INDEX=str(output / "native-index.jsonl"))
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
        if result.returncode != expected:
            print(log.read_text(encoding="utf8")[-16000:], flush=True)
            raise RuntimeError("validation failed: " + label)
        return log.read_text(encoding="utf8")

    sources = [SCG / p for p in (
        "src/silverstar_fccg/app/usb_transport.py",
        "src/silverstar_fccg/generator/usb_cdc_transport.py",
        "tests/test_usb_transport.py", "tools/validation/usb_transport_validate.py")]
    snapshot = {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_files": {str(p.relative_to(REPO)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "source": p.read_text(encoding="utf8")} for p in sources},
        "environment": {k: env[k] for k in env if k.startswith("SILVERSTAR_NATIVE_")},
        "limits": "Kit ABI link only; native callbacks still belong to existing private Ground candidate. "
                  "New kit has no automatically installed hooks. Hardware, full critical contracts and stack NOT PROVEN."}
    (output / "source-snapshot.json").write_text(json.dumps(snapshot, indent=2), encoding="utf8")
    for tool in (sys.executable, "gcc", "arm-none-eabi-gcc"):
        run(Path(tool).stem + "-version", [tool, "--version"])
    runner = SCG / "docs/evidence/native_usb_local_merge_20261010/runners/daily_backend_pytest.py"
    run("host-tests", [sys.executable, "-B", str(runner),
        str(SCG / "tests/test_usb_transport.py"), str(SCG / "tests/test_ground_usb_cdc_ring.py"),
        "-p", "no:cacheprovider", "--basetemp=" + str(output / "host"), "-q"])
    if args.host_only:
        print("Host/export checks complete; no target build requested in this run", flush=True)
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
