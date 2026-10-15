"""Staged current-executor requirements; missing APIs are NOT legacy regressions.

Owner: /root/fusion_current_mode. Proposed APIs are listed in TEST_PLAN.md.
These tests call production executors; they contain no substitute current engine.
"""
from dataclasses import replace
from importlib import import_module

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    Filter_Clone, FixedLagReplay, ReplayEvent,
)
from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, DelayedReplay, Measurement


def _Current_Get(name):
    return import_module(f"silverstar_flp.plugins.algorithms.{name}.current_state").CurrentState


def _KfState_Create():
    return Kf6Filter.Kf6_Create(
        process_accel_std_mps2=np.ones(3) * .2, p0_diagonal=np.ones(6),
        initial_velocity_enu_mps=np.array([0, 0, 2]),
        nis_soft_threshold=np.array([4, 6, 8]),
        nis_hard_threshold=np.array([16, 20, 25]), nis_max_r_scale=10,
    )


def _Baro_Create(source_us=1_200_000, receive_us=1_500_000, sequence=1):
    return ReplayEvent(source_us, receive_us, sequence, 4, 1, {
        "relative_altitude_m": .1, "variance_m2": .1,
        "source_id": 1, "calibration_generation": 1,
    })


def _KfCurrent_Create():
    engine = _Current_Get("kf6")(_KfState_Create(), 1_000_000, epoch=1,
                                  calibration_generation=1)
    for index in range(1, 51):
        assert int(engine.Predict(1_000_000 + index * 10_000, [0, 0, .01], .01)) == 0
    return engine


def _Replay_Forbidden(*args, **kwargs):
    raise AssertionError("current execution entered a history replay method")


def test_kf6_current_is_present_update_and_differs_from_replay(monkeypatch):
    legacy = FixedLagReplay(_KfState_Create(), 1_000_000)
    for index in range(1, 51):
        assert int(legacy.Predict(1_000_000 + index * 10_000, [0, 0, .01], .01)) == 0
    event = _Baro_Create()
    assert int(legacy.Insert(event)) == 0
    monkeypatch.setattr(FixedLagReplay, "Predict", _Replay_Forbidden)
    monkeypatch.setattr(FixedLagReplay, "Insert", _Replay_Forbidden)
    engine = _KfCurrent_Create()
    reference = Filter_Clone(engine.state)
    reference.Kf6_UpdateBaro(.1, .1)
    assert int(engine.Insert(event)) == 0
    np.testing.assert_array_equal(engine.state.state, reference.state)
    np.testing.assert_array_equal(engine.state.covariance, reference.covariance)
    assert np.max(np.abs(engine.state.state - legacy.state.state)) > .01
    assert np.max(np.abs(engine.state.covariance - legacy.state.covariance)) > .01
    audit = engine.Audit_Get()
    assert audit["last_source_us"] == event.measurement_us
    assert audit["last_application_us"] == engine.present == 1_500_000
    assert audit["history_replay_count"] == audit["history_step_count"] == 0
    assert not any(getattr(engine, name, None) for name in ("events", "imu", "checkpoints"))


@pytest.mark.parametrize("source,receive,execution", [
    (1_000_000, 1_500_000, 0),  # source-age limit is inclusive
    (999_999, 1_500_000, 4),  # Before this mission epoch, not merely stale.
    (1_000_000, 1_000_000, 0),  # receive-age limit is inclusive
    (999_999, 999_999, 4),
    (1_500_001, 1_500_000, 1),
    (1_500_000, 1_500_001, 1),
    (0, 1_500_000, 1),
])
def test_kf6_current_age_and_time_order(source, receive, execution):
    engine = _KfCurrent_Create()
    before = Filter_Clone(engine.state)
    assert int(engine.Insert(_Baro_Create(source, receive))) == execution
    if execution:
        np.testing.assert_array_equal(engine.state.state, before.state)
        np.testing.assert_array_equal(engine.state.covariance, before.covariance)
        assert engine.Audit_Get()["last_application_us"] == 0


@pytest.mark.parametrize("payload", [
    {"relative_altitude_m": np.nan}, {"variance_m2": -1}, {"variance_m2": 0},
])
def test_kf6_invalid_observation_does_not_commit_partial_state(payload):
    engine = _KfCurrent_Create()
    event = _Baro_Create()
    event.payload.update(payload)
    before = Filter_Clone(engine.state)
    assert int(engine.Insert(event)) == 1
    np.testing.assert_array_equal(engine.state.state, before.state)
    np.testing.assert_array_equal(engine.state.covariance, before.covariance)


def test_kf6_duplicate_uses_producer_sequence_not_record_sequence():
    engine = _KfCurrent_Create()
    event = _Baro_Create()
    event.payload["record_sequence"] = 101
    assert int(engine.Insert(event)) == 0
    before = Filter_Clone(engine.state)
    duplicate = replace(event, payload={**event.payload, "record_sequence": 987})
    assert int(engine.Insert(duplicate)) == 3
    np.testing.assert_array_equal(engine.state.state, before.state)
    np.testing.assert_array_equal(engine.state.covariance, before.covariance)
    assert int(engine.Insert(replace(event, sequence=2))) == 0


def test_kf6_numeric_failure_is_full_state_transaction(monkeypatch):
    engine = _KfCurrent_Create()
    before = Filter_Clone(engine.state)
    present = engine.present

    def _BrokenPredict(state, *args, **kwargs):
        state.state[0] = 700
        state.covariance[0, 5] = 123
        return False

    monkeypatch.setattr(Kf6Filter, "Kf6_Predict", _BrokenPredict)
    assert int(engine.Predict(present + 10_000, [0, 0, .01], .01)) == 6
    assert engine.present == present
    np.testing.assert_array_equal(engine.state.state, before.state)
    np.testing.assert_array_equal(engine.state.covariance, before.covariance)


def _Body_Create(start=1_000_000):
    return BodyStep(start, start + 10_000, np.array([.8, -.3, .1]),
                    np.array([.1, .2, 9.78]), np.array([-.2, .6, .4]),
                    np.array([.2, .1, 9.78]), 0, 1, 0)


def _Measurement_Create(group=2, sequence=11):
    dimension = 2 if group in (0, 2) else 1
    return Measurement(key=(201, group), timestamp_us=1_002_000,
        receive_us=1_010_000, group=group, value=np.zeros(dimension),
        variance=np.ones(dimension), physically_valid=True, source=0, generation=1,
        source_sequence=sequence, mission_epoch=1)


def _EskfState_Equal(actual, expected):
    for name in ("p", "v", "q", "bg", "ba", "covariance"):
        np.testing.assert_allclose(getattr(actual, name), getattr(expected, name),
                                   rtol=1e-12, atol=1e-12)


def test_eskf_current_uses_endpoint_raw_gyro_and_latest_bias(monkeypatch):
    monkeypatch.setattr(DelayedReplay, "Body_Receive", _Replay_Forbidden)
    monkeypatch.setattr(DelayedReplay, "Measurement_Receive", _Replay_Forbidden)
    lever = np.array([.6, -.2, .3])
    kernel = Eskf15Filter()
    engine = _Current_Get("eskf15")(kernel, 1_000_000, epoch=1, lever_arm=lever)
    body = _Body_Create()
    engine.Body_Receive(body)
    expected = Eskf15Filter(kernel.state.State_Clone())
    expected.last_omega = body.gyro2.copy()
    # Deliberately change residual bias between groups: a cached debiased omega
    # and the existing pair-mean omega both give a different lever-arm model.
    for group, bias in ((2, [.02, -.03, .01]), (3, [-.04, .02, .06])):
        kernel.state.bg[:] = expected.state.bg[:] = bias
        measurement = _Measurement_Create(group)
        axes = (0, 1) if group == 2 else (2,)
        reference = expected.Measurement_Apply("velocity", axes,
            measurement.value, measurement.variance, physically_valid=True,
            lever_arm=lever, soft=(6.635, 9.21)[len(axes)-1],
            hard=(10.828, 13.816)[len(axes)-1], max_scale=4.0)
        actual = engine.Measurement_Receive(measurement)
        assert actual.result == reference.result
        np.testing.assert_allclose(actual.innovation, reference.innovation, rtol=1e-12, atol=1e-12)
        _EskfState_Equal(kernel.state, expected.state)
    np.testing.assert_array_equal(kernel.last_omega, body.gyro2)
    assert engine.Audit_Get()["history_replay_count"] == 0
    assert not any(getattr(engine, name, None) for name in ("steps", "measurements", "checkpoints"))


def test_eskf_same_packet_different_groups_are_independent_but_repeat_group_is_duplicate():
    engine = _Current_Get("eskf15")(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    for group in (0, 1, 2, 3):
        engine.Measurement_Receive(_Measurement_Create(group))
        assert engine.Audit_Get()["last_execution_result"] == 0
    before = engine.kernel.state.State_Clone()
    duplicate = replace(_Measurement_Create(2), key=(9999, 2))
    engine.Measurement_Receive(duplicate)
    assert engine.Audit_Get()["last_execution_result"] == 3
    _EskfState_Equal(engine.kernel.state, before)


def test_eskf_rejected_body_does_not_replace_endpoint_rate_or_full_covariance():
    engine = _Current_Get("eskf15")(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    before = engine.kernel.state.State_Clone()
    omega = engine.kernel.last_omega.copy()
    body = replace(_Body_Create(1_010_000), quality_flags=2)
    with pytest.raises(ValueError, match="quality"):
        engine.Body_Receive(body)
    assert engine.present_us == 1_010_000
    _EskfState_Equal(engine.kernel.state, before)
    np.testing.assert_array_equal(engine.kernel.last_omega, omega)


@pytest.mark.parametrize('value,variance', [(np.nan, 1), (0, -1), (0, 0)])
def test_eskf_kernel_invalid_retains_application_epoch_and_completed_execution(value, variance):
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    item = replace(_Measurement_Create(1), value=np.array([value]), variance=np.array([variance]))
    before = engine.kernel.state.State_Clone()
    result = engine.Measurement_Receive(item)
    assert int(result.result) == 3
    assert engine.Audit_Get()['last_execution_result'] == 0
    assert engine.Audit_Get()['last_application_us'] == 1_010_000
    _EskfState_Equal(engine.kernel.state, before)
    engine.Measurement_Receive(item)
    assert engine.Audit_Get()['last_execution_result'] == 3


def test_eskf_initial_epoch_has_no_fabricated_endpoint_rate():
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    result = engine.Measurement_Receive(replace(_Measurement_Create(),
        timestamp_us=1_000_000, receive_us=1_000_000))
    assert int(result.result) == 23  # 16 + NOT_READY, not a numerical update result.
    assert engine.Audit_Get()['last_application_us'] == 0
    assert engine.Audit_Get()['last_execution_result'] == 7


@pytest.mark.parametrize('source', [4, 255, 256, -1])
def test_current_gnss_source_rejects_outside_generated_capacity(source):
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    result = engine.Measurement_Receive(replace(_Measurement_Create(), source=source))
    assert int(result.result) == 17
    assert engine.Audit_Get()['last_execution_result'] == 1


def test_sequence_watermarks_survive_source_switch_and_uint32_wrap():
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    for source, sequence, execution in ((0, 0xffffffff, 0), (1, 1, 0),
            (0, 0xffffffff, 3), (0, 0, 0), (0, 0xffffffff, 5)):
        engine.Measurement_Receive(replace(_Measurement_Create(sequence=sequence), source=source))
        assert engine.Audit_Get()['last_execution_result'] == execution
    assert engine.Audit_Get()['producer_watermarks'] == 2


def test_kf_packet_receipt_rejection_cannot_be_bypassed_by_group_retry():
    engine = _KfCurrent_Create()
    p = dict(receive_timestamp_us=1_500_000, sequence=1, valid_group_mask=15,
        position_enu_m=[0, 0, 0], velocity_enu_mps=[0, 0, 0],
        position_variance_m2=[1, 1, 1], velocity_variance_m2ps2=[1, 1, 1],
        source_id=0, calibration_generation=1, replay_epoch=1)
    result, event = engine.Receive(p)
    assert int(result) == 0
    assert int(engine.Insert(replace(event, kind=1, measurement_us=999_999))) == 4
    result, repeat = engine.Receive(p)
    assert int(result) == 3
    assert int(engine.Insert(replace(repeat, kind=1, measurement_us=1_500_000))) == 3
    assert engine.Audit_Get()['last_application_us'] == 0


def test_kf_source_age_rejection_consumes_group_and_cannot_be_retimed():
    engine = _KfCurrent_Create()
    assert int(engine.Predict(1_510_000, [0, 0, .01], .01)) == 0
    item = _Baro_Create(source_us=1_000_000, receive_us=1_510_000)
    assert int(engine.Insert(item)) == 2
    assert int(engine.Insert(replace(item, measurement_us=1_510_000))) == 3


@pytest.mark.parametrize('failure', ['invalid', 'epoch', 'discontinuity'])
def test_kf_prediction_adapter_failures_never_commit_state_or_time(failure):
    engine = _KfCurrent_Create()
    before = Filter_Clone(engine.state)
    present = engine.present
    dt, timestamp, expected = .01, present + 10_000, 1
    if failure == 'invalid':
        dt = .2
    elif failure == 'epoch':
        engine.state.process_accel_std_mps2[0] += 1
        expected = 4
    else:
        timestamp += 1000
        expected = 5
    assert int(engine.Predict(timestamp, [0, 0, .01], dt)) == expected
    assert engine.present == present
    np.testing.assert_array_equal(engine.state.state, before.state)
    np.testing.assert_array_equal(engine.state.covariance, before.covariance)
    assert engine.faulted == (failure != 'invalid')


def test_eskf_a_b_a_packet_cannot_retry_an_earlier_physically_invalid_group():
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    first = replace(_Measurement_Create(0), physically_valid=False)
    engine.Measurement_Receive(first)
    assert engine.Audit_Get()['last_execution_result'] == 1
    engine.Measurement_Receive(replace(_Measurement_Create(0), source=1))
    assert engine.Audit_Get()['last_execution_result'] == 0
    engine.Measurement_Receive(replace(first, physically_valid=True, group=1,
        value=np.zeros(1), variance=np.ones(1)))
    assert engine.Audit_Get()['last_execution_result'] == 3
    assert engine.Audit_Get()['last_application_us'] == 0


@pytest.mark.parametrize('failure', ['model', 'discontinuity', 'quality', 'generation'])
def test_eskf_current_prediction_failure_latches_and_rejects_future_measurements(failure):
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    before = engine.kernel.state.State_Clone()
    body = _Body_Create(1_010_000)
    if failure == 'model':
        engine.kernel.gravity += .01
    elif failure == 'discontinuity':
        body = replace(body, start_us=body.start_us + 1)
    elif failure == 'quality':
        body = replace(body, quality_flags=2)
    else:
        body = replace(body, generation=body.generation + 1)
    with pytest.raises(ValueError):
        engine.Body_Receive(body)
    assert engine.faulted
    _EskfState_Equal(engine.kernel.state, before)
    assert engine.present_us == 1_010_000
    assert int(engine.Measurement_Receive(_Measurement_Create()).result) == 23
    with pytest.raises(ValueError, match='eskf_current_faulted'):
        engine.Body_Receive(_Body_Create(1_010_000))


@pytest.mark.parametrize('kernel_result', [4, 5])
def test_eskf_numeric_or_model_failure_rolls_back_and_latches_not_ready(monkeypatch, kernel_result):
    from silverstar_flp.plugins.algorithms.eskf15.filter import EskfMeasurementResult
    engine = _Current_Get('eskf15')(Eskf15Filter(), 1_000_000, epoch=1)
    engine.Body_Receive(_Body_Create())
    before = engine.kernel.state.State_Clone()
    def broken(candidate, *args, **kwargs):
        candidate.state.p[:] = 10
        candidate.state.covariance[0, 14] = 123
        return EskfMeasurementResult(kernel_result, np.zeros(2), 0, np.ones(2))
    monkeypatch.setattr(Eskf15Filter, 'Measurement_Apply', broken)
    result = engine.Measurement_Receive(_Measurement_Create())
    assert int(result.result) == kernel_result
    _EskfState_Equal(engine.kernel.state, before)
    assert engine.Audit_Get()['last_application_us'] == 1_010_000
    assert engine.Audit_Get()['last_execution_result'] == 6
    assert int(engine.Measurement_Receive(_Measurement_Create(1)).result) == 23
    with pytest.raises(ValueError, match='eskf_current_faulted'):
        engine.Body_Receive(_Body_Create(1_010_000))
