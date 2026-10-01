"""Same inputs/compiler/flags, exact full-state/covariance/failure equivalence."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture(scope="module")
def eskf_trace_executables(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[3]
    app = root / "apps/FCCG"
    relative = "apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
    baseline_commit = os.environ.get("SILVERSTAR_ESKF_BASELINE", "42d4203b0158184e4a8609a1a971a788f335cfb0")
    directory = tmp_path_factory.mktemp("eskf-equivalence")
    baseline = directory / "baseline"
    baseline.mkdir()
    for suffix in ("Inc/navigation_eskf.h", "Inc/navigation_eskf_replay.h", "Src/navigation_eskf.c", "Src/navigation_eskf_replay.c"):
        path = baseline / suffix
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"{baseline_commit}:{relative}/{suffix}"], cwd=root))
    core = app / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
    executables = {}
    commands = []
    for optimization in ("-O0", "-O2"):
        for version, source in (("before", baseline), ("after", root / relative)):
            exe = directory / f"{version}{optimization}.exe"
            command = [gcc, "-std=c11", optimization, "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-fno-fast-math", "-ffp-contract=off", "-I" + str(source / "Inc"),
                "-I" + str(core / "Inc"), str(source / "Src/navigation_eskf.c"),
                str(source / "Src/navigation_eskf_replay.c"), str(core / "Src/silverstar_assert.c"),
                str(app / "tests/fixtures/eskf_workspace_trace.c"), "-lm", "-o", str(exe)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            commands.append({"command": command, "exit_code": result.returncode,
                             "output": result.stdout + result.stderr})
            (directory / "compile_commands.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
            assert result.returncode == 0, result.stdout + result.stderr
            executables[optimization, version] = exe
    return executables


@pytest.mark.parametrize("optimization", ["-O0", "-O2"])
@pytest.mark.parametrize("scenario", ["aliases", "stationary", "rotation", "motion", "outage", "faults", "concurrent"])
def test_eskf_exact_trace_equivalence(eskf_trace_executables, optimization, scenario):
    traces = []
    for version in ("before", "after"):
        exe = eskf_trace_executables[optimization, version]
        result = subprocess.run([str(exe), scenario], capture_output=True, timeout=60)
        exe.with_name(f"{version}{optimization}_{scenario}.trace").write_bytes(result.stdout)
        exe.with_name(f"{version}{optimization}_{scenario}.stderr").write_bytes(result.stderr)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        traces.append(result.stdout)
    assert traces[0] == traces[1], f"Complete state/covariance/outcome/history trace changed: {optimization} {scenario}"


def test_eskf_workspace_storage_reduction(eskf_trace_executables):
    sizes = []
    for version in ("before", "after"):
        result = subprocess.run([str(eskf_trace_executables["-O2", version]), "size"],
                                capture_output=True, text=True, check=True, timeout=10)
        sizes.append(int(result.stdout.strip()))
    assert sizes == [3980, 3140]
