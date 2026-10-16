"""Native/MCU clock identity and physical coherence, actual owning C sources."""

import ctypes
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUILTIN = ROOT / "apps/SCG/plugins/builtin"
CORE = BUILTIN / "silverstar_core_0_1_0/payload"
KERNEL = (
    BUILTIN / "silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
)


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def qualifier(request, tmp_path_factory):
    compiler = shutil.which("gcc")
    assert compiler
    directory = tmp_path_factory.mktemp("recovery_qualifier_" + request.param[1:])
    sources = [
        KERNEL / "Src/navigation_eskf_recovery_qualifier.c",
        CORE / "System/Src/system_gnss_receipt.c",
        Path(__file__).parent / "fixtures/eskf15_recovery_qualifier.c",
    ]
    includes = [
        KERNEL / "Inc",
        CORE / "System/Inc",
        CORE / "Interfaces/Inc",
        CORE / "Common/Inc",
        ROOT / "apps/SCG/tests/fixtures/source_selector",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    target = directory / "recovery_qualifier.dll"
    command = [
        compiler,
        "-std=c11",
        request.param,
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wpedantic",
        "-Wconversion",
        "-Wsign-conversion",
        "-Wshadow",
        "-Wstrict-prototypes",
        "-Wmissing-prototypes",
        "-fno-fast-math",
        "-ffp-contract=off",
        "-shared",
        *["-I" + str(p) for p in includes],
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
    library.Test_RecoveryQualifier.argtypes = [ctypes.c_uint32]
    library.Test_RecoveryQualifier.restype = ctypes.c_int
    return library


@pytest.mark.parametrize("scenario", range(39))
def test_recovery_physical_and_clock_evidence(qualifier, scenario):
    failed_line = qualifier.Test_RecoveryQualifier(scenario)
    assert failed_line == 0, f"Actual C fixture failed at line {failed_line}"
