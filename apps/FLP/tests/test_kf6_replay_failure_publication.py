"""Small recorded-operation counterexamples; no mission replay or hardware claim."""
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from silverstar_flp.core.context import TaskContext
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter, Kf6GnssGroup, Kf6UpdateResult
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import Faithful_Run, FixedLagReplay, ReplayEvent, ReplayResult
from silverstar_flp.plugins.algorithms.kf6.measurement_time import MeasurementDelays_Apply
from tests.test_audit_block_artifacts import _Fingerprint


def _Configuration(revision=2):
    return dict(process_accel_std_mps2=np.full(3, .2), p0_diagonal=np.ones(6),
        initial_velocity_enu_mps=np.array([0., 0., 2.]),
        nis_soft_threshold=np.array([4., 6., 8.]), nis_hard_threshold=np.array([16., 20., 25.]),
        nis_max_r_scale=10., algorithm_revision=revision)


def _Payload():
    return dict(receive_timestamp_us=500000, sample_timestamp_us=500000, sequence=7,
        replay_epoch=1, receive_operation_sequence=2, position_operation_sequence=3,
        velocity_operation_sequence=3, estimator_present_timestamp_us=500000,
        position_measurement_timestamp_us=500000, velocity_measurement_timestamp_us=500000,
        receive_result=0, position_replay_result=0, velocity_replay_result=0, replay_generation=0,
        valid_group_mask=15, position_enu_m=(1., 2., .03), velocity_enu_mps=(0., 0., 2.),
        position_variance_m2=(1., 1., 1.), velocity_variance_m2ps2=(.1, .1, .1),
        _quality_source_id='explicit-synthetic-gnss')


def _Record(name, sequence, payload):
    return DecodedRecord(1, name, 1, 0, sequence, 500000, 0, payload, 0)


@dataclass(frozen=True)
class _Scheduled:
    record: DecodedRecord


def _Faithful(payload=None, *, velocity_delay=0, position_delay=0, revision=2, baro=None):
    payload = _Payload() if payload is None else payload
    step = _Record('ESTIMATOR_STEP', 1, dict(replay_epoch=1, operation_sequence=1,
        estimator_present_timestamp_us=500000, source_sequence=1,
        interval_end_timestamp_us=500000, attitude_result=1, replay_result=0))
    native = _Record('GNSS_NATIVE', 9, dict(sequence=7, receive_timestamp_us=500000,
        measurement_timestamp_trusted=False))
    gnss = _Record('GNSS_MEASUREMENT', 10, payload)
    dataset = FlightDataset(Path('synthetic-operations'), 0, {}, ParserDiagnostics(),
        {'ESTIMATOR_STEP': (step,), 'GNSS_MEASUREMENT': (gnss,), 'GNSS_NATIVE': (native,),
         'INERTIAL_INCREMENT': (_Record('INERTIAL_INCREMENT', 2,
            dict(sequence=1, interval_end_timestamp_us=500000)),)}, {})
    if baro is not None:
        dataset = replace(dataset, records={**dataset.records, 'BARO_MEASUREMENT': (
            _Record('BARO_MEASUREMENT', 11, dict(replay_epoch=1, operation_sequence=4,
                estimator_present_timestamp_us=500000, receive_timestamp_us=500000,
                measurement_timestamp_us=500000, sequence=8, relative_altitude_m=baro,
                variance_m2=1., replay_result=0, replay_generation=0)),)})
    params = dict(gravity_mps2=9.80665, gnss_position_measurement_delay_ms=position_delay,
        gnss_velocity_measurement_delay_ms=velocity_delay, baro_measurement_delay_ms=0)
    adjusted = MeasurementDelays_Apply(dataset, (_Scheduled(gnss),), params,
        {**params, 'gnss_velocity_measurement_delay_ms': 0, 'gnss_position_measurement_delay_ms': 0})
    dataset = replace(dataset, records={**dataset.records,
        'GNSS_MEASUREMENT': tuple(item.record for item in adjusted)})
    increment = SimpleNamespace(interval_end_timestamp_us=500000, dt_s=.01,
        delta_velocity_b=np.array([0., 0., .0980665], dtype=np.float32),
        delta_theta_b=np.zeros(3, dtype=np.float32))
    return Faithful_Run(dataset, Kf6Filter.Kf6_Create(**_Configuration(revision)),
        np.array([1., 0., 0., 0.]), (increment,), params, TaskContext())


def test_what_if_old_velocity_history_miss_does_not_swallow_present_position():
    snapshots, state, diagnostics = _Faithful(velocity_delay=270)
    assert np.any(state.state[:2] != 0), 'Position at present must still update'
    rows = {row['group']: row for row in diagnostics['measurement_events']}
    for name in ('position_en', 'position_u'):
        assert rows[name]['replay_result'] == ReplayResult.OK and rows[name]['committed']
        assert rows[name]['result'] in (0, 1)
    for name in ('velocity_en', 'velocity_u'):
        assert rows[name]['replay_result'] == ReplayResult.HISTORY_MISS and not rows[name]['committed']
        assert rows[name]['result'] == Kf6UpdateResult.REJECTED_INVALID
        assert np.isnan(rows[name]['effective_variance']).all()
    assert snapshots[-1].position_result in (0, 1)
    assert snapshots[-1].velocity_result == Kf6UpdateResult.REJECTED_INVALID
    assert list(snapshots[-1].group_result[2:]) == [5, 5]
    assert [(row['kind'], row['replay_result']) for row in diagnostics['measurement_operations']] == [(2, 2), (1, 0)]


@pytest.mark.parametrize('rejection', [ReplayResult.INVALID, ReplayResult.OVERFLOW])
def test_split_nonfatal_admission_rejection_keeps_other_operation(monkeypatch, rejection):
    insert = FixedLagReplay.Insert
    def reject_velocity(self, event):
        if event.kind == 2:
            self.last_outcome = {}
            return rejection
        return insert(self, event)
    monkeypatch.setattr(FixedLagReplay, 'Insert', reject_velocity)
    _, state, diagnostics = _Faithful(velocity_delay=270)
    assert np.any(state.state[:2] != 0)
    assert [(row['kind'], row['replay_result']) for row in diagnostics['measurement_operations']] == [(2, int(rejection)), (1, 0)]


@pytest.mark.parametrize('failure', [ReplayResult.EPOCH_MISMATCH, ReplayResult.DISCONTINUITY,
                                    ReplayResult.NUMERIC_ERROR, ReplayResult.WORK_LIMIT])
def test_split_fatal_failure_stops_later_operation(monkeypatch, failure):
    calls = []
    def fail_older(self, event):
        calls.append(event.kind)
        self.last_outcome = {}
        # Epoch mismatch must stop even if Insert did not latch faulted.
        self.faulted = failure != ReplayResult.EPOCH_MISMATCH
        return failure
    monkeypatch.setattr(FixedLagReplay, 'Insert', fail_older)
    _, _, diagnostics = _Faithful(velocity_delay=270)
    assert calls == [2]
    rows = {row['group']: row for row in diagnostics['measurement_events']}
    assert rows['velocity_en']['replay_result'] == failure and not rows['velocity_en']['committed']
    assert rows['position_en']['replay_result'] is None and not rows['position_en']['operation_attempted']


def test_numeric_combined_insert_discards_accepted_partial_outcome_and_state():
    engine = FixedLagReplay(Kf6Filter.Kf6_Create(**_Configuration()))
    assert engine.Predict(500000, [0., 0., 0.], .01) == ReplayResult.OK
    payload = {**_Payload(), 'velocity_enu_mps': (1.e20, 0., 2.)}
    status, received = engine.Receive(payload)
    assert status == ReplayResult.OK
    before = _Fingerprint(engine.state)
    with np.errstate(over='ignore', invalid='ignore'):
        assert engine.Insert(replace(received, measurement_us=500000, kind=3)) == ReplayResult.NUMERIC_ERROR
    assert engine.faulted and engine.last_outcome == {}
    assert _Fingerprint(engine.state) == before


def test_faithful_uncommitted_position_before_numeric_velocity_is_not_accepted():
    payload = {**_Payload(), 'velocity_enu_mps': (1.e20, 0., 2.)}
    with np.errstate(over='ignore', invalid='ignore'):
        snapshots, state, diagnostics = _Faithful(payload)
    assert not np.any(state.state[:2])
    for row in diagnostics['measurement_events']:
        assert not row['committed'] and row['result'] == Kf6UpdateResult.REJECTED_INVALID
        assert row['replay_result'] == ReplayResult.NUMERIC_ERROR
        assert np.isnan(row['effective_variance']).all()
    assert snapshots[-1].position_result == snapshots[-1].velocity_result == Kf6UpdateResult.NUMERIC_ERROR
    assert list(snapshots[-1].group_result) == [5]*4


def test_split_preserves_earlier_committed_position_when_later_velocity_faults():
    payload = {**_Payload(), 'velocity_enu_mps': (1.e20, 0., 2.)}
    with np.errstate(over='ignore', invalid='ignore'):
        snapshots, state, diagnostics = _Faithful(payload, position_delay=10)
    assert np.any(state.state[:2] != 0)
    rows = {row['group']: row for row in diagnostics['measurement_events']}
    assert rows['position_en']['committed'] and rows['position_en']['result'] in (0, 1)
    assert not rows['velocity_en']['committed'] and rows['velocity_en']['result'] == 3
    assert snapshots[-1].position_result in (0, 1) and snapshots[-1].velocity_result == 4
    assert [(row['kind'], row['replay_result']) for row in diagnostics['measurement_operations']] == [(1, 0), (2, 6)]


@pytest.mark.parametrize('baro, replay_result, group_result, aggregate', [(1.e20, 6, 3, 4), (100., 0, 2, 2)])
def test_faithful_baro_numeric_failure_and_ordinary_nis_rejection(baro, replay_result, group_result, aggregate):
    reference_snapshots, reference_state, _ = _Faithful()
    with np.errstate(over='ignore', invalid='ignore'):
        snapshots, state, diagnostics = _Faithful(baro=baro)
    row = next(row for row in diagnostics['measurement_events'] if row['group'] == 'baro')
    assert row['replay_result'] == replay_result and row['result'] == group_result
    assert row['committed'] == (replay_result == 0)
    assert snapshots[-1].baro_result == aggregate and np.isnan(row['effective_variance']).all()
    np.testing.assert_array_equal(state.state, reference_state.state)
    np.testing.assert_array_equal(state.covariance, reference_state.covariance)
    np.testing.assert_array_equal(snapshots[-1].group_result, reference_snapshots[-1].group_result)


def test_later_historical_event_failure_clears_inserted_accepted_outcome(monkeypatch):
    engine = FixedLagReplay(Kf6Filter.Kf6_Create(**_Configuration()))
    assert engine.Predict(10000, [0., 0., 0.], .01) == ReplayResult.OK
    later = ReplayEvent(8000, 10000, 1, 4, 1, {'relative_altitude_m': .03, 'variance_m2': 1.})
    assert engine.Insert(later) == ReplayResult.OK
    before = _Fingerprint(engine.state)
    monkeypatch.setattr(Kf6Filter, 'Kf6_UpdateBaro', lambda *args: Kf6UpdateResult.NUMERIC_ERROR)
    _, received = engine.Receive({**_Payload(), 'receive_timestamp_us': 10000})
    assert engine.Insert(replace(received, measurement_us=5000, kind=1)) == ReplayResult.NUMERIC_ERROR
    assert engine.faulted and engine.last_outcome == {}
    assert _Fingerprint(engine.state) == before


@pytest.mark.parametrize('field', ['process_accel_std_mps2', 'p0_diagonal',
    'initial_velocity_enu_mps', 'nis_soft_threshold', 'nis_hard_threshold', 'nis_max_r_scale'])
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 1.e300])
def test_create_rejects_nonfinite_float32_configuration_or_initial_state(field, bad):
    configuration = _Configuration()
    if field == 'nis_max_r_scale': configuration[field] = bad
    else:
        value = configuration[field].copy(); value[0] = bad; configuration[field] = value
    with np.errstate(over='ignore', invalid='ignore'):
        with pytest.raises(ValueError, match='kf6_configuration_invalid'):
            Kf6Filter.Kf6_Create(**configuration)


def test_covariance_repair_does_not_accept_float32_symmetry_overflow():
    state = Kf6Filter.Kf6_Create(**_Configuration())
    state.covariance = np.eye(6, dtype=np.float32)*np.float32(2.e38)
    with np.errstate(over='ignore', invalid='ignore'):
        assert not state._Covariance_Repair()


def test_nonfinite_baro_nis_is_numeric_failure_without_state_update():
    state = Kf6Filter.Kf6_Create(**_Configuration())
    before = (state.state.copy(), state.covariance.copy())
    with np.errstate(over='ignore', invalid='ignore'):
        assert state.Kf6_UpdateBaro(1.e20, 1.) == Kf6UpdateResult.NUMERIC_ERROR
    np.testing.assert_array_equal(state.state, before[0])
    np.testing.assert_array_equal(state.covariance, before[1])


def test_finite_large_baro_nis_remains_ordinary_rejection():
    state = Kf6Filter.Kf6_Create(**_Configuration())
    assert state.Kf6_UpdateBaro(100., 1.) == Kf6UpdateResult.REJECTED_NIS


@pytest.mark.parametrize('revision', [1, 2])
def test_normal_recorded_combined_state_and_diagnostics_control(revision):
    snapshots, state, diagnostics = _Faithful(revision=revision)
    assert len(snapshots) == 1 and not diagnostics['execution_mismatches']
    assert list(snapshots[-1].group_result) == [0]*4
    assert all(row['result'] == 0 for row in diagnostics['measurement_events'])
    fingerprint = _Fingerprint((snapshots, state))
    # Exact pre-fix 45778d3 fingerprints, recorded in the complete before log.
    expected = {1: 'c3e6d483291544d1a6402e9a31b8463dadf14635cfcb8d35734341a42f644ed8',
                2: '47aebe3aa2d5337050078d3786ea66206e2576e5a7dbfc5655b9f3c6ae81af5c'}
    assert fingerprint == expected[revision]
    print('NORMAL_CONTROL', revision, fingerprint)
