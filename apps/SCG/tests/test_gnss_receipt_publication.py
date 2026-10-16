"""Actual selector publication races and cache-only paired receipt semantics."""

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUILTIN = ROOT / "apps/SCG/plugins/builtin"
CORE = BUILTIN / "silverstar_core_0_1_0/payload"


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def executable(request, tmp_path_factory):
    output = tmp_path_factory.mktemp("receipt_" + request.param[1:])
    compiler = shutil.which("gcc")
    assert compiler
    source = Path(
        os.environ.get(
            "SILVERSTAR_GNSS_SELECTOR_SOURCE",
            str(CORE / "System/Src/system_source_selector.c"),
        )
    ).resolve()
    fixture = Path(__file__).parent / "fixtures/gnss_receipt_publication.c"
    sources = [
        fixture,
        CORE / "System/Src/system_gnss_receipt.c",
        CORE / "Common/Src/silverstar_assert.c",
    ]
    includes = [
        ROOT / "apps/SCG/tests/fixtures/source_selector",
        CORE / "Tests/Host",
        CORE / "Interfaces/Inc",
        CORE / "System/Inc",
        CORE / "System/User",
        CORE / "Common/Inc",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    includes += [path for path in CORE.rglob("Inc") if path not in includes]
    target = output / "receipt.exe"
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
        "-ffunction-sections",
        "-fdata-sections",
        "-Wl,--gc-sections",
        "-DSILVERSTAR_PROTOCOL_LOGGING_ENABLED=0U",
        "-DSYSTEM_BUILD_BAROMETER_COLD_ENABLED=0U",
        '-DSOURCE_SELECTOR_FIXTURE="'
        + (CORE / "Tests/Host/test_source_selector.c").as_posix()
        + '"',
        '-DSOURCE_SELECTOR_SOURCE="' + source.as_posix() + '"',
        *["-I" + str(path) for path in includes],
        *map(str, sources),
        "-lm",
        "-o",
        str(target),
    ]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    evidence = {
        "command": command,
        "exit_code": run.returncode,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "source_sha256": {
            str(path): sha256(path.read_bytes()).hexdigest()
            for path in [*sources, source, CORE / "Tests/Host/test_source_selector.c"]
        },
    }
    (output / "compile.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf8"
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return target


@pytest.mark.parametrize(
    "scenario",
    [0, 1, 2, 3, 4],
    ids=[
        "liveness_atomic_publication",
        "recovery_atomic_publication",
        "clock_proof",
        "snapshot_output_and_nesting",
        "corrupt_owned_selector_rejected",
    ],
)
def test_actual_source_handoff_barrier_and_clock_proof(executable, scenario):
    command = [str(executable), str(scenario)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    (executable.parent / ("case" + str(scenario) + ".json")).write_text(
        json.dumps(
            {
                "command": command,
                "exit_code": run.returncode,
                "stdout": run.stdout,
                "stderr": run.stderr,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    assert run.returncode == 0, run.stdout + run.stderr
