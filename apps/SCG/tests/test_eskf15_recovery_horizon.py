"""Full-P/policy horizon commit and post-scale output failure rollback."""

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
def horizon(request, tmp_path_factory):
    compiler = shutil.which("gcc")
    assert compiler
    directory = tmp_path_factory.mktemp("recovery_horizon_" + request.param[1:])
    sources = [
        KERNEL / "Src/navigation_eskf.c",
        KERNEL / "Src/navigation_eskf_recovery.c",
        CORE / "Src/silverstar_assert.c",
        Path(__file__).parent / "fixtures/eskf15_recovery.c",
        Path(__file__).parent / "fixtures/eskf15_recovery_horizon.c",
    ]
    actual_horizon = KERNEL / "Src/navigation_eskf_horizon.c"
    target = directory / "recovery_horizon.dll"
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
        '-DHORIZON_SOURCE="' + actual_horizon.as_posix() + '"',
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
                    str(p): sha256(p.read_bytes()).hexdigest()
                    for p in [*sources, actual_horizon]
                },
            },
            indent=2,
        ),
        encoding="utf8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    library = ctypes.CDLL(str(target))
    library.Test_RecoveryHorizon.argtypes = [ctypes.c_uint32]
    library.Test_RecoveryHorizon.restype = ctypes.c_int
    return library


@pytest.mark.parametrize(
    "scenario",
    range(3),
    ids=[
        "full_p_policy_commit",
        "post_scale_output_failure_rollback",
        "corrupt_policy_no_commit",
    ],
)
def test_recovery_horizon_authority(horizon, scenario):
    failed_line = horizon.Test_RecoveryHorizon(scenario)
    assert failed_line == 0, f"Actual C fixture failed at line {failed_line}"
