"""Independent float64 forward horizon plus real C full-state/full-P comparison."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfNoise, EskfState
from silverstar_flp.plugins.algorithms.eskf15.horizon import (
    DelayedHorizon, HorizonBody, HorizonMeasurement, HorizonResult as Result,
)
from silverstar_flp.plugins.algorithms.eskf15.replay import Measurement

START = 1_000_000


def engine_create(lag=30000):
    noise = EskfNoise(*map(lambda value: float(np.float32(value)), (.003, .08, .0001, .001)))
    kernel = Eskf15Filter(EskfState(covariance=np.eye(15)), gravity=float(np.float32(9.78)), noise=noise)
    return DelayedHorizon(kernel, START, epoch=1, horizon_us=lag,
                         soft=tuple(map(float, np.float32([6.635, 9.21]))),
                         hard=tuple(map(float, np.float32([10.828, 13.816]))))


def body_create(index, *, raw=None):
    values = np.asarray(raw if raw is not None else [0] * 6 + [0, 0, 9.78] * 2, dtype=np.float32).astype(float)
    return HorizonBody(START + index * 5000, START + (index + 1) * 5000,
        values[:3].copy(), values[6:9].copy(), values[3:6].copy(), values[9:12].copy(),
        0, 1, 0, float(np.float32(.005)))


def measurement_create(source_us, receive_us, *, group=0, sequence=1, operation=1, source=0,
                       value=None, variance=None, **changes):
    dimension = 2 if group in (0, 2) else 1
    value = np.zeros(dimension) if value is None else np.asarray(value, dtype=np.float32).astype(float)
    variance = np.ones(dimension) if variance is None else np.asarray(variance, dtype=np.float32).astype(float)
    event = Measurement((operation, group), source_us, receive_us, group, value, variance,
                        True, source=source, generation=1, source_sequence=sequence, mission_epoch=1)
    return replace(event, **changes)


def state_flat(state):
    return np.r_[state.p, state.v, state.q, state.bg, state.ba, state.covariance.ravel()]


def test_recorded_prepared_variance_is_not_scaled_a_second_time():
    baseline, recorded = engine_create(), engine_create()
    common = dict(key=(1, 0), timestamp_us=START + 2500, receive_us=START + 5000,
        group=0, value=np.array([.1, -.1]), variance=np.array([2., 3.]),
        physically_valid=True, source=0, generation=1, source_sequence=1, mission_epoch=1)
    events = (Measurement(**common), HorizonMeasurement(**common,
        quality_scale=4., consistency_scale=9., prepared_variance=np.array([2., 3.])))
    for engine, event in zip((baseline, recorded), events, strict=True):
        for cycle in range(8):
            assert engine.Body_Receive(body_create(cycle)) == Result.OK
            if cycle == 0:
                assert engine.Measurement_Receive(event) == Result.QUEUED
            assert engine.Advance() in (Result.OK, Result.WARMUP)
            while engine.Completion_Pop()[0] == Result.OK:
                pass
    np.testing.assert_array_equal(state_flat(recorded.primary), state_flat(baseline.primary))
    np.testing.assert_array_equal(state_flat(recorded.kernel.state), state_flat(baseline.kernel.state))


def test_output_epoch_does_not_advance_on_raw_receipt_or_failed_prediction():
    engine = engine_create()
    assert engine.Body_Receive(body_create(0)) == Result.OK
    assert engine.Audit_Get()['output_state_us'] == START
    engine.steps[0].accel2[0] = np.nan
    before = state_flat(engine.primary).copy(), state_flat(engine.kernel.state).copy()
    assert engine.Advance() == Result.NUMERIC_ERROR
    np.testing.assert_array_equal(state_flat(engine.primary), before[0])
    np.testing.assert_array_equal(state_flat(engine.kernel.state), before[1])
    assert engine.Audit_Get()['output_covariance_us'] == START
    assert engine.Advance() == Result.NOT_READY


def test_output_mutation_never_changes_primary():
    engine = engine_create()
    for i in range(9):
        assert engine.Body_Receive(body_create(i)) == Result.OK
        assert engine.Advance() in (Result.OK, Result.WARMUP)
    before = state_flat(engine.primary).copy(), state_flat(engine.kernel.state).copy()
    engine.kernel.state.p[:] = 12345
    engine.kernel.state.covariance[0, 0] = -1
    assert engine.Advance() == Result.OK
    np.testing.assert_array_equal(state_flat(engine.primary), before[0])
    np.testing.assert_array_equal(state_flat(engine.kernel.state), before[1])


@pytest.mark.parametrize('field', ['bg', 'ba', 'q'])
def test_stored_nominal_violation_is_not_normalized_or_repaired(field):
    engine = engine_create()
    assert engine.Body_Receive(body_create(0)) == Result.OK
    getattr(engine.primary, field)[0] = 10
    before = state_flat(engine.primary).copy()
    assert engine.Advance() == Result.NUMERIC_ERROR
    np.testing.assert_array_equal(state_flat(engine.primary), before)


@pytest.mark.parametrize('changes,expected', [({'generation': 2}, Result.EPOCH_MISMATCH),
    ({'mission_epoch': 2}, Result.EPOCH_MISMATCH), ({'source': 4}, Result.INVALID),
    ({'physically_valid': False}, Result.INVALID), ({'variance': np.array([0., 1.])}, Result.INVALID),
    ({'quality_scale': -1., 'consistency_scale': -1.}, Result.INVALID)])
def test_measurement_rejections_leave_valid_prediction_usable(changes, expected):
    engine = engine_create()
    assert engine.Body_Receive(body_create(0)) == Result.OK
    event = measurement_create(START + 1000, START + 5000)
    assert engine.Measurement_Receive(replace(event, **changes)) == expected
    assert not engine.faulted and not engine.measurements
    assert engine.Advance() == Result.WARMUP


def test_completion_backpressure_and_late_policy():
    engine = engine_create()
    for i in range(7):
        assert engine.Body_Receive(body_create(i)) == Result.OK
        if i == 0:
            assert engine.Measurement_Receive(measurement_create(START + 2500, START + 5000)) == Result.QUEUED
        assert engine.Advance() in (Result.OK, Result.WARMUP)
    assert engine.primary_us == START + 5000
    assert engine.Body_Receive(body_create(7)) == Result.BUSY
    assert engine.Advance() == Result.BUSY
    assert engine.Completion_Pop()[0] == Result.OK
    assert engine.Completion_Pop()[0] == Result.EMPTY
    assert engine.Measurement_Receive(measurement_create(START + 2500, START + 35000, sequence=2)) == Result.LATE
    assert engine.Body_Receive(body_create(7)) == Result.OK
    assert engine.Advance() == Result.OK


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def native_core(request, tmp_path_factory):
    selected = os.environ.get('SILVERSTAR_FCCG_ROOT')
    assert selected, 'Select actual SCG source root; no backend parity skip or fallback'
    helper_path = Path(selected).resolve() / 'tests/test_eskf15_horizon.py'
    spec = importlib.util.spec_from_file_location('actual_horizon_host_accessors', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.HorizonLibrary_Compile(tmp_path_factory.mktemp('native_horizon_' + request.param), request.param)


@pytest.mark.parametrize('lag,steps', [(30000, 120), (32500, 120), (10000, 120)])
def test_forward_primary_output_and_every_p_entry_match_real_c(native_core, tmp_path, lag, steps):
    core = native_core
    assert core.reset(lag) == 'ok'
    engine = engine_create(lag)
    operation = 0
    maximum = dict(primary=0., output=0., nis=0.)
    completions = 0
    for index in range(steps):
        raw = np.float32([.02 * np.sin(index / 17), .01, -.02,
            .03 * np.sin(index / 13), .011, -.019,
            .1, .03 * np.cos(index / 11), 9.78, .11, .02, 9.77]).astype(float)
        step = body_create(index, raw=raw)
        assert core.body(step.start_us, raw=raw) == engine.Body_Receive(step).name.lower() == 'ok'
        incoming = []
        now = step.end_us
        if index >= 4 and index % 5 == 4:
            for group in range(4):
                dimension = 2 if group in (0, 2) else 1
                incoming.append(measurement_create(now - min(lag - 1000, 17000), now,
                    group=group, sequence=index // 5 + 1, operation=operation + len(incoming) + 1,
                    value=np.full(dimension, .01 * np.sin(index / 7)), variance=np.full(dimension, .5)))
        if index >= 2 and index % 2 == 0:
            incoming.append(measurement_create(now - min(lag - 1500, 12000), now,
                group=4, sequence=index // 2 + 1, source=1, operation=operation + len(incoming) + 1,
                value=[.02], variance=[1.5]))
        for event in incoming:
            obs = list(event.value) + [0.] * (2 - len(event.value))
            var = list(event.variance) + [0.] * (2 - len(event.variance))
            c_result = core.insert(event.timestamp_us, now, group=event.group, source=event.source,
                sequence=event.source_sequence, operation=event.key[0], observation=obs, variance=var)
            assert c_result == engine.Measurement_Receive(event).name.lower() == 'queued'
        operation += len(incoming)
        assert core.advance() == engine.Advance().name.lower()
        actual = core.snapshot()
        assert actual['times'][:2] == [engine.primary_us, engine.output_us]
        for label, expected in [('primary', engine.primary), ('output', engine.kernel.state)]:
            delta = np.max(np.abs(np.asarray(actual[label]) - state_flat(expected)))
            maximum[label] = max(maximum[label], float(delta))
            np.testing.assert_allclose(actual[label], state_flat(expected), rtol=8e-5, atol=3e-6)
        assert actual['counts'][5] == engine.last_work
        np.testing.assert_allclose(core.acceleration(), engine.output_acceleration, atol=3e-5, rtol=8e-5)
        while True:
            c_status, ids, values = core.pop()
            status, completion = engine.Completion_Pop()
            assert c_status == status.name.lower()
            if status == Result.EMPTY:
                break
            assert status == Result.OK
            event, outcome = completion
            assert ids == [event.key[0], event.source_sequence, event.group, event.source, int(outcome.result)]
            maximum['nis'] = max(maximum['nis'], abs(values[0] - outcome.nis))
            assert values[0] == pytest.approx(outcome.nis, rel=2e-4, abs=1e-6)
            completions += 1
    (tmp_path / 'full_state_p_parity.json').write_text(json.dumps(dict(
        scope='C module vs independent float64 primary/full-P output; not backend/wire/hardware',
        steps=steps, horizon_us=lag, completions=completions, maximum_absolute_error=maximum,
        pending=engine.Audit_Get()), indent=2), encoding='utf-8')
    assert completions > 80 and maximum['primary'] < 3e-5 and maximum['output'] < 3e-5
