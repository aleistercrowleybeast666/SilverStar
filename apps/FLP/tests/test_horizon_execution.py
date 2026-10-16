"""Product execution helpers with fresh staged C evidence, before UI admission.

The small plugin port deliberately bypasses package/parameter admission. These
tests establish execution/result semantics, not normal generation or LogOpen.
"""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from silverstar_flp.core.context import TaskContext
from silverstar_flp.plugins.algorithms.horizon_execution import KfHorizon_Run, EskfHorizon_Run
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest, ReplayFidelity
from tests.test_horizon_recorded_bodies import actual, _Build
from tests.test_horizon_backend_numerics import _Parameters_Get


def _Execute(dataset, algorithm, evidence, request, parameters=None, *, declared_horizon=30000):
    # Exact effective staged compiler configuration. Original package bytes are
    # still mode0/HMS300; this is not an admitted decoder identity.
    baseline = {**_Parameters_Get(algorithm), 'fusion_timing_mode': 2, 'fusion_horizon_ms': 30}
    parameters = {**baseline, **(parameters or {})}
    owner = 'silverstar.algorithm.' + ('kf6' if algorithm == 1 else 'eskf15')
    port = SimpleNamespace(metadata=SimpleNamespace(plugin_id=owner, version='staged-cpu-helper-only'),
        recorded_parameters=lambda ignored: dict(baseline),
        ParameterAudit_Get=lambda ignored, selected: {'test_scope': 'execution_helper_without_package_admission'})
    engine, bodies = _Build(dataset, algorithm, evidence)
    bounds = SimpleNamespace(start_timestamp_us=bodies[0].start_us, end_timestamp_us=bodies[-1].end_us)
    context = TaskContext()
    if algorithm == 1:
        from silverstar_flp.plugins.algorithms.pure_ins.mechanization import InertialIncrement_ReadRecorded
        increments = InertialIncrement_ReadRecorded(dataset.Records_Get('INERTIAL_INCREMENT'),
            start_timestamp_us=bodies[0].start_us)
        return KfHorizon_Run(port, dataset, request, parameters, {}, engine.primary, increments,
            context, bounds, recorded_horizon_us=declared_horizon)
    return EskfHorizon_Run(port, dataset, request, parameters, {}, engine.kernel,
        dataset.Records_Get('ESKF15_INITIAL_STATE')[0], context, bounds, recorded_horizon_us=declared_horizon)


def test_recorded_execution_returns_full_covariance_and_explicit_unknown_health(actual):
    dataset, algorithm, evidence = actual
    before = tuple(deepcopy(dict(row.payload)) for row in evidence.requests)
    result = _Execute(dataset, algorithm, evidence, ReplayRequest())
    prefix = 'kf6' if algorithm == 1 else 'eskf15'
    assert result.fidelity == ReplayFidelity.APPROXIMATE
    assert result.diagnostics['history_replay_count'] == 0 and result.diagnostics['output_feedback'] is False
    assert result.diagnostics['attempt_count'] == len(evidence.completions)
    assert result.diagnostics['effective_update_count'] == len(evidence.completions)
    assert result.channels[prefix + '.covariance.upper_triangle'].values.shape[1] == (21 if algorithm == 1 else 120)
    assert not result.channels[prefix + '.navigation_health'].valid.any()
    assert tuple(dict(row.payload) for row in evidence.requests) == before


def test_explicit_what_if_lag_is_separate_and_unreconstructible_noise_changes_block(actual):
    dataset, algorithm, evidence = actual
    request = ReplayRequest(ReplayMode.WHAT_IF, parameters={'fusion_horizon_ms': 10})
    result = _Execute(dataset, algorithm, evidence, request, {'fusion_horizon_ms': 10})
    assert result.provenance == 'What-if'
    assert result.diagnostics['recorded_horizon_us'] == 30000
    assert result.diagnostics['selected_horizon_us'] == 10000
    before = _Parameters_Get(algorithm)['gnss_velocity_std']
    request = ReplayRequest(ReplayMode.WHAT_IF, parameters={'gnss_velocity_std': before * 2})
    with pytest.raises(ValueError, match='receive_or_noise_recompute_unavailable'):
        _Execute(dataset, algorithm, evidence, request, {'gnss_velocity_std': before * 2})


def test_recorded_lag_actual_cannot_disagree_with_identity_even_during_warmup(actual):
    dataset, algorithm, evidence = actual
    with pytest.raises(ValueError, match='recorded_lag_mismatch'):
        _Execute(dataset, algorithm, evidence, ReplayRequest(), declared_horizon=40000)
