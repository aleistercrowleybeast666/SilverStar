from dataclasses import replace

import numpy as np

from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    FixedLagReplay,
    ReplayEvent,
    ReplayResult,
)
from silverstar_flp.plugins.algorithms.kf6.measurement_time import MeasurementTime_Resolve


def state_create():
    return Kf6Filter.Kf6_Create(process_accel_std_mps2=np.ones(3)*.2,
        p0_diagonal=np.ones(6), initial_velocity_enu_mps=np.array([0,0,2]),
        nis_soft_threshold=np.array([4,6,8]), nis_hard_threshold=np.array([16,20,25]),
        nis_max_r_scale=10)


def test_delayed_baro_restores_x_p_and_internal_state():
    reference, delayed, incorrect = (FixedLagReplay(state_create()) for _ in range(3))
    event = ReplayEvent(200000, 500000, 1, 4, 1, {'relative_altitude_m': .1, 'variance_m2': .1})
    for index in range(1, 51):
        for engine in (reference, delayed, incorrect):
            assert engine.Predict(index*10000, [0,0,.01], .01) == ReplayResult.OK
        if index == 20:
            assert reference.Insert(replace(event, receive_us=200000)) == ReplayResult.OK
    assert delayed.Insert(event) == ReplayResult.OK
    incorrect.state.Kf6_UpdateBaro(.1, .1)  # Timestamp correction alone cannot pass.
    np.testing.assert_allclose(delayed.state.state, reference.state.state, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(
        delayed.state.covariance, reference.state.covariance, rtol=1e-6, atol=1e-6
    )
    assert np.max(np.abs(incorrect.state.state-reference.state.state)) > .01
    assert np.max(np.abs(incorrect.state.covariance-reference.state.covariance)) > .01
    assert delayed.replays == 1


def test_mixed_gnss_baro_sorting_and_unchanged_invalid_state():
    a, b = (FixedLagReplay(state_create()) for _ in range(2))
    p={'receive_timestamp_us':500000,'sequence':1,'valid_group_mask':15,
       'position_enu_m':[.1,.2,.3],'velocity_enu_mps':[0,0,2],
       'position_variance_m2':[1,1,1],'velocity_variance_m2ps2':[.1,.1,.1]}
    for engine in (a,b):
        for index in range(1,51):
            assert engine.Predict(index*10000,[0,0,.001],.01) == ReplayResult.OK
    _, ea = a.Receive(p)
    _, eb = b.Receive(p)
    baro=ReplayEvent(230000,500000,2,4,1,{'relative_altitude_m':.5,'variance_m2':1})
    for engine, event, order in ((a,ea,(1,4,2)),(b,eb,(2,1,4))):
        for kind in order:
            item = (
                baro
                if kind == 4
                else replace(event, kind=kind, measurement_us=200000 if kind == 1 else 270000)
            )
            assert engine.Insert(item)==ReplayResult.OK
    np.testing.assert_allclose(a.state.state,b.state.state,rtol=1e-6,atol=1e-6)
    np.testing.assert_allclose(a.state.covariance,b.state.covariance,rtol=1e-6,atol=1e-6)
    before = a.state.state.copy()
    assert (
        a.Insert(
            replace(baro, sequence=4, payload={"relative_altitude_m": np.nan, "variance_m2": 1})
        )
        == ReplayResult.INVALID
    )
    np.testing.assert_array_equal(before,a.state.state)
    assert a.Insert(replace(baro,epoch=2)) == ReplayResult.EPOCH_MISMATCH


def test_trusted_native_clock_is_not_delayed_twice():
    assert MeasurementTime_Resolve(500000,200000,True,100,500000)==200000
    assert MeasurementTime_Resolve(500000,200000,False,100,500000)==400000
    assert MeasurementTime_Resolve(500000,200000,False,0,490000)==490000


def test_epoch_reset_requires_explicit_initial_x_p_and_resets_internal_evidence():
    from pathlib import Path

    from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
    from silverstar_flp.core.diagnostics import ParserDiagnostics
    from silverstar_flp.plugins.algorithms.kf6.fixed_lag import EpochState_Restore
    state = state_create()
    state.reanchor_counts[0] = 3
    payload = dict(replay_epoch=2, operation_sequence=0, position_enu_m=[1,2,3],
                   velocity_enu_mps=[4,5,6], q_nb=[1,0,0,0])
    snapshot = DecodedRecord(4,'ESTIMATOR',1,0,100,0,0,payload,0)
    covariance = np.diag([2,3,4,5,6,7]).astype(np.float32)
    full = DecodedRecord(8,'KF6_FULL_P',0,0,101,0,0,
                          {'covariance_upper_triangle':covariance[np.triu_indices(6)]},0)
    dataset = FlightDataset(Path('synthetic'),0,{},ParserDiagnostics(),
                            {'ESTIMATOR':(snapshot,), 'KF6_FULL_P':(full,)},{})
    history, q = EpochState_Restore(dataset, 2, state)
    np.testing.assert_array_equal(history.state.state,[1,2,3,4,5,6])
    np.testing.assert_array_equal(history.state.covariance,covariance)
    assert history.state.reanchor_counts == [0]*4
    assert history.events == [] and history.present == 0 and history.epoch == 2
    np.testing.assert_array_equal(q,[1,0,0,0])
    import pytest
    with pytest.raises(ValueError, match='epoch_initial_state_missing'):
        EpochState_Restore(dataset, 3, state)
    with pytest.raises(ValueError, match='epoch_covariance_missing'):
        EpochState_Restore(replace(dataset, records={'ESTIMATOR':(snapshot,)}), 2, state)


def test_replay_rejects_history_miss_capacity_and_mutated_model():
    engine = FixedLagReplay(state_create())
    for index in range(1, 101):
        assert engine.Predict(index*10000,[0,0,0],.01) == ReplayResult.OK
    event = ReplayEvent(100000,1000000,1,4,1,{'relative_altitude_m':0,'variance_m2':1})
    assert engine.Insert(event) == ReplayResult.HISTORY_MISS
    engine.state.nis_max_r_scale *= 2
    assert engine.Insert(replace(event,measurement_us=1000000)) == ReplayResult.EPOCH_MISMATCH
    assert engine.Predict(1010000,[0,0,0],.01) == ReplayResult.EPOCH_MISMATCH
    full = FixedLagReplay(state_create())
    assert full.Predict(10000,[0,0,0],.01) == ReplayResult.OK
    for sequence in range(160):
        assert full.Insert(replace(event,measurement_us=10000,sequence=sequence)) == ReplayResult.OK
    assert full.Insert(replace(event,measurement_us=10000,sequence=160)) == ReplayResult.OVERFLOW
