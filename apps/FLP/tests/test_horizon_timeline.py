"""Coordinator ownership/timing tests; numerical C parity is tested separately."""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.fusion_horizon_records import FusionHorizonRecords_Validate
from silverstar_flp.plugins.algorithms.horizon_timeline import HorizonTimeline_Run
from tests.test_fusion_horizon import engine_create, body_create
from tests.test_kf6_horizon import _Horizon, KfHorizonBody, START
from tests.test_fusion_horizon_records import _Record, _Completed, _Dataset, MEASUREMENT, STATUS


def _Inputs(algorithm, count=8, *, selected_lag=30000):
    engine = _Horizon(selected_lag) if algorithm == 1 else engine_create(selected_lag)
    bodies = tuple(KfHorizonBody(START + i * 5000, START + (i + 1) * 5000,
        np.zeros(3, dtype=np.float32), np.float32(.005), 0, 1) if algorithm == 1 else body_create(i)
        for i in range(count))
    common = dict(algorithm_id=algorithm, algorithm_revision=2 if algorithm == 1 else 1,
        numerical_revision=1 if algorithm == 1 else 2, epoch=engine.epoch, calibration_generation=1)
    request = _Record(MEASUREMENT, **common, sample_timestamp_us=START + 2500,
        measurement_timestamp_us=START + 2500, receive_timestamp_us=START + 5000,
        evaluation_timestamp_us=START + 5000, observation=[.1, -.1], prepared_variance=[2., 3.],
        quality_scale=3., consistency_scale=2.)
    records = [request]
    if count >= 7:
        completed = _Completed(request, evaluation_timestamp_us=START + 35000)
        records.append(replace(completed, file_offset=100))
    for index, body in enumerate(bodies):
        status = _Record(STATUS, **common, input_present_timestamp_us=body.end_us,
            output_state_timestamp_us=body.end_us, output_covariance_timestamp_us=body.end_us,
            primary_timestamp_us=max(START, body.end_us - 30000),
            phase=int(body.end_us - START >= 30000), execution_result=12 if body.end_us - START < 30000 else 0)
        records.append(replace(status, timestamp_us=body.end_us, file_offset=index * 20 + 10))
    evidence = FusionHorizonRecords_Validate(_Dataset(*records), algorithm_id=algorithm, horizon_us=30000)
    return engine, bodies, evidence


@pytest.mark.parametrize('algorithm', [1, 2])
def test_forward_cycle_owns_all_samples_and_matches_recorded_completion_epoch(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    result = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    assert result.failure is None and len(result.samples) == 8 and not result.pending_operations
    assert [item[0] for item in result.completions] == [START + 35000]
    assert result.samples[-1].primary_timestamp_us == START + 10000
    for sample in result.samples:
        assert sample.output_covariance_timestamp_us == sample.timestamp_us
        covariance = sample.output.covariance
        np.testing.assert_allclose(covariance, covariance.T, rtol=0, atol=1e-12)
        np.linalg.cholesky(covariance)
    if algorithm == 1:
        result.samples[0].output.state[:] = 999
        assert np.all(result.samples[1].output.state == 0)
    else:
        result.samples[0].output.p[:] = 999
        assert np.linalg.norm(result.samples[1].output.p) < 1


@pytest.mark.parametrize('algorithm', [1, 2])
def test_log_end_pending_ahead_of_primary_is_preserved(algorithm):
    engine, bodies, evidence = _Inputs(algorithm, count=3)
    result = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    assert result.pending_operations == (1,) and not result.completions and result.failure is None
    assert len(result.samples) == 3


@pytest.mark.parametrize('algorithm', [1, 2])
def test_missing_raw_interval_stops_before_any_invalid_output_publication(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    result = HorizonTimeline_Run(engine, algorithm, (*bodies[:3], *bodies[4:]), evidence)
    assert len(result.samples) == 3
    assert result.failure == {'timestamp_us': START + 25000, 'phase': 'body', 'result': 'DISCONTINUITY'}
    assert engine.output_us == START + 15000 and engine.faulted


@pytest.mark.parametrize('algorithm', [1, 2])
def test_explicit_what_if_lag_changes_application_cycle_without_rewriting_records(algorithm):
    engine, bodies, evidence = _Inputs(algorithm, selected_lag=10000)
    original = tuple((r.timestamp_us, dict(r.payload)) for r in (*evidence.requests, *evidence.completions))
    result = HorizonTimeline_Run(engine, algorithm, bodies, evidence, strict_recorded=False)
    assert result.failure is None and [item[0] for item in result.completions] == [START + 15000]
    assert tuple((r.timestamp_us, dict(r.payload)) for r in (*evidence.requests, *evidence.completions)) == original


@pytest.mark.parametrize('algorithm', [1, 2])
def test_recorded_lag_cannot_silently_use_a_different_primary_epoch(algorithm):
    engine, bodies, evidence = _Inputs(algorithm, selected_lag=10000)
    with pytest.raises(ValueError, match='committed_epoch_mismatch'):
        HorizonTimeline_Run(engine, algorithm, bodies, evidence)


@pytest.mark.parametrize('algorithm', [1, 2])
def test_recorded_status_cannot_borrow_another_imu_source_identity(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    first = evidence.statuses[0]
    wrong = replace(first, payload={**first.payload, 'source_id': engine.source + 1})
    changed = replace(evidence, statuses=(wrong, *evidence.statuses[1:]))
    with pytest.raises(ValueError, match='committed_epoch_mismatch'):
        HorizonTimeline_Run(engine, algorithm, bodies, changed)
    assert engine.primary_us == engine.output_us == engine.present_us == START


@pytest.mark.parametrize('algorithm', [1, 2])
def test_explicit_what_if_fallback_delay_keeps_recorded_time_and_result_separate(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    request = _Record(MEASUREMENT, algorithm_id=algorithm,
        algorithm_revision=2 if algorithm == 1 else 1, numerical_revision=1 if algorithm == 1 else 2,
        epoch=engine.epoch, calibration_generation=engine.generation,
        measurement_timestamp_us=START + 8000, timing_flags=9)
    completed = _Completed(request)
    changed = replace(evidence, requests=(request,), completions=(completed,))
    result = HorizonTimeline_Run(engine, algorithm, bodies, changed, strict_recorded=False,
        changed_delays_ms={0: 6})
    assert result.failure is None
    assert [(time, event.timestamp_us) for time, event, _ in result.completions] == [(START + 35000, START + 4000)]
    assert result.operations[0]['source_timestamp_us'] == START + 4000
    assert result.operations[0]['recorded_source_timestamp_us'] == START + 8000
    assert request.payload['measurement_timestamp_us'] == START + 8000


def test_recorded_mode_rejects_a_delay_override_before_mutating_any_epoch():
    engine, bodies, evidence = _Inputs(1)
    with pytest.raises(ValueError, match='recorded_override_forbidden'):
        HorizonTimeline_Run(engine, 1, bodies, evidence, changed_delays_ms={0: 7})
    assert engine.present_us == engine.initial_us
