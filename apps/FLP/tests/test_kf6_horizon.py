"""Independent Python scheduler against the actual owning KF horizon C.

The physical inputs are CPU fixtures. No generated mode2/board acceptance claim.
"""
import importlib.util
from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.kf6.horizon import (
    DelayedKfHorizon, HorizonResult, KfHorizonBody, KfHorizonEvent,
)

START = 1000000


def _Filter():
    state = Kf6Filter.Kf6_Create(process_accel_std_mps2=np.array([1.5, 1.5, 2.]),
        p0_diagonal=np.array([4., 4., 9., .25, .25, .25]), initial_velocity_enu_mps=np.zeros(3),
        nis_soft_threshold=np.array([6.635, 9.21, 11.345]),
        nis_hard_threshold=np.array([10.828, 13.816, 16.266]), nis_max_r_scale=10., algorithm_revision=2)
    state.require_effective_gain = True
    return state


def _Horizon(lag=30000):
    return DelayedKfHorizon(_Filter(), START, epoch=7, source=0, generation=1, horizon_us=lag)


@pytest.fixture(scope='module', params=['-O0', '-O2'])
def native(request, tmp_path_factory):
    supplied = os.environ.get('SILVERSTAR_FCCG_ROOT')
    assert supplied, 'Explicit actual SCG source is required; no native parity fallback'
    source = Path(supplied)/'tests/test_kf6_horizon.py'
    spec = importlib.util.spec_from_file_location('silverstar_scg_kf_horizon_fixture', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.core.__wrapped__(SimpleNamespace(param=request.param), tmp_path_factory)


def _Body(horizon, cycle, delta=(0., 0., 0.)):
    return horizon.Body_Receive(KfHorizonBody(START+(cycle-1)*5000, START+cycle*5000,
        np.asarray(delta, dtype=np.float32), np.float32(.005), 0, 1))


def _Event(time, receive, sequence, group, values=(.1, -.1), variance=(1., 1.)):
    return KfHorizonEvent(time, receive, sequence, sequence, 7, 1 if group == 4 else 0, 1,
        group, np.asarray(values, dtype=np.float32), np.asarray(variance, dtype=np.float32))


@pytest.mark.parametrize('field', ['value', 'prepared_variance'])
def test_values_outside_binary32_are_rejected_before_receipt_publication(field):
    horizon = _Horizon()
    assert _Body(horizon, 1) == HorizonResult.OK
    valid = _Event(START + 2500, START + 5000, 1, 0)
    invalid = replace(valid, **{field: np.array([1e300, 1.])})
    assert horizon.Insert(invalid) == HorizonResult.INVALID
    assert not horizon.measurements and not horizon.faulted
    # An invalid numeric API value must not consume this valid producer receipt.
    assert horizon.Insert(valid) == HorizonResult.QUEUED


def test_malformed_output_model_latches_fault_without_partial_primary_commit():
    horizon = _Horizon()
    assert _Body(horizon, 1) == HorizonResult.OK
    before = horizon.primary.state.copy(), horizon.primary.covariance.copy(), horizon.primary_us
    horizon.output.process_accel_std_mps2 = None
    assert horizon.Advance() == HorizonResult.EPOCH_MISMATCH
    assert horizon.Advance() == HorizonResult.NOT_READY
    np.testing.assert_array_equal(horizon.primary.state, before[0])
    np.testing.assert_array_equal(horizon.primary.covariance, before[1])
    assert horizon.primary_us == before[2]


def _SnapshotCompare(native, horizon):
    actual = native.snapshot()
    assert actual['times'] == [horizon.primary_us, horizon.output_us, horizon.present_us]
    for name, state in [('primary', horizon.primary), ('output', horizon.output)]:
        expected = np.r_[state.state, state.covariance.ravel()]
        np.testing.assert_allclose(actual[name], expected, rtol=3e-5, atol=3e-6)
        np.testing.assert_array_equal(state.covariance, state.covariance.T)
        np.linalg.cholesky(state.covariance)
    np.testing.assert_allclose(actual['accel'], horizon.output_acceleration, rtol=2e-6, atol=1e-7)
    assert actual['counts'][0] == len(horizon.steps)
    assert actual['counts'][3:5] == [int(horizon.faulted), int(horizon.warmup)]
    assert actual['counts'][5:7] == [horizon.last_work, horizon.maximum_work]


def _Drain(native, horizon):
    while True:
        result, ids, values = native.pop()
        own, completed = horizon.Completion_Pop()
        assert result == own.name.lower()
        if own == HorizonResult.EMPTY:
            break
        event, outcome = completed
        assert ids == [event.operation_sequence, event.source_sequence, event.group, event.source,
                       int(outcome.result), int(outcome.effective_update)]
        expected = np.r_[outcome.nis, outcome.robust_scale, outcome.innovation, outcome.effective_variance]
        np.testing.assert_allclose(values, expected, rtol=5e-5, atol=5e-6)


@pytest.mark.parametrize('lag', [10000, 30000, 32500])
def test_every_primary_output_state_covariance_and_completion_matches_actual_c(native, lag):
    assert native.reset(lag) == 'ok'; horizon = _Horizon(lag)
    sequence = 0
    for cycle in range(1, 181):
        delta = np.asarray([.001*np.sin(cycle*.1), .0005, -.0002], dtype=np.float32)
        assert native.body(START+(cycle-1)*5000, delta=delta) == 'ok'
        assert _Body(horizon, cycle, delta) == HorizonResult.OK
        if cycle % 7 == 0:
            sequence += 1; group = sequence % 5
            source = max(START+1, START+cycle*5000-lag+2500)
            event = _Event(source, START+cycle*5000, sequence, group)
            assert native.insert(source, event.receive_us, sequence=sequence, operation=sequence,
                source=event.source, group=group) == horizon.Insert(event).name.lower()
        assert native.advance() == horizon.Advance().name.lower()
        _SnapshotCompare(native, horizon)
        _Drain(native, horizon)


@pytest.mark.parametrize('group', range(5))
@pytest.mark.parametrize('value,variance', [(1., 1.), (2.2, 1.), (5., 1.), (1000., 1.), (1., 1e30)])
def test_normal_soft_hard_and_vanishing_gain_are_explicit_outcomes(native, group, value, variance):
    assert native.reset() == 'ok'; horizon = _Horizon()
    assert native.body(START) == 'ok' and _Body(horizon, 1) == HorizonResult.OK
    event = _Event(START+2500, START+5000, 1, group, (value, value), (variance, variance))
    assert native.insert(event.timestamp_us, event.receive_us, source=event.source, group=group,
        observation=event.value, variance=event.prepared_variance) == horizon.Insert(event).name.lower()
    for cycle in range(1, 8):
        if cycle > 1:
            assert native.body(START+(cycle-1)*5000) == 'ok' and _Body(horizon, cycle) == HorizonResult.OK
        assert native.advance() == horizon.Advance().name.lower()
        _SnapshotCompare(native, horizon); _Drain(native, horizon)


def test_output_never_feedback_and_corrupt_primary_fault_preserves_output(native):
    assert native.reset() == 'ok'; horizon = _Horizon()
    for cycle in range(1, 9):
        assert native.body(START+(cycle-1)*5000) == 'ok' and _Body(horizon, cycle) == HorizonResult.OK
        assert native.advance() == horizon.Advance().name.lower()
    native.lib.Test_KfCorrupt(7); horizon.output.state[0] = 12345; horizon.output.covariance[0, 0] = -1
    assert native.advance() == horizon.Advance().name.lower() == 'ok'
    _SnapshotCompare(native, horizon)
    before = horizon.output.state.copy(), horizon.output.covariance.copy()
    native.lib.Test_KfCorrupt(1); horizon.primary.covariance[0, 0] = -1
    assert native.advance() == horizon.Advance().name.lower() == 'numeric_error'
    np.testing.assert_array_equal(horizon.output.state, before[0])
    np.testing.assert_array_equal(horizon.output.covariance, before[1])


def test_completion_backpressure_and_duplicate_receipts_preserve_ownership(native):
    assert native.reset() == 'ok'; horizon = _Horizon(10000)
    assert native.reset(10000) == 'ok'
    for cycle in range(1, 4):
        assert native.body(START+(cycle-1)*5000) == 'ok' and _Body(horizon, cycle) == HorizonResult.OK
        if cycle == 1:
            event = _Event(START+2500, START+5000, 1, 0)
            assert native.insert(event.timestamp_us, event.receive_us) == horizon.Insert(event).name.lower() == 'queued'
            assert native.insert(event.timestamp_us, event.receive_us) == horizon.Insert(event).name.lower() == 'duplicate'
        assert native.advance() == horizon.Advance().name.lower()
    assert native.body(START+15000) == _Body(horizon, 4).name.lower() == 'busy'
    assert native.advance() == horizon.Advance().name.lower() == 'busy'
    _Drain(native, horizon)
    assert native.body(START+15000) == _Body(horizon, 4).name.lower() == 'ok'
