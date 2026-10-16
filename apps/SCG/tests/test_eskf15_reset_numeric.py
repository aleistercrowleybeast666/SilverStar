"""Independent high-precision SO(3) reset oracle; no acceptance-threshold waiver."""
import ctypes as ct
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
KERNEL = ROOT / 'apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15'
COMMON = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common'
FIXTURE = Path(__file__).with_name('fixtures') / 'eskf15_reset_numeric.c'


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def numeric_library(request, tmp_path_factory):
    directory = tmp_path_factory.mktemp('reset_numeric_' + request.param)
    compiler = shutil.which('gcc')
    assert compiler
    library = directory / 'reset_numeric.dll'
    source = KERNEL / 'Src/navigation_eskf.c'
    command = [compiler, '-std=c11', request.param, '-Wall', '-Wextra', '-Werror', '-Wpedantic',
        '-Wconversion', '-Wsign-conversion', '-Wshadow', '-Wstrict-prototypes', '-Wmissing-prototypes',
        '-fno-fast-math', '-ffp-contract=off', '-shared', '-I' + str(KERNEL / 'Inc'),
        '-I' + str(COMMON / 'Inc'), '-DNAV_ESKF_TEST_SOURCE="' + source.as_posix() + '"',
        '-DNAV_ESKF_TEST_RESET_REVISION=2',
        str(FIXTURE), str(COMMON / 'Src/silverstar_assert.c'), '-lm', '-o', str(library)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    record = dict(command=command, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr,
                  source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in (source, FIXTURE, KERNEL / 'Inc/navigation_eskf.h')})
    if library.exists():
        record['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
    (directory / 'compile.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
    result = ct.CDLL(str(library))
    result.Test_EskfResetNumeric.argtypes = [ct.POINTER(ct.c_float)] * 4
    return result


def reference_jacobian(vector):
    # Evaluate sin/cos with 60-digit Decimal series, not the candidate C formula.
    with localcontext() as context:
        context.prec = 60
        v = [Decimal.from_float(float(x)) for x in vector]
        angle2 = sum(x * x for x in v)
        if not angle2:
            return [[float(i == j) for j in range(3)] for i in range(3)]
        angle = angle2.sqrt()
        sine, cosine = Decimal(0), Decimal(0)
        for n in range(32):
            sine += (-1) ** n * angle ** (2 * n + 1) / Decimal(math.factorial(2 * n + 1))
            cosine += (-1) ** n * angle ** (2 * n) / Decimal(math.factorial(2 * n))
        a, b = (1 - cosine) / angle2, (angle - sine) / (angle2 * angle)
        skew = [[Decimal(0), -v[2], v[1]], [v[2], Decimal(0), -v[0]], [-v[1], v[0], Decimal(0)]]
        return [[float(Decimal(i == j) - a * skew[i][j] +
            b * sum(skew[i][k] * skew[k][j] for k in range(3))) for j in range(3)] for i in range(3)]


@pytest.mark.parametrize('angle', [0., 1e-7, 9e-4, .000999, .001, .001001, .0015,
                                  .002, .003, .005, .01, .02, .05, .1, .2, .349])
@pytest.mark.parametrize('direction', [(1, 0, 0), (1, 2, -3)])
def test_revision2_jacobian_and_all_225_entries_match_high_precision(numeric_library, angle, direction):
    norm = math.sqrt(sum(x * x for x in direction))
    vector = [ct.c_float(angle * x / norm).value for x in direction]
    # Strictly SPD dense matrix; every cross term is nonzero and checked.
    rank = [(i + 1) / 32 for i in range(15)]
    p = [[ct.c_float(rank[i] * rank[j] + (1 + i / 8 if i == j else 0)).value
          for j in range(15)] for i in range(15)]
    actual_j, actual_p = (ct.c_float * 9)(), (ct.c_float * 225)()
    numeric_library.Test_EskfResetNumeric((ct.c_float * 3)(*vector),
        (ct.c_float * 225)(*(x for row in p for x in row)), actual_j, actual_p)
    expected_j = reference_jacobian(vector)
    for i in range(3):
        for j in range(3):
            assert actual_j[i * 3 + j] == pytest.approx(expected_j[i][j], abs=4e-8, rel=0)
    jacobian = [[float(i == j) for j in range(15)] for i in range(15)]
    for i in range(3):
        jacobian[i + 6][6:9] = expected_j[i]
    product = [[math.fsum(jacobian[i][k] * p[k][j] for k in range(15)) for j in range(15)] for i in range(15)]
    expected = [[math.fsum(product[i][k] * jacobian[j][k] for k in range(15)) for j in range(15)] for i in range(15)]
    for i in range(15):
        for j in range(15):
            assert actual_p[i * 15 + j] == pytest.approx(expected[i][j], abs=2e-6, rel=0)
