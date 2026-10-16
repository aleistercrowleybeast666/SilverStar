from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.horizon_result import HorizonChannels_Build
from silverstar_flp.plugins.algorithms.horizon_timeline import HorizonTimeline_Run, HorizonTimelineResult
from tests.test_horizon_timeline import _Inputs


@pytest.mark.parametrize('algorithm', [1, 2])
def test_primary_and_complete_output_covariance_have_their_actual_distinct_epochs(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    timeline = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    q = {body.end_us: np.array([1., 0., 0., 0.]) for body in bodies}
    channels = HorizonChannels_Build(timeline, algorithm, quaternions=q)
    prefix = 'kf6' if algorithm == 1 else 'eskf15'
    np.testing.assert_array_equal(channels['navigation.position_enu'].timestamp_us,
        [sample.timestamp_us for sample in timeline.samples])
    np.testing.assert_array_equal(channels[prefix + '.horizon.primary.navigation.position_enu'].timestamp_us,
        [sample.primary_timestamp_us for sample in timeline.samples])
    covariance = channels[prefix + '.covariance.upper_triangle']
    size = 6 if algorithm == 1 else 15
    np.testing.assert_array_equal(covariance.values[-1], timeline.samples[-1].output.covariance[np.triu_indices(size)])
    assert not covariance.values.flags.writeable
    health = channels[prefix + '.navigation_health']
    assert not health.valid.any()
    assert health.metadata['unavailable_reason'] == 'fusion_horizon_source_selection_health_evidence_unavailable'


@pytest.mark.parametrize('algorithm', [1, 2])
def test_queued_requests_do_not_create_completed_update_or_nis_channels(algorithm):
    engine, bodies, evidence = _Inputs(algorithm, count=3)
    timeline = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    channels = HorizonChannels_Build(timeline, algorithm,
        quaternions={body.end_us: np.array([1., 0., 0., 0.]) for body in bodies})
    prefix = 'kf6' if algorithm == 1 else 'eskf15'
    assert timeline.pending_operations == (1,) and not timeline.completions
    assert not any(name.startswith(prefix + '.nis.') for name in channels)
    assert not any(name.startswith(prefix + '.update_result.') for name in channels)


@pytest.mark.parametrize('algorithm', [1, 2])
def test_nis_rejection_is_an_attempt_with_zero_effective_updates(algorithm):
    engine, bodies, evidence = _Inputs(algorithm)
    original = evidence.requests[0]
    rejected = replace(original, payload={**original.payload, 'observation': [10000., 10000.]})
    evidence = replace(evidence, requests=(rejected,))
    timeline = HorizonTimeline_Run(engine, algorithm, bodies, evidence, strict_recorded=False)
    assert int(timeline.completions[0][2].result) == 2
    channels = HorizonChannels_Build(timeline, algorithm,
        quaternions={body.end_us: np.array([1., 0., 0., 0.]) for body in bodies})
    prefix = 'kf6' if algorithm == 1 else 'eskf15'
    measurement = prefix + '.measurement_' if algorithm == 1 else prefix + '.'
    assert channels[measurement + 'admitted.position_en'].values.tolist() == [1]
    assert channels[measurement + 'effective_update.position_en'].values.tolist() == [0]
    assert channels[prefix + '.update_result.position_en'].values.tolist() == [2]


def test_empty_or_missing_attitude_output_is_not_replaced_by_an_initial_or_zero_state():
    empty = HorizonTimelineResult((), (), (), (), None)
    with pytest.raises(ValueError, match='no_valid_output'):
        HorizonChannels_Build(empty, 1)
    engine, bodies, evidence = _Inputs(1)
    result = HorizonTimeline_Run(engine, 1, bodies, evidence)
    with pytest.raises(ValueError, match='attitude_epoch_missing'):
        HorizonChannels_Build(result, 1)
