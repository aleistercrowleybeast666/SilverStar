"""Real C queue/transaction/lifecycle tests; backend and FLP activation are separate."""
from __future__ import annotations

import ctypes as ct
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
KERNEL = ROOT / 'apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15'
COMMON = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common'
FIXTURE = Path(__file__).with_name('fixtures') / 'eskf15_horizon.c'
NAMES = ('ok', 'queued', 'warmup', 'invalid', 'stale', 'late', 'capacity', 'duplicate',
         'epoch_mismatch', 'discontinuity', 'numeric_error', 'model_mismatch', 'not_ready', 'busy', 'empty')
START = 1_000_000


class Core:
    def __init__(self, library):
        self.lib = library
        fp = ct.POINTER(ct.c_float)
        u32 = ct.c_uint32
        u64 = ct.c_uint64
        library.Test_Reset.argtypes = [u64, u64]
        library.Test_Body.argtypes = [u64, u64, ct.c_float, fp, u32, u32, u32]
        library.Test_Insert.argtypes = [u64, u64, u32, u32, u32, u32, u32, u32, fp]
        library.Test_Snapshot.argtypes = [fp, fp, ct.POINTER(u64), ct.POINTER(u32)]
        library.Test_Pop.argtypes = [ct.POINTER(u32), fp]
        library.Test_Corrupt.argtypes = [u32]
        library.Test_AccelerationGet.argtypes = [fp]
        self.results = {library.Test_Result(i): name for i, name in enumerate(NAMES)}
        assert len(self.results) == len(NAMES)

    def name(self, result):
        return self.results[result]

    def reset(self, lag=30_000):
        return self.name(self.lib.Test_Reset(START, lag))

    def body(self, start, end=None, *, dt=None, raw=None, source=0, generation=1, flags=0):
        end = start + 5000 if end is None else end
        dt = (end - start) * 1e-6 if dt is None else dt
        raw = [0] * 6 + [0, 0, 9.78] * 2 if raw is None else raw
        return self.name(self.lib.Test_Body(start, end, dt, (ct.c_float * 12)(*raw), source, generation, flags))

    def insert(self, source_us, receive_us, *, sequence=1, source=0, generation=1,
               group=0, valid=1, operation=1, observation=(.1, -.1), variance=(1, 1), lever=(0, 0, 0)):
        values = (ct.c_float * 7)(*observation, *variance, *lever)
        return self.name(self.lib.Test_Insert(source_us, receive_us, sequence, source, generation,
                                              group, valid, operation, values))

    def advance(self):
        return self.name(self.lib.Test_Advance())

    def snapshot(self):
        primary, output = (ct.c_float * 241)(), (ct.c_float * 241)()
        times, counts = (ct.c_uint64 * 4)(), (ct.c_uint32 * 9)()
        self.lib.Test_Snapshot(primary, output, times, counts)
        return dict(primary=list(primary), output=list(output), times=list(times), counts=list(counts),
                    primary_bytes=bytes(primary), output_bytes=bytes(output))

    def pop(self):
        ids, values = (ct.c_uint32 * 5)(), (ct.c_float * 8)()
        result = self.name(self.lib.Test_Pop(ids, values))
        return result, list(ids), list(values)

    def acceleration(self):
        value = (ct.c_float * 3)()
        self.lib.Test_AccelerationGet(value)
        return list(value)


def HorizonLibrary_Compile(output, optimization):
    compiler = shutil.which('gcc')
    assert compiler, 'Actual GCC is required; no syntax-only or synthetic substitute'
    sources = [KERNEL / 'Src/navigation_eskf.c', KERNEL / 'Src/navigation_eskf_horizon.c',
               KERNEL / 'Src/navigation_eskf_recovery.c',
               COMMON / 'Src/silverstar_assert.c', FIXTURE]
    library = output / 'horizon.dll'
    command = [compiler, '-std=c11', optimization, '-Wall', '-Wextra', '-Werror', '-Wpedantic',
               '-Wconversion', '-Wsign-conversion', '-Wshadow', '-Wstrict-prototypes',
               '-Wmissing-prototypes', '-fno-fast-math', '-ffp-contract=off', '-shared',
               '-I' + str(KERNEL / 'Inc'), '-I' + str(COMMON / 'Inc'),
               *map(str, sources), '-lm', '-o', str(library)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=120)
    record = dict(command=command, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr,
                  compiler=subprocess.check_output([compiler, '--version'], text=True),
                  sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [*sources, KERNEL / 'Inc/navigation_eskf_horizon.h']})
    (output / 'compile.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    assert run.returncode == 0, run.stdout + run.stderr
    record['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
    result = Core(ct.CDLL(str(library)))
    record['context_bytes_host_only_not_linked_target_budget'] = result.lib.Test_ContextSize()
    (output / 'compile.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return result


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def core(request, tmp_path_factory):
    return HorizonLibrary_Compile(tmp_path_factory.mktemp('horizon_' + request.param), request.param)


def advance_cycles(core, count, *, first=START, raw=None):
    for i in range(count):
        assert core.body(first + i * 5000, raw=raw) == 'ok'
        assert core.advance() in ('ok', 'warmup')


def assert_spd(values):
    p = [values[16 + i * 15:16 + (i + 1) * 15] for i in range(15)]
    lower = [[0.] * 15 for _ in range(15)]
    for i in range(15):
        for j in range(i + 1):
            assert math.isfinite(p[i][j]) and p[i][j] == p[j][i]
            residual = p[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                assert residual > 0
                lower[i][j] = math.sqrt(residual)
            else:
                lower[i][j] = residual / lower[j][j]
    assert math.fsum(q * q for q in values[6:10]) == pytest.approx(1, abs=2e-5)


@pytest.mark.parametrize('lag,expected', [(0, 'invalid'), (9999, 'invalid'), (10000, 'ok'),
                                        (550000, 'ok'), (550001, 'invalid')])
def test_explicit_horizon_bounds(core, lag, expected):
    assert core.reset(lag) == expected


def test_primary_stays_delayed_output_predicts_complete_covariance(core):
    assert core.reset() == 'ok'
    raw = [0] * 6 + [1, 0, 9.78] * 2
    for i in range(8):
        assert core.body(START + i * 5000, raw=raw) == 'ok'
        result = core.advance()
        snapshot = core.snapshot()
        elapsed = (i + 1) * .005
        delayed = max(0, elapsed - .03)
        assert result == ('warmup' if i < 5 else 'ok')
        assert snapshot['times'][:3] == [START + max(0, (i + 1) * 5000 - 30000),
                                        START + (i + 1) * 5000, START + (i + 1) * 5000]
        assert snapshot['primary'][0] == pytest.approx(.5 * delayed ** 2, abs=2e-8)
        assert snapshot['output'][0] == pytest.approx(.5 * elapsed ** 2, abs=2e-8)
        assert_spd(snapshot['primary']); assert_spd(snapshot['output'])
        assert snapshot['output'][16 + 3 * 15 + 3] >= snapshot['primary'][16 + 3 * 15 + 3]


def test_output_is_never_fed_back_to_primary(core):
    assert core.reset() == 'ok'
    advance_cycles(core, 9)
    before = core.snapshot()
    core.lib.Test_Corrupt(7)  # Corrupt only the external output, not primary/raw data.
    assert core.advance() == 'ok'
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes']
    assert after['output_bytes'] == before['output_bytes']


def test_mid_interval_observation_waits_then_applies_once(core):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    assert core.insert(START + 2500, START + 5000, operation=123) == 'queued'
    assert core.advance() == 'warmup'
    assert core.pop()[0] == 'empty'
    advance_cycles(core, 5, first=START + 5000)
    assert core.snapshot()['counts'][2] == 0
    assert core.body(START + 30000) == 'ok'
    assert core.advance() == 'ok'
    snapshot = core.snapshot()
    assert snapshot['times'][:2] == [START + 5000, START + 35000]
    assert snapshot['primary'][0] > 0 and snapshot['output'][0] > 0
    result, ids, values = core.pop()
    assert result == 'ok' and ids[:4] == [123, 1, 0, 0]
    assert ids[4] in (0, 1) and values[6] > 0
    assert core.pop()[0] == 'empty'
    assert core.snapshot()['counts'][1:3] == [0, 0]


def test_nis_reject_is_a_completed_attempt_without_numerical_update(core):
    assert core.reset() == 'ok'
    advance_cycles(core, 7)
    baseline = core.snapshot()
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    assert core.insert(START + 5000, START + 5000, observation=(100, -100), variance=(.01, .01)) == 'queued'
    assert core.advance() == 'warmup'
    advance_cycles(core, 6, first=START + 5000)
    after = core.snapshot()
    assert after['primary_bytes'] == baseline['primary_bytes']
    assert after['output_bytes'] == baseline['output_bytes']
    result, ids, values = core.pop()
    assert result == 'ok' and ids[4] == 2 and values[0] > 13.816 and values[6] == 0


def test_fused_velocity_jump_is_not_published_as_imu_acceleration(core):
    assert core.reset(10000) == 'ok'
    assert core.body(START) == 'ok'
    assert core.insert(START + 5000, START + 5000, group=2, observation=(1, 0)) == 'queued'
    assert core.advance() == 'warmup'
    advance_cycles(core, 2, first=START + 5000)
    snapshot = core.snapshot()
    assert snapshot['output'][3] > .4  # A real, sizeable GNSS velocity correction.
    assert max(abs(value) for value in core.acceleration()) < 1e-5
    assert core.pop()[0] == 'ok'


def test_model_mismatch_does_not_partly_commit_primary_or_output(core):
    assert core.reset(10000) == 'ok'
    assert core.body(START) == 'ok'
    assert core.insert(START + 5000, START + 5000, observation=(10, 5), lever=(10, 0, 0)) == 'queued'
    assert core.advance() == 'warmup'
    assert core.body(START + 5000) == 'ok'
    assert core.advance() == 'ok'
    assert core.body(START + 10000) == 'ok'
    before = core.snapshot()
    acceleration = core.acceleration()
    assert core.advance() == 'model_mismatch'
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes'] and after['output_bytes'] == before['output_bytes']
    assert core.acceleration() == acceleration
    assert after['counts'][3] == 1 and after['counts'][2] == 0
    assert core.pop()[0] == 'not_ready'


def test_source_groups_wrap_and_returning_source_watermarks(core):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    for group in (3, 1, 2, 0):
        assert core.insert(START + 1000, START + 5000, sequence=0xffffffff, group=group, operation=group) == 'queued'
    assert core.insert(START + 1000, START + 5000, sequence=0xffffffff, group=0) == 'duplicate'
    assert core.insert(START + 2000, START + 5000, sequence=0, source=1) == 'queued'
    assert core.insert(START + 2000, START + 5000, sequence=0) == 'queued'
    assert core.insert(START + 2000, START + 5000, sequence=0xffffffff) == 'discontinuity'
    assert core.advance() == 'warmup'
    advance_cycles(core, 6, first=START + 5000)
    ids = [core.pop()[1] for _ in range(6)]
    assert [row[2] for row in ids[:4]] == [0, 1, 2, 3]
    assert [row[3] for row in ids[4:]] == [1, 0]  # Same-source-time/group arrival order.


def test_late_reject_and_exact_committed_boundary(core):
    assert core.reset() == 'ok'
    advance_cycles(core, 12)
    before = core.snapshot()
    assert core.insert(START + 25000, START + 60000) == 'late'
    assert core.snapshot()['primary_bytes'] == before['primary_bytes']
    assert core.snapshot()['counts'][7] == 1
    assert core.insert(START + 30000, START + 60000, sequence=2) == 'queued'
    assert core.advance() == 'ok'
    assert core.pop()[0] == 'ok'
    assert core.snapshot()['times'][0] == START + 30000


def test_event_capacity_is_ordinary_and_does_not_replace_queued_work(core):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    for i in range(64):
        assert core.insert(START + i + 1, START + 5000, sequence=i + 1, operation=i + 1,
                           observation=(0, 0), variance=(1000, 1000)) == 'queued'
    assert core.insert(START + 1000, START + 5000, sequence=65) == 'capacity'
    assert core.insert(START + 1000, START + 5000, sequence=65) == 'duplicate'
    assert core.snapshot()['counts'][1:4] == [64, 0, 0]
    assert core.advance() == 'warmup'
    advance_cycles(core, 6, first=START + 5000)
    assert core.snapshot()['counts'][2] == 64
    assert [core.pop()[1][0] for _ in range(64)] == list(range(1, 65))
    assert core.pop()[0] == 'empty'


def test_completion_backpressure_requires_complete_drain(core):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    for group in (0, 1):
        assert core.insert(START + 5000, START + 5000, group=group) == 'queued'
    assert core.advance() == 'warmup'
    advance_cycles(core, 6, first=START + 5000)
    before = core.snapshot()
    assert core.body(START + 35000) == 'busy'
    assert core.advance() == 'busy'
    assert core.insert(START + 10000, START + 35000, sequence=2) == 'busy'
    assert core.snapshot() == before
    assert core.pop()[0] == 'ok'
    assert core.body(START + 35000) == 'busy'
    assert core.pop()[0] == 'ok'
    assert core.body(START + 35000) == 'ok'
    assert core.advance() == 'ok'


def test_raw_body_capacity_latches_and_preserves_primary_output(core):
    assert core.reset(550000) == 'ok'
    before = core.snapshot()
    for i in range(160):
        assert core.body(START + i * 1000, START + (i + 1) * 1000) == 'ok'
    assert core.body(START + 160000, START + 161000) == 'capacity'
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes'] and after['output_bytes'] == before['output_bytes']
    assert after['counts'][0] == 160 and after['counts'][3] == 1
    assert core.advance() == 'not_ready'


@pytest.mark.parametrize('kind,expected', [(1, 'numeric_error'), (2, 'numeric_error'),
    (3, 'numeric_error'), (4, 'numeric_error'), (5, 'numeric_error'), (6, 'epoch_mismatch'),
    (8, 'numeric_error')])
def test_fault_transaction_and_latch(core, kind, expected):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    core.lib.Test_Corrupt(kind)
    before = core.snapshot()
    assert core.advance() == expected
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes']
    assert after['output_bytes'] == before['output_bytes']
    assert after['counts'][3] == 1 and after['counts'][2] == 0
    assert core.advance() == 'not_ready'
    assert core.body(START + 5000) == 'not_ready'
    assert core.pop()[0] == 'not_ready'


@pytest.mark.parametrize('kwargs,expected', [({'source': 1}, 'epoch_mismatch'),
    ({'generation': 2}, 'epoch_mismatch'), ({'dt': math.nan}, 'discontinuity'),
    ({'flags': 0x10}, 'discontinuity')])
def test_invalid_body_identity_or_values_latch(core, kwargs, expected):
    assert core.reset() == 'ok'
    before = core.snapshot()
    assert core.body(START, **kwargs) == expected
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes'] and after['output_bytes'] == before['output_bytes']
    assert after['times'] == before['times'] and after['counts'][3] == 1


@pytest.mark.parametrize('kwargs,expected', [({'group': 5}, 'invalid'), ({'source': 4}, 'invalid'),
    ({'group': 4, 'source': 0}, 'invalid'), ({'generation': 2}, 'epoch_mismatch'),
    ({'valid': 0}, 'invalid'), ({'variance': (math.nan, 1)}, 'invalid'),
    ({'variance': (0, 1)}, 'invalid'), ({'observation': (math.inf, 0)}, 'invalid')])
def test_bad_measurement_is_ordinary_rejection(core, kwargs, expected):
    assert core.reset() == 'ok'
    assert core.body(START) == 'ok'
    before = core.snapshot()
    assert core.insert(START + 1000, START + 5000, **kwargs) == expected
    after = core.snapshot()
    assert after['primary_bytes'] == before['primary_bytes'] and after['output_bytes'] == before['output_bytes']
    assert after['counts'][1:4] == [0, 0, 0]
    assert core.advance() == 'warmup'
