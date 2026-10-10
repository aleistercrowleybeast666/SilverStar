"""Linked interrupt identity and complete compiled dependency closure gates."""
from pathlib import Path
import os
import re
import shutil
import struct
import subprocess
import json


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


def _MakeWords_Get(text: str) -> tuple[str, ...]:
    return tuple(token.replace("\\ ", " ").replace("\\#", "#").replace("\\\\", "\\").replace("$$", "$")
                 for token in re.findall(r"(?:\\.|[^\s])+", text))


def _BuildFile_Get(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or relative.parts[0] != "build" or ".." in relative.parts:
        raise ValueError("invalid build evidence path: " + str(relative))
    candidate = Path(os.path.abspath(root / relative))
    if not candidate.is_relative_to(root) or candidate.resolve() != candidate:
        raise ValueError("build evidence path contains an alias or escapes target: " + str(relative))
    return candidate


def AssemblerSource_Prepare(root: Path, graph: dict, source: str, build_dir: str) -> None:
    """Qualify GCC's basename-only source label before GAS records dependencies.

    GAS includes .file labels in --MD output, although it does not read them.
    Normalize only GCC's first source label; never discard a GAS dependency.
    """
    if build_dir not in {"build", "build/analysis"} or source not in graph["sources"]:
        raise ValueError("assembler input is not a declared C compilation")
    root = root.resolve()
    assembly = _BuildFile_Get(root, Path(build_dir) / Path(source).with_suffix(".s"))
    text = assembly.read_text(encoding="utf8")
    label = re.search(r'(?m)^\s*\.file\s+"([^"\r\n]+)"\s*$', text)
    if label is None or label.group(1) != Path(source).name:
        raise ValueError("unrecognized GCC assembler source label: " + source)
    # A qualified label binds to the already declared original source, including
    # in subdirectories. Later labels from inline assembly remain checked.
    text = text[:label.start()] + "\t.file " + json.dumps(source) + text[label.end():]
    assembly.write_text(text, encoding="utf8", newline="\n")


def _DependencyPaths_Get(root: Path, manifest: Path, expected_object: Path) -> tuple[Path, ...]:
    if not manifest.is_file():
        raise ValueError("compiled dependency evidence missing: " + str(manifest))
    logical = manifest.read_text(encoding="utf8").replace("\\\n", " ")
    rules = re.findall(r"(?m)^([^\n]*\.o):[ \t]*([^\n]*)$", logical)
    if len(rules) != 1:
        raise ValueError("unrecognized compiled dependency list: " + str(manifest))
    targets = _MakeWords_Get(rules[0][0])
    if len(targets) != 1 or Path(os.path.abspath(root / targets[0])) != expected_object:
        raise ValueError("dependency target differs from declared object: " + str(manifest))
    return tuple(root / spelling for spelling in _MakeWords_Get(rules[0][1]))


def _DependencyPath_Validate(root: Path, candidate: Path, approved: tuple[Path, ...],
                             intermediate: Path | None) -> Path:
    path = candidate.resolve()
    lexical = Path(os.path.abspath(candidate))
    escaped_alias = lexical.is_relative_to(root) and not path.is_relative_to(root)
    if escaped_alias or not path.is_file() or not (
            path.is_relative_to(root) or any(path.is_relative_to(item) for item in approved)):
        raise ValueError("compiled dependency escaped copied target: " + str(candidate))
    # There is exactly one compiler-produced assembler input per object. No
    # other build output, system Temp directory, or aliased spelling is exempt.
    if path.is_relative_to(root / "build") and (path != intermediate or lexical != intermediate):
        raise ValueError("unexpected build-output dependency: " + str(candidate))
    return path


def _ObjectDependencies_Get(root: Path, source: str, approved: tuple[Path, ...],
                            build_dir: str) -> tuple[Path, tuple[Path, ...]]:
    relative = Path(build_dir) / Path(source).with_suffix(".o")
    obj = _BuildFile_Get(root, relative)
    assembly = _BuildFile_Get(root, relative.with_suffix(".s"))
    cpp = _DependencyPaths_Get(root, _BuildFile_Get(root, relative.with_suffix(".d")), obj)
    paths = [_DependencyPath_Validate(root, path, approved, None) for path in cpp]
    if (root / source).resolve() not in paths:
        raise ValueError("CPP dependencies omit the declared source: " + source)
    gas = _DependencyPaths_Get(root, _BuildFile_Get(root, relative.with_suffix(".gas.d")), obj)
    gas_paths = [_DependencyPath_Validate(root, path, approved, assembly) for path in gas]
    if assembly not in gas_paths:
        raise ValueError("GAS dependencies omit the exact saved assembler input: " + source)
    dependencies = tuple(dict.fromkeys([*paths, *gas_paths]))
    if not obj.is_file() or any(path.stat().st_mtime_ns > obj.stat().st_mtime_ns for path in dependencies):
        raise ValueError("object is absent or older than its compiled dependencies: " + source)
    return obj, dependencies


def _MakePath_Render(root: Path, path: Path) -> str:
    value = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    # Do not expose raw GAS output to Make expansion. These uncommon filename
    # forms are outside the first-profile build contract, even if GAS reads them.
    if any(char in value for char in "\t\r\n#$;|*?[]%") or ":" in value[2:]:
        raise ValueError("dependency filename cannot be represented safely in Make: " + value)
    return value.replace(" ", "\\ ")


def DependencyClosure_Validate(root: Path, graph: dict, compiler: str | None = None,
                               *, build_dir: str = "build", source: str | None = None) -> None:
    if build_dir not in {"build", "build/analysis"}:
        raise ValueError("unsupported dependency build directory")
    root = root.resolve()
    approved = _ToolchainHeaderRoots_Get(compiler, root) if compiler else ()
    sources = (*graph["sources"], *graph.get("asm_sources", ()))
    if any(not item or "\\" in item or ":" in item or
           any(part in {"", ".", ".."} for part in item.split("/")) for item in sources):
        raise ValueError("declared dependency source is not a safe relative path")
    objects = [str(Path(item).with_suffix(".o")).casefold() for item in sources]
    if len(objects) != len(set(objects)):
        raise ValueError("declared C/ASM sources collide on an object path")
    if source is not None and source not in sources:
        raise ValueError("dependency source is not in the declared graph: " + source)
    for item in ((source,) if source is not None else sources):
        obj, dependencies = _ObjectDependencies_Get(root, item, approved, build_dir)
        names = [_MakePath_Render(root, path) for path in dependencies]
        if source is not None:
            # Publish only validated, safely rendered prerequisites. Include
            # phony input rules so deletion triggers recompilation and failure.
            text = _MakePath_Render(root, obj) + ": " + " ".join(names) + "\n"
            text += "".join(name + ":\n" for name in names)
            output = _BuildFile_Get(root, obj.relative_to(root).with_suffix(".deps.mk"))
            temporary = _BuildFile_Get(root, output.relative_to(root).with_suffix(".tmp"))
            temporary.write_text(text, encoding="utf8", newline="\n")
            temporary.replace(output)
    print("PASS paired CPP/GAS dependencies, exact saved assembler inputs and selected compiler defaults: " + build_dir)


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
