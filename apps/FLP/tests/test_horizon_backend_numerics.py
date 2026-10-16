"""Fresh actual backend frames through trusted inputs and both Python engines.

CPU fixtures with explicit staged mode2 compiler flags. KF raw intervals and its
initial zero state/P0 below are explicit test_estimator_horizon.c inputs, not
reconstructed log evidence. The configuration packages remain mode0; no production opening or
normally generated mode2 admission is claimed by this test.
"""
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile
import zlib

import numpy as np
import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.catalog import RecordLayout
from silverstar_flp.decoder_profiles.fusion_horizon_records import FusionHorizonRecords_Validate
from silverstar_flp.plugins.algorithms.horizon_timeline import HorizonTimeline_Run
from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfNoise, EskfState
from silverstar_flp.plugins.algorithms.eskf15.horizon import DelayedHorizon, HorizonBody
from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
from silverstar_flp.plugins.algorithms.kf6.horizon import DelayedKfHorizon, KfHorizonBody


def _Source_Require(name):
    value = os.environ.get(name)
    assert value, 'Explicit fresh source/configuration evidence required: ' + name
    result = Path(value).resolve()
    assert result.is_dir()
    return result


def _Frames_Read(path):
    source = _Source_Require('SILVERSTAR_FCCG_ROOT')
    document = json.loads((source / 'plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/'
        'Protocol/SSLOG/schema/sslog_schema.json').read_text(encoding='utf-8'))
    layouts = {int(row['id'], 0): RecordLayout.FromDocument(row, 0) for row in document['records']}
    data = path.read_bytes()
    records, cursor = [], 0
    while cursor < len(data):
        sync, version, kind, size, sequence, timestamp, flags = struct.unpack_from('<IBBHIQI', data, cursor)
        total = 28 + size
        assert sync == 0x31474c46 and cursor + total <= len(data)
        assert zlib.crc32(data[cursor:cursor+total-4]) == struct.unpack_from('<I', data, cursor+total-4)[0]
        layout = layouts[kind]
        assert (layout.record_version, layout.payload_size) == (version, size)
        records.append(DecodedRecord(kind, layout.name, version, size, sequence, timestamp, flags,
            layout.Decode(data[cursor+24:cursor+24+size]), cursor))
        cursor += total
    return SimpleNamespace(Records_Get=lambda name: tuple(r for r in records if r.record_name == name))


def _Parameters_Get(algorithm):
    selected = 'SILVERSTAR_HORIZON_KF_STAGE_PROJECT' if algorithm == 1 else 'SILVERSTAR_HORIZON_STAGE_PROJECT'
    project = _Source_Require(selected)
    packages = list(project.glob('*.ssdecoder'))
    assert len(packages) == 1
    with zipfile.ZipFile(packages[0]) as archive:
        semantics = json.loads(archive.read('project_semantics.json'))
    owner = 'silverstar.algorithm.estimator.' + ('kf6' if algorithm == 1 else 'eskf15')
    actual = next(row for row in semantics['firmware_algorithm_parameters'] if row['component'] == owner)
    return {row['id']: row['value'] for row in actual['parameters']}


def _Covariance_FromParts(parts, state):
    values = np.empty(120)
    covered = np.zeros(120, dtype=bool)
    for record in parts:
        p = record.payload
        if p['snapshot_id'] != state.payload['snapshot_id']:
            continue
        assert record.timestamp_us == state.timestamp_us
        for key in ('epoch', 'source_id', 'calibration_generation', 'algorithm_id'):
            assert p[key] == state.payload[key]
        start, count = p['offset'], p['count']
        assert count == 30 and not covered[start:start+count].any()
        values[start:start+count] = p['values'][:count]
        covered[start:start+count] = True
    assert covered.all()
    result = np.zeros((15, 15))
    result[np.triu_indices(15)] = values
    result += np.triu(result, 1).T
    return result


def _Engine_Build(dataset, algorithm):
    parameters = _Parameters_Get(algorithm)
    f32 = lambda value: float(np.float32(value))
    dimensions = ('1d', '2d', '3d') if algorithm == 1 else ('1d', '2d')
    soft = tuple(f32(parameters['nis_' + size + '_soft']) for size in dimensions)
    hard = tuple(f32(parameters['nis_' + size + '_hard']) for size in dimensions)
    statuses = dataset.Records_Get('FUSION_HORIZON_STATUS')
    first = statuses[0].payload
    if algorithm == 1:
        assert dataset.Records_Get('ESTIMATOR')[0].timestamp_us == 1005000
        p0 = [parameters['p0_' + group + '_' + axis]
              for group in ('position', 'velocity') for axis in ('e', 'n', 'u')]
        state = Kf6Filter.Kf6_Create(algorithm_revision=2,
            process_accel_std_mps2=np.array([parameters['process_accel_std_' + axis] for axis in ('e', 'n', 'u')]),
            p0_diagonal=np.array(p0), initial_velocity_enu_mps=np.zeros(3),
            nis_soft_threshold=np.array(soft), nis_hard_threshold=np.array(hard),
            nis_max_r_scale=parameters['nis_max_r_scale'],
            gnss_reacquire_outage_ms=parameters['gnss_reacquire_outage_ms'])
        state.require_effective_gain = True
        engine = DelayedKfHorizon(state, 1000000, epoch=first['epoch'], source=first['source_id'],
            generation=first['calibration_generation'], horizon_us=30000)
        ends = [r.payload['interval_end_timestamp_us'] for r in dataset.Records_Get('ESTIMATOR_STEP')]
        bodies = tuple(KfHorizonBody(end-5000, end, np.zeros(3, dtype=np.float32), np.float32(.005),
            first['source_id'], first['calibration_generation']) for end in ends)
        return engine, bodies
    initial = dataset.Records_Get('ESKF15_INITIAL_STATE')[0]
    p = initial.payload
    state = EskfState(np.array(p['position_enu_m']), np.array(p['velocity_enu_mps']), np.array(p['q_nb']),
        np.array(p['gyro_bias_radps']), np.array(p['accel_bias_mps2']),
        _Covariance_FromParts(dataset.Records_Get('ESKF15_INITIAL_P_PART'), initial))
    kernel = Eskf15Filter(state, gravity=f32(parameters['gravity_mps2']),
        noise=EskfNoise(*(f32(parameters[name]) for name in
            ('gyro_noise_density', 'accel_noise_density', 'gyro_bias_rw', 'accel_bias_rw'))))
    inputs = dataset.Records_Get('ESKF15_BODY_INPUT')
    engine = DelayedHorizon(kernel, inputs[0].payload['interval_start_timestamp_us'], epoch=first['epoch'],
        horizon_us=30000, source=first['source_id'], generation=first['calibration_generation'],
        soft=soft[:2], hard=hard[:2], max_r_scale=f32(parameters['nis_max_r_scale']))
    bodies = []
    for record in inputs:
        p = record.payload
        gyro, accel = np.asarray(p['body_gyro_radps']), np.asarray(p['body_accel_mps2'])
        bodies.append(HorizonBody(p['interval_start_timestamp_us'], p['interval_end_timestamp_us'],
            gyro[:3].copy(), accel[:3].copy(), gyro[3:].copy(), accel[3:].copy(), p['source_id'],
            p['calibration_generation'], p['quality_flags'], p['dt_s']))
    return engine, tuple(bodies)


@pytest.mark.parametrize('algorithm,prefix', [(1, 'kf'), (2, 'eskf')])
@pytest.mark.parametrize('optimization', ['O0', 'O2'])
@pytest.mark.parametrize('scenario', [0, 9, 11])
def test_actual_backend_complete_output_covariance_uses_recorded_prepared_r(algorithm, prefix, optimization, scenario):
    root = _Source_Require('SILVERSTAR_HORIZON_TRACE_ROOT')
    paths = list(root.glob(f'{prefix}_backend_horizon-{optimization}*/case{scenario}.frames'))
    assert len(paths) == 1
    dataset = _Frames_Read(paths[0])
    evidence = FusionHorizonRecords_Validate(dataset, algorithm_id=algorithm, horizon_us=30000)
    assert not evidence.replay_blockers
    engine, bodies = _Engine_Build(dataset, algorithm)
    result = HorizonTimeline_Run(engine, algorithm, bodies, evidence)
    assert result.failure is None and result.samples and not result.pending_operations
    _Outputs_Compare(dataset, algorithm, result.samples)


def _Outputs_Compare(dataset, algorithm, samples):
    for sample in samples:
        if algorithm == 1:
            actual = next(r for r in dataset.Records_Get('ESTIMATOR') if r.timestamp_us == sample.timestamp_us)
            actual_p = next(r for r in dataset.Records_Get('KF6_FULL_P') if r.timestamp_us == sample.timestamp_us)
            np.testing.assert_allclose(sample.output.state,
                [*actual.payload['position_enu_m'], *actual.payload['velocity_enu_mps']], rtol=8e-5, atol=3e-6)
            packed = actual_p.payload['covariance_upper_triangle']
            covariance = np.zeros((6, 6)); covariance[np.triu_indices(6)] = packed
            covariance += np.triu(covariance, 1).T
        else:
            actual = next(r for r in dataset.Records_Get('ESKF15_STATE') if r.timestamp_us == sample.timestamp_us)
            for attribute, field in (('p', 'position_enu_m'), ('v', 'velocity_enu_mps'), ('q', 'q_nb'),
                                     ('bg', 'gyro_bias_radps'), ('ba', 'accel_bias_mps2')):
                np.testing.assert_allclose(getattr(sample.output, attribute), actual.payload[field], rtol=8e-5, atol=3e-6)
            covariance = _Covariance_FromParts(dataset.Records_Get('ESKF15_FULL_P_PART'), actual)
        np.testing.assert_allclose(sample.output.covariance, covariance, rtol=8e-5, atol=3e-6)
