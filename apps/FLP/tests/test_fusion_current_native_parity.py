"""Actual-C kernel oracle and explicitly supplied actual backend trace checks.

Kernel-only tests do not establish backend or wire parity. The separate trace
test requires the firmware owner's exported log and exact generated decoder.
"""
import ctypes as ct
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfState
from silverstar_flp.plugins.algorithms.eskf15.replay import BodyStep, Measurement
from tests.eskf15_c_bridge import CCore
from tests.fccg_source_fixture import FccgCommon_RootGet


def test_actual_eskf_current_backend_trace_matches_state_covariance_and_timing(tmp_path):
    from silverstar_flp.decoder_profiles import DecoderProfileCache
    from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.plugins.api.algorithm import ReplayRequest, ReplayFidelity
    from silverstar_flp.plugins.algorithms.eskf15.verification import RecordedParity_Verify
    log_value, decoder_value = (os.environ.get(name) for name in (
        'SILVERSTAR_CURRENT_ESKF_TRACE', 'SILVERSTAR_CURRENT_ESKF_DECODER'))
    if not log_value or not decoder_value:
        pytest.skip('actual current backend trace and exact generated decoder not supplied; backend parity NOT PROVEN')
    log, decoder = Path(log_value).resolve(), Path(decoder_value).resolve()
    hashes = {str(path): sha256(path.read_bytes()).hexdigest() for path in (log, decoder)}
    registry = builtin_registry()
    dataset = LogOpenCoordinator(registry, cache=DecoderProfileCache(tmp_path / 'cache')).Open(
        LogOpenRequest(log_path=log, decoder_package_path=decoder)).dataset
    result = registry.Algorithm_Get('silverstar.algorithm.estimator.eskf15').run(dataset, ReplayRequest())
    parity = RecordedParity_Verify(dataset, result.channels)
    operations = result.diagnostics['fusion_timing_operations']
    records = dataset.Records_Get('ESKF15_MEASUREMENT')
    evidence = dict(scope='actual backend exported trace, exact wire opening, present executor',
        inputs=hashes, parity=parity, timing_operation_count=len(operations),
        record_count=len(records), fidelity=result.fidelity.value)
    (tmp_path / 'backend_parity.json').write_text(json.dumps(evidence, indent=2), encoding='utf8')
    assert parity['passed'], parity
    assert result.fidelity == ReplayFidelity.APPROXIMATE  # One host trace is no general exact/hardware claim.
    assert len(operations) == len(records) > 0
    assert result.diagnostics['history_replay_count'] == result.diagnostics['history_step_count'] == 0
    assert result.diagnostics['failure'] is None
    for operation, record in zip(operations, records, strict=True):
        p = record.payload
        assert p['fusion_timing_mode'] == 0
        for actual, expected in (('last_source_us', 'measurement_timestamp_us'),
                ('last_application_us', 'application_timestamp_us'),
                ('last_execution_result', 'execution_result'),
                ('operation_sequence', 'operation_sequence'), ('group', 'group'),
                ('source_id', 'source_id'), ('source_sequence', 'source_sequence'),
                ('mission_epoch', 'epoch'), ('calibration_generation', 'calibration_generation')):
            assert operation[actual] == p[expected], (p['operation_sequence'], actual, operation[actual], p[expected])
    assert {str(path): sha256(path.read_bytes()).hexdigest() for path in (log, decoder)} == hashes


def test_actual_kf_current_backend_trace_matches_state_covariance_and_timing(tmp_path):
    """Backend JSONL oracle, not a production log-open fallback or mission proof."""
    from dataclasses import replace
    from types import SimpleNamespace
    import struct
    import zlib
    from silverstar_flp.core.dataset import DecodedRecord
    from silverstar_flp.core.math import Quaternion_RotateVector, Quaternion_PropagateBodyIncrement
    from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
    from silverstar_flp.decoder_profiles.fusion_timing import FusionTiming_FromSemantics
    from silverstar_flp.decoder_profiles.fusion_timing_records import FusionTimingOperations_Get
    from silverstar_flp.plugins.algorithms.kf6.current_state import CurrentState
    from silverstar_flp.plugins.algorithms.kf6.filter import Kf6Filter
    from silverstar_flp.plugins.algorithms.kf6.fixed_lag import ReplayEvent, Faithful_Run
    from silverstar_flp.core.context import TaskContext
    selected = [os.environ.get(name) for name in ('SILVERSTAR_CURRENT_KF_TRACE', 'SILVERSTAR_CURRENT_KF_DECODER')]
    if not all(selected):
        pytest.skip('actual KF backend JSONL and generated decoder not supplied; backend parity NOT PROVEN')
    trace, decoder = map(lambda p: Path(p).resolve(), selected)
    hashes = {str(p): sha256(p.read_bytes()).hexdigest() for p in (trace, decoder)}
    package = DecoderProfilePackage.Load(decoder)
    identity = FusionTiming_FromSemantics(package.semantics.raw_metadata)
    assert identity.component.endswith('kf6') and identity.version == '0.3.0' and identity.mode == 0
    group = next(g for g in package.semantics.raw_metadata['firmware_algorithm_parameters']
                 if g['component'] == identity.component)
    params = {p['id']: p['value'] for p in group['parameters']}
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    initial = rows[0]
    assert initial['kind'] == 'state' and initial['cycle'] == 0
    state = Kf6Filter.Kf6_Create(
        process_accel_std_mps2=[params['process_accel_std_' + axis] for axis in 'enu'],
        p0_diagonal=np.diag(np.array(initial['P']).reshape(6, 6)),
        initial_velocity_enu_mps=initial['state'][3:],
        nis_soft_threshold=[params[f'nis_{d}d_soft'] for d in (1, 2, 3)],
        nis_hard_threshold=[params[f'nis_{d}d_hard'] for d in (1, 2, 3)],
        nis_max_r_scale=params['nis_max_r_scale'],
        gnss_reacquire_outage_ms=params['gnss_reacquire_outage_ms'], algorithm_revision=2,
        nis_soft_enabled=bool(params['nis_soft_enabled']), nis_hard_enabled=bool(params['nis_hard_enabled']))
    state.state[:] = initial['state']
    state.covariance[:] = np.array(initial['P']).reshape(6, 6)
    state.require_effective_gain = True
    engine = CurrentState(state, initial['time_us'], initial['epoch'],
                          calibration_generation=initial['calibration_generation'])
    q = np.asarray(initial['q'], dtype=np.float32)
    counts = dict(inputs=0, states=0, wire=0, measurements=0)
    maximum = dict(state=0., covariance=0., nis=0.)
    timing = []
    wire_records, increments, expected_states = {}, [], []
    inputs_by_cycle = {}
    prediction = None
    for row in rows[1:]:
        cycle = row['cycle']
        if row['kind'] == 'input':
            inputs_by_cycle[cycle] = row
            increments.append(SimpleNamespace(interval_end_timestamp_us=row['time_us'],
                delta_velocity_b=np.asarray(row['dv_body'], dtype=np.float32),
                delta_theta_b=np.asarray(row['dtheta_body'], dtype=np.float32), dt_s=row['dt_s']))
            dt = np.float32(row['dt_s'])
            dv = Quaternion_RotateVector(q, np.asarray(row['dv_body'], dtype=np.float32))
            dv[2] -= np.float32(params['gravity_mps2']) * dt
            q = Quaternion_PropagateBodyIncrement(q, np.asarray(row['dtheta_body'], dtype=np.float32))
            prediction = int(engine.Predict(row['time_us'], dv, dt))
            counts['inputs'] += 1
        elif row['kind'] == 'wire':
            wire = bytes.fromhex(row['hex'])
            assert wire[:4] == b'FLG1' and zlib.crc32(wire[:-4]) == int.from_bytes(wire[-4:], 'little')
            version, record_type, size = struct.unpack_from('<BBH', wire, 4)
            sequence, timestamp, flags = struct.unpack_from('<IQI', wire, 8)
            assert len(wire) == 28 + size and record_type == row['record_type']
            layout = package.catalog.Layout_Get(record_type, version)
            p = dict(layout.Decode(wire[24:-4]))
            record = DecodedRecord(record_type, layout.name, version, size, sequence, timestamp, flags, p, sequence)
            wire_records.setdefault(layout.name, []).append(record)
            counts['wire'] += 1
            if record_type == 30:
                assert p['source_sequence'] == inputs_by_cycle[cycle]['cycle']
                assert p['interval_end_timestamp_us'] == inputs_by_cycle[cycle]['time_us']
                # Identity-only adapter for real fixture input, explicitly not
                # a claim that this JSONL contains an INERTIAL_INCREMENT wire.
                wire_records.setdefault('INERTIAL_INCREMENT', []).append(replace(record,
                    record_name='INERTIAL_INCREMENT', payload=dict(sequence=p['source_sequence'],
                    interval_end_timestamp_us=p['interval_end_timestamp_us'])))
                assert prediction == p['replay_result'], (cycle, 'predict_result')
                assert engine.present == p['estimator_present_timestamp_us']
            if record_type not in (20, 21):
                continue
            FusionTimingOperations_Get(record, declared_mode=0)
            if record_type == 20:
                received, event = engine.Receive(p)
                assert {0: 0, 1: 1, 2: 2, 3: 1, 4: 4, 5: 5, 6: 6, 7: 1}[int(received)] == p['receive_result']
                parts = [(prefix, replace(event, kind=kind, measurement_us=p[prefix + 'source_timestamp_us']))
                         for prefix, kind in (('position_', 1), ('velocity_', 2))]
            else:
                parts = [('', ReplayEvent(p['source_timestamp_us'], p['receive_timestamp_us'],
                                          p['sequence'], 4, p['replay_epoch'], p))]
            for prefix, event in parts:
                execution = int(engine.Insert(event))
                audit = engine.Audit_Get()
                timing.append(dict(cycle=cycle, source=p['source_id'], sequence=p['sequence'],
                                   kind=event.kind, **audit))
                assert execution == p[prefix + 'execution_result'], (cycle, prefix, execution)
                assert audit['last_application_us'] == p[prefix + 'application_timestamp_us'], (cycle, prefix)
                assert audit['last_source_us'] == p[prefix + 'source_timestamp_us']
                if execution == 0:
                    if record_type == 21:
                        assert int(engine.last_outcome['baro']) == p['update_result']
                    else:
                        groups = (0, 1) if event.kind == 1 else (2, 3)
                        for g in groups:
                            assert int(engine.last_outcome['results'][g]) == p['group_update_result'][g]
            counts['measurements'] += 1
        elif row['kind'] == 'state':
            expected_states.append(row)
            for name, actual, expected in (
                    ('state', engine.state.state, row['state']),
                    ('covariance', engine.state.covariance, np.asarray(row['P']).reshape(6, 6)),
                    ('nis', engine.state.last_group_nis, row['nis'])):
                maximum[name] = max(maximum[name], float(np.max(np.abs(np.asarray(actual)-expected))))
                np.testing.assert_allclose(actual, expected, rtol=3e-4, atol=2e-4, err_msg=f'cycle={cycle} {name}')
            np.testing.assert_allclose(q, row['q'], rtol=3e-4, atol=2e-4)
            assert engine.present == row['time_us'] and engine.predictions == row['predict_count']
            assert engine.faulted == bool(row['faulted'])
            assert engine.replays == row['replay_count'] == 0
            counts['states'] += 1
        else:
            raise AssertionError('unknown backend trace row')
    assert counts['inputs'] == counts['states'] == 200 and counts['measurements'] > 0
    dataset = SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=package.semantics.raw_metadata),
                              Records_Get=lambda name: wire_records.get(name, ()))
    snapshots, final, runner_audit = Faithful_Run(dataset, state, np.asarray(initial['q'], dtype=np.float32),
                                                 increments, params, TaskContext())
    assert not runner_audit['execution_mismatches'], runner_audit['execution_mismatches']
    assert runner_audit['history_replay_count'] == 0 and len(snapshots) == len(expected_states)
    for snapshot, expected in zip(snapshots, expected_states, strict=True):
        assert snapshot.timestamp_us == expected['time_us']
        np.testing.assert_allclose(snapshot.state, expected['state'], rtol=3e-4, atol=2e-4)
        np.testing.assert_allclose(snapshot.covariance, np.array(expected['P']).reshape(6, 6), rtol=3e-4, atol=2e-4)
    assert {str(p): sha256(p.read_bytes()).hexdigest() for p in (trace, decoder)} == hashes
    (tmp_path/'kf_backend_parity.json').write_text(json.dumps(dict(
        scope='actual estimator_task pipeline trace; sensor/clock/mission activation fixture; not full mission log opening',
        inputs=hashes, counts=counts, maximum_absolute_error=maximum, timing=timing,
        history_replay_count=0, operation_runner_snapshot_count=len(snapshots),
        operation_runner_mismatches=runner_audit['execution_mismatches']), indent=2), encoding='utf8')


@pytest.fixture(scope="module", params=["-O0", "-O2"])
def current_native_kernel(request, tmp_path_factory):
    # Explicit source and compiler selection; no SDK/download or copied tree.
    selected = os.environ.get("SILVERSTAR_FCCG_ROOT")
    compiler = shutil.which("gcc")
    if not selected or not compiler:
        pytest.fail("new current parity prerequisite missing: select actual SCG root and GCC")
    root = Path(selected).resolve()
    core = root / "plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"
    quality = root / "plugins/builtin/silverstar_algorithm_common/payload/Algorithm/Common"
    common = FccgCommon_RootGet(root)
    output = tmp_path_factory.mktemp("current_kernel_" + request.param[1:])
    target = output / "native_current_kernel.dll"
    sources = [common / "Src/silverstar_assert.c", core / "Src/navigation_eskf.c",
               quality / "Src/navigation_quality.c"]
    command = [compiler, "-shared", "-std=c11", request.param, "-Wall", "-Wextra",
               "-Werror", "-static-libgcc"]
    for directory in (core / "Inc", quality / "Inc", common / "Inc"):
        command.extend(["-I", str(directory)])
    command.extend([*(str(path) for path in sources), "-o", str(target), "-lm"])
    version = subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True)
    result = subprocess.run(command, capture_output=True, text=True,
                            env={**os.environ, "TEMP": str(output), "TMP": str(output)})
    (output / "compile.log").write_text(result.stdout + result.stderr, encoding="utf8")
    evidence = {"scope": "actual C numerical core only; no backend parity claim",
        "command": command, "compiler": version.stdout, "exit_code": result.returncode,
        "source_sha256": {str(p): sha256(p.read_bytes()).hexdigest() for p in sources},
        "artifact_sha256": sha256(target.read_bytes()).hexdigest() if target.exists() else None}
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr
    return ct.CDLL(str(target))


def _State_Compare(core, kernel):
    for c_name, py_name in (("p", "p"), ("v", "v"), ("q", "q"), ("bg", "bg"), ("ba", "ba")):
        np.testing.assert_allclose(np.asarray(getattr(core.state, c_name)),
            getattr(kernel.state, py_name), rtol=2e-5, atol=2e-5)
    np.testing.assert_allclose(np.asarray(core.state.covariance), kernel.state.covariance,
                               rtol=2e-5, atol=2e-5)


@pytest.mark.parametrize("group", range(5))
def test_current_present_full_state_and_225_p_match_actual_c_kernel(current_native_kernel, group):
    CurrentState = import_module("silverstar_flp.plugins.algorithms.eskf15.current_state").CurrentState
    initial = EskfState()
    initial.bg[:] = [.003, -.002, .001]
    # SPD cross terms make dropping off-diagonal covariance observable.
    transform = np.eye(15)
    transform[0, 12], transform[3, 9], transform[4, 10] = .1, .2, -.15
    initial.covariance = transform @ initial.covariance @ transform.T
    core = CCore(current_native_kernel, initial)
    kernel = Eskf15Filter(initial)
    lever = np.array([.6, -.2, .3])
    engine = CurrentState(kernel, 1_000_000, epoch=1, lever_arm=lever)
    for index in range(20):
        gyro1 = np.array([.01, -.03, .1]) + index * .0001
        gyro2 = np.array([-.04, .02, .07]) - index * .0001
        accel1, accel2 = np.array([.2, -.1, 9.78]), np.array([.1, .2, 9.78])
        assert core.Predict(gyro1, accel1, gyro2, accel2) == 0
        start = 1_000_000 + index * 10_000
        engine.Body_Receive(BodyStep(start, start + 10_000, gyro1, accel1, gyro2, accel2, 0, 1, 0))
    count = 2 if group in (0, 2) else 1
    value, variance = np.full(count, .02), np.full(count, .7)
    c_status, outcome = core.Update(group, value, variance, gyro2,
                                   np.zeros(3) if group == 4 else lever)
    assert c_status == 0
    measured = engine.Measurement_Receive(Measurement((91, group), 1_050_000, 1_200_000,
        group, value, variance, True, source=1 if group == 4 else 0,
        generation=1, source_sequence=10, mission_epoch=1))
    assert int(measured.result) == outcome.result
    _State_Compare(core, kernel)
    assert engine.Audit_Get()["last_source_us"] == 1_050_000
    assert engine.Audit_Get()["last_application_us"] == 1_200_000
    assert engine.Audit_Get()["history_replay_count"] == 0


def test_current_nis_rejection_is_completed_attempt_with_unchanged_full_p(current_native_kernel):
    CurrentState = import_module("silverstar_flp.plugins.algorithms.eskf15.current_state").CurrentState
    core = CCore(current_native_kernel, EskfState())
    kernel = Eskf15Filter()
    engine = CurrentState(kernel, 1_000_000, epoch=1)
    gyro, accel = np.zeros(3), np.array([0, 0, 9.78])
    assert core.Predict(gyro, accel, gyro, accel) == 0
    engine.Body_Receive(BodyStep(1_000_000, 1_010_000, gyro, accel, gyro, accel, 0, 1, 0))
    before = kernel.state.State_Clone()
    status, outcome = core.Update(4, [1e4], [1], gyro, gyro)
    result = engine.Measurement_Receive(Measurement((5, 4), 1_001_000, 1_010_000,
        4, np.array([1e4]), np.ones(1), True, source=1, generation=1,
        source_sequence=5, mission_epoch=1))
    assert status == outcome.result == int(result.result) == 2
    assert engine.Audit_Get()["last_execution_result"] == 0
    assert engine.Audit_Get()["last_application_us"] == 1_010_000
    np.testing.assert_array_equal(kernel.state.covariance, before.covariance)
    _State_Compare(core, kernel)
