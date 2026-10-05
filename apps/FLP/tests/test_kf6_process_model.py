"""Numerical and lifecycle contracts for the versioned interval process model."""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.plugins.algorithms.kf6.fixed_lag import (
    EpochState_Restore,
    Filter_Clone,
    FixedLagReplay,
)
from tests.test_kf6_outage import Filter_Create


def Revision2_Create():
    kf = Filter_Create()
    kf.algorithm_revision = 2
    return kf


def test_revision2_random_partition_preserves_all_state_and_full_covariance():
    random = np.random.default_rng(20261005)
    for _ in range(128):
        full = Revision2_Create()
        a = random.normal(size=(6, 6)).astype(np.float32) * .03
        full.covariance = a @ a.T + np.eye(6, dtype=np.float32) * .02
        full.state[:] = random.normal(size=6)
        split = Filter_Clone(full)
        h = float(random.uniform(.005, .09))
        delta = random.normal(size=3).astype(np.float32) * .01
        assert full.Kf6_Predict(delta, h, h)
        parts = random.dirichlet(np.ones(7)) * h
        parts[-1] = h - parts[:-1].sum()
        for part in parts:
            assert split.Kf6_Predict(delta * np.float32(part/h), part, h)
        np.testing.assert_allclose(split.state, full.state, rtol=2e-6, atol=2e-6)
        np.testing.assert_allclose(split.covariance, full.covariance, rtol=2e-6, atol=2e-6)
        assert np.linalg.eigvalsh(split.covariance).min() > 0


@pytest.mark.parametrize("original", [0, .009, np.nan, np.inf, .101])
def test_invalid_original_interval_does_not_publish_partial_state(original):
    kf = Revision2_Create()
    before = Filter_Clone(kf)
    assert not kf.Kf6_Predict(np.array([.1, .2, .3]), .01, original)
    np.testing.assert_array_equal(kf.state, before.state)
    np.testing.assert_array_equal(kf.covariance, before.covariance)
    assert kf.predict_count == before.predict_count
    assert kf.health_flags & 1


def test_model_revision_survives_clone_checkpoint_prune_and_epoch_restore(tmp_path):
    from tests.synthetic_parameter_navigation import NavigationPair_Open
    kf = Revision2_Create()
    replay = FixedLagReplay(kf, timestamp_us=1000000)
    for i in range(80):
        assert replay.Predict(1000000+(i+1)*10000, np.zeros(3), .01).value == 0
    assert len(replay.checkpoints) < 80
    assert all(state.algorithm_revision == 2 for _, state in replay.checkpoints)
    assert replay.state.algorithm_revision == replay.tracker.algorithm_revision == 2
    replay.state.algorithm_revision = 1
    assert not replay._ModelMatches()
    dataset = NavigationPair_Open(tmp_path/'epoch', flight_samples=3).dataset
    covariance = kf.covariance
    start = DecodedRecord(0, 'ESTIMATOR', 0, 0, 5, 0, 0, {
        'replay_epoch': 9, 'operation_sequence': 0,
        'position_enu_m': [1, 2, 3], 'velocity_enu_mps': [4, 5, 6], 'q_nb': [1, 0, 0, 0],
    }, 0)
    p = DecodedRecord(0, 'KF6_FULL_P', 0, 0, 6, 0, 0, {
        'covariance_upper_triangle': covariance[np.triu_indices(6)].tolist(),
    }, 0)
    dataset = replace(dataset, records={**dataset.records, 'ESTIMATOR': (start,), 'KF6_FULL_P': (p,)})
    restored, q = EpochState_Restore(dataset, 9, kf)
    assert restored.state.algorithm_revision == restored.tracker.algorithm_revision == 2
    assert restored.checkpoints[0][1].algorithm_revision == 2
    np.testing.assert_array_equal(restored.state.state, [1, 2, 3, 4, 5, 6])
    np.testing.assert_array_equal(restored.state.covariance, covariance)
    np.testing.assert_array_equal(q, [1, 0, 0, 0])
