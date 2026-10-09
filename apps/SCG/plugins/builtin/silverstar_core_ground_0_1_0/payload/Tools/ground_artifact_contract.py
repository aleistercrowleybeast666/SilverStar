"""Linked interrupt identity and complete compiled dependency closure gates."""
from pathlib import Path
import os
import re
import shutil
import struct
import subprocess


def InterruptVectors_Validate(root: Path, graph: dict, symbols: str, vector: bytes) -> None:
    if not graph["required_irq_handlers"]:
        print("Legacy Ground IRQ contract: NOT PROVEN (no complete-import IRQ inventory)")
        return
    startup = (root / graph["asm_sources"][0]).read_text(encoding="utf-8-sig")
    if "g_pfnVectors:" not in startup:
        raise ValueError("unsupported startup vector declaration")
    declarations = re.findall(r"(?m)^\s*\.word\s+(\w+)\s*(?:/\*.*)?$", startup.split("g_pfnVectors:", 1)[1])
    entries = {name: (int(address, 16), kind) for address, kind, name in
               re.findall(r"(?m)^([0-9a-fA-F]+)\s+(\w)\s+(\w+)$", symbols)}
    for handler in graph["required_irq_handlers"]:
        if handler not in entries or entries[handler][1] != "T":
            raise ValueError("required IRQ handler is missing or weak: " + handler)
        if declarations.count(handler) != 1:
            raise ValueError("required IRQ has no unique startup vector: " + handler)
        offset = declarations.index(handler) * 4
        if offset + 4 > len(vector) or struct.unpack_from("<I", vector, offset)[0] != (entries[handler][0] | 1):
            raise ValueError("linked IRQ vector does not select its strong handler: " + handler)
    print("PASS strong linked IRQ handlers and actual vector entries")


def _ToolchainHeaderRoots_Get(compiler: str, root: Path) -> tuple[Path, ...]:
    executable = shutil.which(compiler)
    if executable is None:
        raise ValueError("dependency compiler is unavailable: " + compiler)
    installation = Path(executable).resolve().parent.parent
    environment = os.environ.copy()
    for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH",
                 "GCC_EXEC_PREFIX", "COMPILER_PATH"):
        environment.pop(name, None)
    result = subprocess.run([executable, "-E", "-v", "-x", "c", "-"], input="", cwd=root,
                            env=environment, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60)
    match = re.search(r'#include <\.\.\.> search starts here:\s*\n(.*?)End of search list\.',
                      result.stderr, re.S)
    if result.returncode or match is None:
        raise ValueError("cannot establish selected compiler default header roots")
    roots = tuple(Path(line.strip()).resolve() for line in match[1].splitlines() if line.strip())
    if not roots or any(not path.is_dir() or not path.is_relative_to(installation) for path in roots):
        raise ValueError("compiler default header root escapes its installation")
    return roots


def DependencyClosure_Validate(root: Path, graph: dict, compiler: str | None = None) -> None:
    approved = _ToolchainHeaderRoots_Get(compiler, root) if compiler else ()
    canonical_root = root.resolve()
    for source in (*graph["sources"], *graph.get("asm_sources", ())):
        dependency = root / "build" / Path(source).with_suffix(".d")
        if not dependency.is_file():
            raise ValueError("compiled dependency evidence missing: " + source)
        logical = dependency.read_text(encoding="utf8").replace("\\\n", " ")
        match = re.search(r"(?m)^[^\n]*\.o:\s*([^\n]+)", logical)
        if match is None:
            raise ValueError("unrecognized compiled dependency list: " + source)
        for token in re.findall(r"(?:\\.|[^\s])+", match[1]):
            spelling = token.replace("\\ ", " ").replace("\\#", "#").replace("\\\\", "\\")
            candidate = root / spelling
            path = candidate.resolve()
            # Project aliases must stay inside the copied tree even when their
            # resolved destination happens to be an approved compiler header.
            lexical = Path(os.path.abspath(candidate))
            escaped_alias = lexical.is_relative_to(canonical_root) and not path.is_relative_to(canonical_root)
            if escaped_alias or not path.is_file() or not (
                    path.is_relative_to(canonical_root) or any(path.is_relative_to(item) for item in approved)):
                raise ValueError("compiled dependency escaped copied target: " + token)
    print("PASS actual compiled C/ASM dependencies including system headers; copied target or selected compiler defaults")


def EffectiveMacros_Validate(root: Path, graph: dict, compiler: str) -> None:
    if not graph.get("complete_cube_import"):
        print("Legacy Ground effective clock macro contract: NOT PROVEN")
        return
    expected = next((name for name in ("STM32F103xB", "STM32F407xx") if name in graph["defines"]), None)
    if expected is None:
        raise ValueError("complete Ground import has no supported MCU macro")
    family = "stm32f1xx" if expected == "STM32F103xB" else "stm32f4xx"
    main = next(source for source in graph["sources"] if source.endswith("/main.c"))
    rcc = next(source for source in graph["sources"] if source.endswith("/" + family + "_hal_rcc.c"))
    config = (root / main).parents[1] / "Inc" / (family + "_hal_conf.h")
    values = re.findall(r"(?m)^\s*#\s*define\s+HSE_VALUE\s+\(?([0-9]+)[uU]?\)?", config.read_text(encoding="utf-8-sig"))
    if len(values) != 1:
        raise ValueError("complete Ground import needs one literal HSE macro contract")
    flags = [*graph["mcu_flags"], *["-I" + path for path in graph["include_dirs"]], *["-D" + value for value in graph["defines"]]]
    for source in (main, rcc):
        result = subprocess.run([compiler, "-std=c11", "-E", "-dM", *flags, source], cwd=root,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        # Never print the complete macro dump: unrelated project macros can
        # contain private data. Only audited MCU/HSE values are reported.
        print("PREPROCESS_CONTRACT source=" + source + " exit=" + str(result.returncode))
        if result.returncode:
            raise ValueError("effective macro preprocessing failed: " + source)
        actual_hse = re.findall(r"(?m)^#define HSE_VALUE\s+\(?([0-9]+)[uU]?\)?\s*$", result.stdout)
        actual_mcu = re.findall(r"(?m)^#define (STM32F[0-9]{3}[A-Za-z0-9]+)\s+([^\r\n]*)$", result.stdout)
        if actual_hse != values or actual_mcu != [(expected, "1")]:
            raise ValueError("effective MCU/HSE macros contradict the imported clock contract: " + source)
        print("PASS effective macros " + expected + " HSE_VALUE=" + values[0] + " " + source)
