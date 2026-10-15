"""Bounded direct ARM build of an inspected USB graph; no native scripts run."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from silverstar_fccg.core.task import TaskContext
from silverstar_fccg.generator.native_usb_graph import NativeUsbDigest_Get
from silverstar_fccg.hardware.native_machine_contract import (
    NativeArmAttributes_Validate,
    NativeIndependentVectors_Validate,
)

_STRICT = ["-Wall", "-Wextra", "-Wpedantic", "-Werror", "-Wconversion", "-Wsign-conversion",
    "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion", "-Wcast-align", "-Wcast-qual",
    "-Wstrict-prototypes", "-Wmissing-prototypes", "-Wswitch-enum", "-Wvla"]
_VENDOR = ["-Wall", "-Werror=implicit-function-declaration", "-Werror=incompatible-pointer-types",
    "-Werror=return-type", "-Wvla", "-Werror=vla"]
_SYMBOLS = ["UsbCdc_Service", "UsbCdc_Configure", "UsbCdc_Quiesced", "UsbCdc_Receive",
    "UsbCdc_Read", "UsbCdc_Write", "UsbCdc_LinkDown", "UsbCdc_SessionGet",
    "UsbCdcRetire_Endpoint", "UsbCdcRetire_ConfigurationCheck"]


def _Process_Stop(process: subprocess.Popen) -> None:
    """Stop the owned compiler tree, including cc1/as/ld children."""
    if os.name == "nt":
        try:
            result = subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if result.returncode:
            detail = (result.stdout + result.stderr).decode(errors="replace")[-2048:]
            raise ValueError("Compiler tree termination was not confirmed: " + detail)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


def NativeUsbCompiler_Resolve(selected: str) -> Path:
    resolved = shutil.which(selected or "arm-none-eabi-gcc")
    if not resolved:
        raise ValueError("ARM GCC is unavailable; select its executable in build configuration")
    path = Path(resolved).resolve()
    if path.name not in {"arm-none-eabi-gcc", "arm-none-eabi-gcc.exe"}:
        raise ValueError("Native USB workflow requires the ARM GCC executable")
    return path


def _Command_Run(command: list[str], directory: Path, context: TaskContext, rows: list) -> str:
    context.Cancel_RaiseIfRequested()
    log = directory / f"{len(rows):03d}.log"
    row = {"argv": command, "cwd": str(directory), "log": log.name, "exit_code": None}
    rows.append(row)
    context.Line_Report(f"> {Path(command[0]).name}: {Path(command[-1]).name}")
    started = time.monotonic()
    environment = {key: value for key, value in os.environ.items() if key.upper() not in {
        "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "LIBRARY_PATH",
        "COMPILER_PATH", "GCC_EXEC_PREFIX"}}
    environment.update(LC_ALL="C", LANG="C")
    with log.open("xb") as stream:
        process = subprocess.Popen(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT,
            shell=False, env=environment,
            start_new_session=os.name != "nt",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                context.Cancel_RaiseIfRequested()
                if time.monotonic() - started > 120 or log.stat().st_size > 8 * 1024 * 1024:
                    raise ValueError("Native USB compiler exceeded its time/output bound")
                time.sleep(0.05)
            row["exit_code"] = process.returncode
        finally:
            if process.poll() is None:
                _Process_Stop(process)
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if log.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Native USB compiler output exceeded 8 MiB")
    output = log.read_text(encoding="utf-8", errors="replace")
    row["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
    row["warnings"] = bool(re.search(r"\bwarning:", output))
    if row["exit_code"] != 0:
        raise ValueError(f"Native USB compiler failed ({row['exit_code']}), see {log}")
    if output and command[-1] == "--version":
        context.Line_Report(output[-8000:])
    elif row["warnings"]:
        context.Line_Report("Compiler diagnostics retained: " + str(log))
    return output


def NativeUsbBuild_Run(graph: dict, output: Path, compiler: Path, context: TaskContext,
                       *, analyzer: bool = False, verify_inputs=None) -> tuple[Path, dict]:
    """Retain failures/cancellation; a receipt never certifies firmware acceptance."""
    directory = output / ("analysis-" if analyzer else "compile-")
    directory = directory.with_name(directory.name + uuid4().hex)
    directory.mkdir()
    receipt = {"format": "silverstar.usb.compile-receipt", "version": 1,
        "status": "INCOMPLETE", "analyzer": analyzer, "commands": [],
        "graph_digest": NativeUsbDigest_Get(graph),
        "source_sha256": graph["source_sha256"], "critical_contracts": "NOT_PROVEN",
        "power10": "NOT_RUN_BY_THIS_BUILD", "stack_wcet": "NOT_PROVEN", "hardware": "NOT_TESTED"}
    rows = receipt["commands"]
    started = time.monotonic()
    def run(args):
        if time.monotonic() - started > 1800:
            raise ValueError("Native USB build exceeded its total time bound")
        return _Command_Run(list(map(str, args)), directory, context, rows)
    try:
        receipt["compiler"] = {"path": str(compiler), "sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
            "version": run([compiler, "--version"])}
        flags = graph["mcu_flags"]
        objects = []
        sources = graph["sources"]
        receipt["effective_headers"] = {}
        native = Path(graph["native_root"])
        kit = json.loads((output / "kit-sha256.json").read_text(encoding="utf8"))
        if not 1 <= len(sources) <= 512:
            raise ValueError("Native USB compile inventory exceeds its bound")
        for index, entry in enumerate(sources):
            context.Progress_Report(index / (len(sources) + 6), "status.task_running")
            obj = directory / f"{index:03d}.o"
            diagnostics = run([compiler, *flags, "-std=c11", "-Os", "-ffunction-sections", "-fdata-sections", "-fstack-usage", "-H",
                *("-I" + p for p in graph["includes"]), *graph["defines"],
                *(_STRICT if entry["policy"] == "first_party" else _VENDOR),
                *(["-fanalyzer"] if analyzer else []), "-MD", "-MF", obj.with_suffix(".d"),
                "-c", entry["compiled"], "-o", obj])
            for name in re.findall(r"(?m)^\.+ (.+?)\r?$", diagnostics):
                header = Path(name).resolve()
                digest = hashlib.sha256(header.read_bytes()).hexdigest()
                if header.is_relative_to(native):
                    expected = graph["native_files_sha256"].get(header.relative_to(native).as_posix())
                elif header.is_relative_to(output):
                    expected = kit.get(header.relative_to(output).as_posix())
                elif header.is_relative_to(compiler.parent.parent):
                    expected = digest  # Toolchain headers are recorded, not native source authority.
                else:
                    raise ValueError("Compiler header escapes the native/kit/toolchain graph: " + str(header))
                if digest != expected:
                    raise ValueError("Compiler header was not present in the inspected inventory: " + str(header))
                receipt["effective_headers"][str(header)] = digest
            objects.append(obj)
        for index, source in enumerate(graph["assembly"]):
            obj = directory / f"asm-{index}.o"
            run([compiler, *flags, *graph["defines"], "-x", "assembler-with-cpp", "-c", source, "-o", obj])
            objects.append(obj)
        elf = directory / "usb-native.elf"
        run([compiler, *objects, *flags, *("-Wl,-u," + s for s in _SYMBOLS),
            "-Wl,--gc-sections,-Map=" + str(elf.with_suffix(".map")), "-T" + graph["linker"],
            "-specs=nano.specs", "-lc", "-lm", "-lnosys", "-o", elf])
        def tool(name):
            return compiler.with_name(compiler.name.replace("gcc", name))
        attributes = run([tool("readelf"), "-A", elf])
        NativeArmAttributes_Validate(attributes, core=graph["core"], fpu=graph["fpu"], hard_float=bool(graph["fpu"]))
        symbols = run([tool("nm"), "-n", elf])
        if any(" " + symbol + "\n" not in symbols for symbol in _SYMBOLS):
            raise ValueError("Native USB linked transport symbol is missing")
        vectors = directory / "vectors.bin"
        run([tool("objcopy"), "--dump-section", ".isr_vector=" + str(vectors), elf])
        NativeIndependentVectors_Validate(vectors.read_bytes(), symbols, graph["independent_irq_slots"])
        run([tool("size"), elf])
        dependencies = "\n".join(p.read_text(encoding="utf8") for p in directory.glob("*.d"))
        dependencies = dependencies.replace("\\\n", "").replace("\\ ", " ").replace("\\", "/").casefold()
        for old, derived in graph["replacements"].items():
            if old.endswith(".h") and derived.replace("\\", "/").casefold() not in dependencies:
                raise ValueError("Derived configuration header is absent from compiler dependencies")
        receipt["libraries"] = {}
        for name in ("libc_nano.a", "libm.a", "libnosys.a", "libgcc.a"):
            path = Path(run([compiler, *flags, "-print-file-name=" + name]).strip()).resolve()
            receipt["libraries"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        if verify_inputs is not None:
            verify_inputs()
        receipt["elf"] = str(elf)
        receipt["elf_sha256"] = hashlib.sha256(elf.read_bytes()).hexdigest()
        receipt["status"] = "COMPILED_WITH_DIAGNOSTICS" if any(r.get("warnings") for r in rows) else "COMPILED_LINKED"
    except Exception as error:
        receipt["status"] = "CANCELLED" if context.cancelled else "FAILED"
        receipt["error"] = str(error)
        raise
    finally:
        (directory / "validation-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf8")
    return directory / "validation-receipt.json", receipt
