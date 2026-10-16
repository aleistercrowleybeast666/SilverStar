"""Actual optional replay companion: canonical reconstruction and rollback."""

import ctypes
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common"
KERNEL = (
    ROOT
    / "apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
)


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def replay(request, tmp_path_factory):
    compiler = shutil.which("gcc")
    assert compiler
    directory = tmp_path_factory.mktemp("recovery_replay_" + request.param[1:])
    sources = [
        KERNEL / ("Src/" + name + ".c")
        for name in (
            "navigation_eskf",
            "navigation_eskf_replay",
            "navigation_eskf_recovery",
        )
    ]
    sources += [
        CORE / "Src/silverstar_assert.c",
        Path(__file__).parent / "fixtures/eskf15_recovery.c",
        Path(__file__).parent / "fixtures/eskf15_recovery_replay.c",
    ]
    target = directory / "recovery_replay.dll"
    command = [
        compiler,
        "-std=c11",
        request.param,
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-fno-fast-math",
        "-ffp-contract=off",
        "-shared",
        "-I" + str(KERNEL / "Inc"),
        "-I" + str(CORE / "Inc"),
        *map(str, sources),
        "-lm",
        "-o",
        str(target),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=90
    )
    (directory / "compile.json").write_text(
        json.dumps(
            {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "source_sha256": {
                    str(p): sha256(p.read_bytes()).hexdigest() for p in sources
                },
            },
            indent=2,
        ),
        encoding="utf8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    library = ctypes.CDLL(str(target))
    library.Test_RecoveryReplay.argtypes = [ctypes.c_uint32]
    library.Test_RecoveryReplay.restype = ctypes.c_int
    return library


@pytest.mark.parametrize(
    "scenario",
    range(5),
    ids=[
        "reorder_prefix_commit",
        "bad_source_rollback",
        "corrupt_policy_rollback",
        "duplicate_no_refill",
        "history_miss_no_refill",
    ],
)
def test_recovery_replay_authority(replay, scenario):
    failed_line = replay.Test_RecoveryReplay(scenario)
    assert failed_line == 0, f"Actual C fixture failed at line {failed_line}"
