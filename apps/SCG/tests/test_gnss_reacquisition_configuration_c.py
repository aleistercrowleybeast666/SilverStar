"""Exact generated104-byte configuration, C checksum and no-write rejection."""

import ctypes
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParametersHeader_Render,
)
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.gnss_reacquisition import (
    CAPS,
    FIELDS,
    OWNER,
    GnssReacquisitionConfiguration_Resolve,
)
from silverstar_fccg.project.reference import ReferenceProject_Create

ROOT = Path(__file__).resolve().parents[3]
BUILTIN = ROOT / "apps/SCG/plugins/builtin"
CORE = BUILTIN / "silverstar_core_0_1_0/payload"
KERNEL = (
    BUILTIN / "silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
)


@pytest.fixture(
    scope="module",
    params=[
        ("-O0", False, False),
        ("-O2", False, False),
        ("-O0", True, False),
        ("-O2", True, False),
        ("-O0", True, True),
        ("-O2", True, True),
    ],
)
def configuration(request, tmp_path_factory, builtin_catalog):
    optimization, enabled, tampered = request.param
    compiler = shutil.which("gcc")
    assert compiler
    directory = tmp_path_factory.mktemp(
        "configuration_" + optimization[1:] + str(enabled)
    )
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = OWNER
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    values = model.algorithm_parameters[OWNER]
    if enabled:
        synthetic = {
            "enabled": 1,
            "loss_gap_ms": 1000,
            "stable_span_ms": 120,
            "maximum_interval_ms": 100,
            "cooldown_ms": 500,
            "stable_count": 3,
            "reject_count": 2,
            "confirmation_count": 4,
            "maximum_attempts": 8,
            "uniform_scale": 1.9,
            "clock_jitter_ms": 10,
            "horizontal_acceleration_limit_mps2": 30.0,
            "vertical_acceleration_limit_mps2": 20.0,
            "closure_sigma": 3.0,
            **{name: 10.0 + index / 100.0 for index, name in enumerate(CAPS)},
        }
        values.update(
            {"gnss_recovery_" + name: value for name, value in synthetic.items()}
        )
    expected = GnssReacquisitionConfiguration_Resolve(values)
    header = directory / "project_algorithm_parameters.h"
    generated = AlgorithmParametersHeader_Render(model, builtin_catalog)
    if tampered:
        original = f"0x{expected.identity:08X}UL"
        assert generated.count(original) == 1
        generated = generated.replace(original, f"0x{expected.identity ^ 1:08X}UL")
    header.write_text(generated, encoding="utf8")
    sources = [
        KERNEL / ("Src/" + name + ".c")
        for name in (
            "navigation_eskf",
            "navigation_eskf_recovery",
            "navigation_eskf_recovery_qualifier",
            "navigation_eskf_recovery_configuration",
        )
    ]
    sources += [
        CORE / "System/Src/system_gnss_receipt.c",
        CORE / "Common/Src/silverstar_assert.c",
        ROOT / "apps/SCG/tests/fixtures/eskf15_recovery_qualifier.c",
    ]
    includes = [
        KERNEL / "Inc",
        CORE / "System/Inc",
        CORE / "Interfaces/Inc",
        CORE / "Common/Inc",
        ROOT / "apps/SCG/tests/fixtures/source_selector",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    target = directory / "configuration.dll"
    command = [
        compiler,
        "-std=c11",
        optimization,
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
        "-include",
        str(header),
        *["-I" + str(p) for p in includes],
        *map(str, sources),
        "-lm",
        "-o",
        str(target),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=120
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
                    for p in [*sources, header]
                },
                "actual_values": dict(expected.values),
                "wire_hex": expected.wire.hex(),
                "identity": expected.identity,
                "tampered_identity_negative_case": tampered,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    library = ctypes.CDLL(str(target))
    library.NavigationEskfRecoveryConfiguration_Encode.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_uint16,
    ]
    library.NavigationEskfRecoveryConfiguration_Encode.restype = ctypes.c_int
    library.NavigationEskfRecoveryConfiguration_Validate.argtypes = []
    library.NavigationEskfRecoveryConfiguration_Validate.restype = ctypes.c_int
    library.NavigationEskfRecoveryConfiguration_Get.argtypes = []
    library.NavigationEskfRecoveryConfiguration_Get.restype = ctypes.c_void_p
    return library, expected, directory, tampered


def test_actual_generated_configuration_matches_wire_and_crc(configuration):
    library, expected, directory, tampered = configuration
    output = (ctypes.c_uint8 * 104)()
    assert library.NavigationEskfRecoveryConfiguration_Validate() == (
        3 if tampered else 0
    )
    assert library.NavigationEskfRecoveryConfiguration_Encode(output, 104) == 0
    assert bytes(output) == expected.wire
    (directory / "actual_configuration.bin").write_bytes(bytes(output))
    assert len(expected.values) == len(FIELDS) == 29


def test_configuration_invalid_output_preserved(configuration):
    library, _, _, _ = configuration
    output = (ctypes.c_uint8 * 104)(*([0xA5] * 104))
    assert library.NavigationEskfRecoveryConfiguration_Encode(output, 103) == 1
    assert bytes(output) == bytes([0xA5] * 104)
    assert library.NavigationEskfRecoveryConfiguration_Encode(None, 104) == 1
    config_address = library.NavigationEskfRecoveryConfiguration_Get()
    assert config_address
    original = ctypes.string_at(config_address, 192)
    assert (
        library.NavigationEskfRecoveryConfiguration_Encode(
            ctypes.cast(config_address, ctypes.POINTER(ctypes.c_uint8)), 104
        )
        == 1
    )
    assert ctypes.string_at(config_address, 192) == original
