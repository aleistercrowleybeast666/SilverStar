"""Same-compiler differential against the exact pre-optimization source commit.

No historical golden is rewritten. Every source/header/command is inventoried;
the C harness compares full states and covariances in memory, avoiding giant
100,000-step trace files. Host timing is not an MCU timing measurement.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/SCG"
FIXTURES = APP / "tests/fixtures"
BASELINE = "57b78fbb56d64eb09a76c8b7e961aa4027a6eb70"
BUILTIN = APP / "plugins/builtin"
SOURCES = {
    "ins": BUILTIN / "silverstar_algorithm_ins_coning2_sculling2/payload/Algorithm/INS/Coning2Sculling2",
    "eskf": BUILTIN / "silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15",
    "kf": BUILTIN / "silverstar_algorithm_estimator_kf6/payload/Algorithm/Estimator/KF6",
}
NAMES = {"ins": "ins_mechanization", "eskf": "navigation_eskf", "kf": "navigation_kf"}


def _run(command: list[str], directory: Path, name: str, timeout: int = 180):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    (directory / f"{name}.json").write_text(json.dumps({
        "command": command, "cwd": str(ROOT), "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
    }, indent=2), encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module", params=("-O0", "-O2", "-O2-default-contract"))
def perf_executable(request, tmp_path_factory):
    compiler = shutil.which("gcc")
    assert compiler, "Real Host GCC is required"
    directory = tmp_path_factory.mktemp("navigation-perf" + request.param)
    headers = []
    baseline_sources = {}
    manifest = {"baseline_commit": BASELINE, "files": {}, "optimization": request.param}
    for kind, folder in SOURCES.items():
        name = NAMES[kind]
        source = folder / f"Src/{name}.c"
        old = subprocess.check_output(["git", "show", f"{BASELINE}:{source.relative_to(ROOT).as_posix()}"], cwd=ROOT)
        baseline_sources[kind] = directory / (name + ".c")
        baseline_sources[kind].write_bytes(old)
        header = folder / f"Inc/{name}.h"
        declarations = re.findall(r"(?:void|uint8_t|Navigation\w+Result|InsInertialUpdateResult)\s+([A-Z]\w+)\s*\([^;{}]+\);", header.read_text(encoding="utf-8"))
        headers.append((header, declarations))
        for path in (source, header):
            manifest["files"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["files"][f"baseline/{name}.c"] = hashlib.sha256(old).hexdigest()
    declarations = []
    for header, names in headers:
        content = header.read_text(encoding="utf-8")
        for name in names:
            match = re.search(r"(?:void|uint8_t|Navigation\w+Result|InsInertialUpdateResult)\s+" + name + r"\s*\([^;{}]+\);", content)
            assert match
            declarations.append(match.group().replace(name, "Baseline_" + name, 1))
    (directory / "baseline_api.h").write_text("\n".join(declarations), encoding="utf-8")
    common = BUILTIN / "silverstar_algorithm_common/payload/Algorithm/Common"
    core = BUILTIN / "silverstar_core_0_1_0/payload/Common"
    includes = [folder / "Inc" for folder in SOURCES.values()]
    includes += [common / "Inc", core / "Inc", FIXTURES / "navigation_perf_config", directory]
    optimization = "-O2" if request.param == "-O2-default-contract" else request.param
    flags = [compiler, "-std=c11", optimization, "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-fno-fast-math"]
    if request.param != "-O2-default-contract":
        flags.append("-ffp-contract=off")
    flags += ["-I" + str(p) for p in includes]
    objects = []
    for version in ("baseline", "current"):
        for (kind, folder), (_, names) in zip(SOURCES.items(), headers, strict=True):
            source = baseline_sources[kind] if version == "baseline" else folder / f"Src/{NAMES[kind]}.c"
            renamed = list(names)
            extra = []
            if kind == "eskf":
                extra = ['-DNAV_PERF_SOURCE="' + source.as_posix() + '"']
                source = FIXTURES / "navigation_perf_eskf_bridge.c"
                renamed += ["NavPerf_EskfReset", "NavPerf_EskfTransition", "NavPerf_EskfNoise"]
            if version == "baseline":
                extra += [f"-D{name}=Baseline_{name}" for name in renamed]
            obj = directory / f"{version}_{kind}.o"
            _run(flags + extra + ["-c", str(source), "-o", str(obj)], directory, f"compile_{version}_{kind}")
            objects.append(obj)
    executable = directory / "navigation_perf.exe"
    command = flags + [str(x) for x in objects] + [str(common / "Src/attitude_frame.c"),
        str(core / "Src/silverstar_assert.c"), str(FIXTURES / "navigation_perf_trace.c"), "-lm", "-o", str(executable)]
    _run(command, directory, "link")
    manifest["compiler_version"] = _run([compiler, "--version"], directory, "compiler").stdout
    for p in FIXTURES.glob("navigation_perf*"):
        paths = p.rglob("*") if p.is_dir() else (p,)
        for f in paths:
            if f.is_file():
                manifest["files"][str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return executable


@pytest.mark.parametrize("scenario", ("dense", "long", "faults", "ins", "kf", "benchmark"))
def test_current_baseline_exact_equivalence(perf_executable, scenario):
    result = _run([str(perf_executable), scenario], perf_executable.parent, "run_" + scenario)
    assert "PASS" in result.stdout


def test_single_sample_ins_exact_equivalence(perf_executable):
    """The one-sample mode zeros the second pair and must retain its behavior."""
    directory = perf_executable.parent
    substitutions = {}
    for version in ("baseline", "current"):
        command = json.loads((directory / f"compile_{version}_ins.json").read_text(encoding="utf-8"))["command"]
        old_object = command[command.index("-o") + 1]
        new_object = str(directory / f"{version}_ins_single.o")
        command[command.index("-o") + 1] = new_object
        command.insert(1, "-DSYSTEM_MECHANIZATION_SUBSAMPLE_COUNT=1")
        _run(command, directory, f"compile_{version}_ins_single")
        substitutions[old_object] = new_object
    command = json.loads((directory / "link.json").read_text(encoding="utf-8"))["command"]
    command = [substitutions.get(item, item) for item in command]
    executable = directory / "navigation_perf_single.exe"
    command[command.index("-o") + 1] = str(executable)
    _run(command, directory, "link_single")
    result = _run([str(executable), "ins"], directory, "run_ins_single")
    assert "PASS" in result.stdout
