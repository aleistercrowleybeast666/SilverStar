"""Recorded initialization and body identity from fresh CPU backend streams.

The KF fixture explicitly produces raw intervals outside the INS scheduler.
These are real owning serializers and init writers, not onboard evidence.
"""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.decoder_profiles.fusion_horizon_records import FusionHorizonRecords_Validate
from silverstar_flp.plugins.algorithms.horizon_bodies import (
    EskfHorizonBodies_Build, KfHorizonBodies_Build, KfHorizon_RecordedInitialize,
)
from silverstar_flp.plugins.algorithms.horizon_timeline import HorizonTimeline_Run
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.pure_ins.mechanization import InertialIncrement_ReadRecorded
from tests.test_horizon_backend_numerics import (
    _Source_Require, _Frames_Read, _Parameters_Get, _Engine_Build, _Outputs_Compare,
)


def _Template(parameters):
    state = Kf6Filter.Kf6_Create(algorithm_revision=2,
        process_accel_std_mps2=np.array([parameters['process_accel_std_' + axis] for axis in ('e', 'n', 'u')]),
        p0_diagonal=np.ones(6), initial_velocity_enu_mps=np.zeros(3),
        nis_soft_threshold=np.array([parameters['nis_' + kind + '_soft'] for kind in ('1d', '2d', '3d')]),
        nis_hard_threshold=np.array([parameters['nis_' + kind + '_hard'] for kind in ('1d', '2d', '3d')]),
        nis_max_r_scale=parameters['nis_max_r_scale'], gnss_reacquire_outage_ms=parameters['gnss_reacquire_outage_ms'])
    state.require_effective_gain = True
    return state


def _Build(dataset, algorithm, evidence):
    first = evidence.statuses[0].payload
    if algorithm == 2:
        engine, _ = _Engine_Build(dataset, algorithm)
        bodies = EskfHorizonBodies_Build(dataset.Records_Get('ESKF15_BODY_INPUT'),
            source=engine.source, calibration_generation=engine.generation)
        return engine, bodies
    parameters = _Parameters_Get(algorithm)
    increments = InertialIncrement_ReadRecorded(dataset.Records_Get('INERTIAL_INCREMENT'), start_timestamp_us=1000000)
    assert increments
    engine, q = KfHorizon_RecordedInitialize(dataset, _Template(parameters), epoch=first['epoch'],
        source=first['source_id'], calibration_generation=first['calibration_generation'],
        start_us=increments[0].interval_start_timestamp_us, horizon_us=30000)
    bodies = KfHorizonBodies_Build(increments, dataset.Records_Get('ESTIMATOR_STEP'), evidence,
        epoch=engine.epoch, source=engine.source, calibration_generation=engine.generation,
        initial_q_nb=q, gravity_mps2=parameters['gravity_mps2'])
    return engine, bodies.bodies


@pytest.fixture(params=[(a, o, s) for a in (1, 2) for o in ('O0', 'O2') for s in (0, 9, 11)])
def actual(request):
    algorithm, optimization, scenario = request.param
    root = _Source_Require('SILVERSTAR_HORIZON_RECORDED_TRACE_ROOT')
    prefix = 'kf' if algorithm == 1 else 'eskf'
    paths = list(root.glob(f'{prefix}_backend_horizon-{optimization}*/case{scenario}.frames'))
    assert len(paths) == 1
    dataset = _Frames_Read(paths[0])
    evidence = FusionHorizonRecords_Validate(dataset, algorithm_id=algorithm, horizon_us=30000)
    assert not evidence.replay_blockers
    return dataset, algorithm, evidence


def test_complete_recorded_inputs_and_initial_state_match_every_c_output(actual):
    dataset, algorithm, evidence = actual
    engine, bodies = _Build(dataset, algorithm, evidence)
    result = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    assert result.failure is None and result.samples and not result.pending_operations
    _Outputs_Compare(dataset, algorithm, result.samples)


def test_recorded_source_and_body_sequence_mismatch_are_rejected_before_execution(actual):
    dataset, algorithm, evidence = actual
    engine, bodies = _Build(dataset, algorithm, evidence)
    if algorithm == 2:
        records = dataset.Records_Get('ESKF15_BODY_INPUT')
        first = records[0]
        wrong = replace(first, payload={**first.payload, 'source_id': engine.source + 1})
        with pytest.raises(ValueError, match='body_record_identity_mismatch'):
            EskfHorizonBodies_Build((wrong, *records[1:]), source=engine.source,
                calibration_generation=engine.generation)
    else:
        parameters = _Parameters_Get(algorithm)
        increments = InertialIncrement_ReadRecorded(dataset.Records_Get('INERTIAL_INCREMENT'), start_timestamp_us=1000000)
        steps = dataset.Records_Get('ESTIMATOR_STEP')
        with pytest.raises(ValueError, match='body_operation_incomplete|epoch_operation_start_missing|sequence_discontinuity'):
            KfHorizonBodies_Build(increments[1:], steps[1:], evidence, epoch=engine.epoch,
                source=engine.source, calibration_generation=engine.generation,
                initial_q_nb=np.array([1., 0., 0., 0.]), gravity_mps2=parameters['gravity_mps2'])
    assert engine.primary_us == engine.output_us == engine.initial_us
