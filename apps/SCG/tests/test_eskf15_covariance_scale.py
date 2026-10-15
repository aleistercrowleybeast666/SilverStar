"""Bounded full-P congruence kernel; deliberately no GNSS recovery policy.

Before implementation run only ``-k 'test_reference or test_baseline'``. A nonexistent
new API is an unimplemented feature, not pre-fix failure evidence. Acceptance
runs the complete file with both real GCC optimization levels; no fallback.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

DIM = 15
ROOT = Path(__file__).resolve().parents[3]
PAYLOAD = ROOT / "apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload"
KERNEL = PAYLOAD / "Algorithm/Estimator/ESKF15"
COMMON = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common"
FIXTURE = Path(__file__).with_name("fixtures") / "eskf15_covariance_scale.c"
FLOAT_MAX = struct.unpack("f", bytes.fromhex("ffff7f7f"))[0]
RESULT_NAMES = ("applied", "no_change", "at_cap", "invalid_argument", "numeric_error")


def f32(value):
    return ctypes.c_float(value).value


def matrix_identity(diagonal=1.0):
    return [[f32(diagonal if i == j else 0.0) for j in range(DIM)] for i in range(DIM)]


def matrix_dense(seed=0):
    # Diagonal + positive rank-one: strictly SPD, every off-diagonal nonzero.
    vector = [f32((-1 if (i + seed) % 2 else 1) * (i + 1 + seed) / 32) for i in range(DIM)]
    return [[f32(vector[i] * vector[j] + (1 + i / 8 if i == j else 0))
             for j in range(DIM)] for i in range(DIM)]


def matrix_multiply(left, right):
    # Deliberately general float64 matrix product, independent of the C
    # triangle traversal, mirroring and float32 intermediate arithmetic.
    return [[math.fsum(left[i][k] * right[k][j] for k in range(DIM))
             for j in range(DIM)] for i in range(DIM)]


def reference_congruence(covariance, scale):
    diagonal = [[scale[i] if i == j else 0.0 for j in range(DIM)] for i in range(DIM)]
    return matrix_multiply(matrix_multiply(diagonal, covariance), diagonal)


def reference_cholesky(matrix):
    lower = [[0.0] * DIM for _ in range(DIM)]
    for i in range(DIM):
        for j in range(i + 1):
            residual = matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                assert residual > 0 and math.isfinite(residual)
                lower[i][j] = math.sqrt(residual)
            else:
                lower[i][j] = residual / lower[j][j]
    return lower


def float_bytes(values):
    return struct.pack("=" + "f" * len(values), *values)


def covariance_assert(actual, expected):
    for i in range(DIM):
        for j in range(DIM):
            assert actual[i][j] == pytest.approx(expected[i][j], rel=3e-7, abs=1e-44)
            assert float_bytes([actual[i][j]]) == float_bytes([actual[j][i]])
    reference_cholesky(actual)


def library_compile(directory, optimization, scale_api):
    gcc = shutil.which("gcc")
    assert gcc is not None, "Actual Host GCC required; no synthetic compilation substitute"
    output = directory / "eskf_scale.dll"
    command = [gcc, "-std=c11", optimization, "-Wall", "-Wextra", "-Werror", "-pedantic",
               "-fno-fast-math", "-ffp-contract=off", "-shared",
               "-I" + str(KERNEL / "Inc"), "-I" + str(COMMON / "Inc")]
    if scale_api:
        command += ["-DTEST_COVARIANCE_SCALE_API=1"]
    sources = [KERNEL / "Src/navigation_eskf.c", COMMON / "Src/silverstar_assert.c", FIXTURE]
    command += [str(path) for path in sources] + ["-lm", "-o", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    metadata = {
        "command": command, "exit_code": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr,
        "compiler": subprocess.check_output([gcc, "--version"], text=True),
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [*sources, KERNEL / "Inc/navigation_eskf.h"]},
    }
    if output.exists():
        metadata["library_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (directory / "compile.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return ctypes.CDLL(str(output))


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def baseline_library(request, tmp_path_factory):
    directory = tmp_path_factory.mktemp("baseline" + request.param)
    library = library_compile(directory, request.param, False)
    library.Test_NisTrace.argtypes = [ctypes.POINTER(ctypes.c_float)] * 2 + [ctypes.POINTER(ctypes.c_int)] * 2
    library.Test_NisTrace.restype = ctypes.c_int
    return library, directory


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def scale_library(request, tmp_path_factory):
    assert "NavigationEskf_CovarianceScale(" in (KERNEL / "Inc/navigation_eskf.h").read_text(encoding="utf-8"), (
        "CovarianceScale acceptance awaits new API implementation; missing API is not pre-fix defect evidence"
    )
    directory = tmp_path_factory.mktemp("scale" + request.param)
    library = library_compile(directory, request.param, True)
    pointer = ctypes.POINTER(ctypes.c_float)
    library.Test_ScaleRun.argtypes = [pointer, pointer, pointer, ctypes.c_uint32, pointer, ctypes.POINTER(ctypes.c_int)]
    library.Test_ScaleRun.restype = ctypes.c_int
    library.Test_ScaleResult.argtypes = [ctypes.c_uint32]
    library.Test_ScaleResult.restype = ctypes.c_int
    return library


def scale_run(library, covariance, scale=None, cap=None, flags=0):
    scale = [f32(v) for v in (scale if scale is not None else [1.5] * DIM)]
    cap = [f32(v) for v in (cap if cap is not None else [1000.0] * DIM)]
    flat = [f32(value) for row in covariance for value in row]
    p_in = (ctypes.c_float * (DIM * DIM))(*flat)
    scale_in = (ctypes.c_float * DIM)(*scale)
    cap_in = (ctypes.c_float * DIM)(*cap)
    snapshot = bytes(p_in), bytes(scale_in), bytes(cap_in)
    output = (ctypes.c_float * (DIM * DIM))()
    invariants = (ctypes.c_int * 6)()
    result = library.Test_ScaleRun(p_in, scale_in, cap_in, flags, output, invariants)
    enum_values = [library.Test_ScaleResult(i) for i in range(5)]
    assert len(set(enum_values)) == 5
    assert result in enum_values
    assert all(invariants[1:]), list(invariants)
    assert snapshot == (bytes(p_in), bytes(scale_in), bytes(cap_in))
    name = RESULT_NAMES[enum_values.index(result)]
    if name != "applied":
        assert invariants[0] == 1, "Failure/no-change partially committed authoritative state"
        # Alias faults place the input vector into P before the call. The C
        # byte snapshot is taken after this setup and proves unchanged state.
        if not flags & (256 | 512):
            assert bytes(output) == snapshot[0]
    return name, [[float(output[i * DIM + j]) for j in range(DIM)] for i in range(DIM)]


def test_baseline_existing_update_preserves_state_on_repeated_nis_reject(baseline_library):
    library, directory = baseline_library
    covariance = matrix_dense()
    flat = [value for row in covariance for value in row]
    nis = (ctypes.c_float * 8)()
    results = (ctypes.c_int * 8)()
    unchanged = (ctypes.c_int * 8)()
    rejected = library.Test_NisTrace((ctypes.c_float * 225)(*flat), nis, results, unchanged)
    trace = {"scope": "Eight synthetic Update calls; no outage timing, receive qualification or recovery policy",
             "expected_rejected_nis": rejected, "result": list(results),
             "nis": list(nis), "state_byte_unchanged": list(unchanged)}
    (directory / "nis_trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    assert list(results) == [rejected] * 8
    assert all(math.isfinite(value) and value > 25 for value in nis)
    assert list(unchanged) == [1] * 8


def test_reference_uniform_scaling_has_positive_semidefinite_increment():
    covariance = matrix_dense()
    for scale in (1.0, 1.25, 2.0):
        transformed = reference_congruence(covariance, [scale] * DIM)
        if scale == 1:
            assert transformed == covariance
        else:
            increment = [[transformed[i][j] - covariance[i][j] for j in range(DIM)] for i in range(DIM)]
            reference_cholesky(increment)


def test_reference_selective_scaling_is_not_loewner_inflation():
    covariance = matrix_identity()
    covariance[0][1] = covariance[1][0] = 0.9
    transformed = reference_congruence(covariance, [2.0] + [1.0] * (DIM - 1))
    reference_cholesky(transformed)
    a = transformed[0][0] - covariance[0][0]
    b = transformed[0][1] - covariance[0][1]
    d = transformed[1][1] - covariance[1][1]
    assert a * d - b * b == pytest.approx(-0.81)


@pytest.mark.parametrize("seed", [0, 1, 9])
@pytest.mark.parametrize("scales", [[1.0] * DIM, [1.25] * DIM, [2.0] * DIM,
                                  [1 + i / 16 for i in range(DIM)]])
def test_all_225_entries_match_independent_reference(scale_library, seed, scales):
    covariance = matrix_dense(seed)
    result, actual = scale_run(scale_library, covariance, scales)
    assert result == ("no_change" if max(scales) == 1 else "applied")
    covariance_assert(actual, reference_congruence(covariance, scales))
    for i in range(DIM):
        for j in range(DIM):
            assert actual[i][j] != 0  # This dense fixture has no zero cross terms.
            before = covariance[i][j] / math.sqrt(covariance[i][i] * covariance[j][j])
            after = actual[i][j] / math.sqrt(actual[i][i] * actual[j][j])
            assert after == pytest.approx(before, rel=3e-7)


@pytest.mark.parametrize("axis", [0, 7, 14])
@pytest.mark.parametrize("value", [0.0, -1.0, 0.99999994, 2.00000024, math.nan, math.inf, -math.inf])
def test_invalid_scale_is_transactional(scale_library, axis, value):
    scales = [1.5] * DIM
    scales[axis] = value
    assert scale_run(scale_library, matrix_dense(), scales)[0] == "invalid_argument"


@pytest.mark.parametrize("axis", [0, 7, 14])
@pytest.mark.parametrize("value", [0.0, -0.0, -1.0, math.nan, math.inf, -math.inf])
def test_invalid_cap_is_transactional(scale_library, axis, value):
    caps = [1000.0] * DIM
    caps[axis] = value
    assert scale_run(scale_library, matrix_dense(), cap=caps)[0] == "invalid_argument"


@pytest.mark.parametrize("flags", [1, 2, 4, 8, 16, 32])
def test_null_and_uninitialized_arguments_are_transactional(scale_library, flags):
    assert scale_run(scale_library, matrix_dense(), flags=flags)[0] == "invalid_argument"


@pytest.mark.parametrize("flags", [64, 128, 256, 512])
def test_input_aliases_with_mutable_objects_are_rejected_before_write(scale_library, flags):
    assert scale_run(scale_library, matrix_dense(), flags=flags)[0] == "invalid_argument"


def test_read_only_scale_and_cap_can_share_an_array(scale_library):
    covariance = matrix_identity(0.25)
    result, actual = scale_run(scale_library, covariance, flags=1024)
    assert result == "applied"
    covariance_assert(actual, reference_congruence(covariance, [1.5] * DIM))


@pytest.mark.parametrize("axis", [0, 7, 14])
@pytest.mark.parametrize("scales", [[1.0] * DIM, [2.0] * DIM])
def test_caps_are_inclusive_and_never_clamped(scale_library, axis, scales):
    covariance = matrix_identity()
    caps = [4.0] * DIM
    caps[axis] = scales[axis] ** 2
    assert scale_run(scale_library, covariance, scales, caps)[0] == (
        "no_change" if max(scales) == 1 else "applied")
    caps[axis] *= 0.99999988
    assert scale_run(scale_library, covariance, scales, caps)[0] == "at_cap"


@pytest.mark.parametrize("fault", ["diagonal_nan", "diagonal_inf", "lower_nan", "upper_inf",
                                  "negative_diagonal", "zero_diagonal", "indefinite", "singular",
                                  "asymmetric_large", "asymmetric_one_ulp", "asymmetric_signed_zero"])
@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_original_covariance_is_not_repaired(scale_library, fault, factor):
    covariance = matrix_identity()
    if fault == "diagonal_nan":
        covariance[14][14] = math.nan
    elif fault == "diagonal_inf":
        covariance[7][7] = math.inf
    elif fault == "lower_nan":
        covariance[14][0] = math.nan
    elif fault == "upper_inf":
        covariance[0][14] = math.inf
    elif fault == "negative_diagonal":
        covariance[14][14] = -1.0
    elif fault == "zero_diagonal":
        covariance[14][14] = 0.0
    elif fault == "indefinite":
        covariance[0][1] = covariance[1][0] = 2.0
    elif fault == "singular":
        covariance[0][1] = covariance[1][0] = 1.0
    elif fault == "asymmetric_large":
        covariance[0][14] = 0.1
    elif fault == "asymmetric_one_ulp":
        covariance[0][14] = 0.25
        covariance[14][0] = f32(0.2500000298023224)
    elif fault == "asymmetric_signed_zero":
        covariance[0][14] = -0.0
    assert scale_run(scale_library, covariance, [factor] * DIM)[0] == "numeric_error"


@pytest.mark.parametrize("axis", [0, 7, 14])
def test_candidate_overflow_is_numeric_error_with_no_commit(scale_library, axis):
    covariance = matrix_identity()
    covariance[axis][axis] = FLOAT_MAX
    scales = [1.0] * DIM
    scales[axis] = 2.0
    assert scale_run(scale_library, covariance, scales, [FLOAT_MAX] * DIM)[0] == "numeric_error"


def test_finite_large_candidate_can_reach_exact_cap(scale_library):
    covariance = matrix_identity()
    covariance[14][14] = f32(FLOAT_MAX / 4)
    scales = [1.0] * DIM
    scales[14] = 2.0
    result, actual = scale_run(scale_library, covariance, scales, [FLOAT_MAX] * DIM)
    assert result == "applied"
    covariance_assert(actual, reference_congruence(covariance, scales))


def test_finite_candidate_cholesky_failure_does_not_publish(scale_library):
    covariance = matrix_identity()
    covariance[0][1] = covariance[1][0] = f32(1.0 - 2 ** -24)
    scales = [1.8009313344955444, 1.7172355651855469] + [1.0] * (DIM - 2)
    # Both original and exact real-arithmetic congruence are SPD. A finite
    # float32 candidate can still fail the existing numerical diagnostic.
    reference_cholesky(covariance)
    reference_cholesky(reference_congruence(covariance, scales))
    assert scale_run(scale_library, covariance, [1.0] * DIM)[0] == "no_change"
    assert scale_run(scale_library, covariance, scales)[0] == "numeric_error"


def test_repeated_calls_use_no_hidden_policy_or_budget(scale_library):
    original = matrix_dense()
    covariance = original
    for _ in range(4):
        result, covariance = scale_run(scale_library, covariance, [2.0] * DIM, [1e6] * DIM)
        assert result == "applied"
    covariance_assert(covariance, reference_congruence(original, [16.0] * DIM))
