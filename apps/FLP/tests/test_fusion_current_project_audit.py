"""Staged optional timing parameter and historical project boundary tests.

The captured old values are synthetic OFFLINE configuration, never recorded data.
Full v2 Recorded/What-if numerical audit awaits the actual backend trace fixture.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
import numpy as np

from silverstar_flp.core.project import Project_Load, Project_Save, ReplayConfiguration_Validate
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.parameter_fixtures import ParameterPackage_Open
from tests.sslog_synthetic import StationaryFlight_Build
from tests.test_project_export import _ProjectDocument_Build


# Captured before activation at cb53daf3; synthetic offline defaults only.
_BEFORE = {'kf6': {'plugin_id': 'silverstar.algorithm.kf6',
         'plugin_version': '0.2.0-firmware-SILV0008',
         'accepted_schema_identities': ['627f701414ec781735f595a398e4a5595a80e04a37ad9c4d8d5b2e1d7b95fec0',
                                        '06c8d6f27b77aab96f00ea8d2e83329907b2413d86af12541a80bc3b8a780fce',
                                        '6d98b8898d681c4191ccd7e95fd8fcee1f94273010e99fe70e11257728c3c02d'],
         'synthetic_offline_actual_values': {'gravity_mps2': 9.78,
                                             'p0_position_e': 4.0,
                                             'p0_position_n': 4.0,
                                             'p0_position_u': 9.0,
                                             'p0_velocity_e': 0.25,
                                             'p0_velocity_n': 0.25,
                                             'p0_velocity_u': 0.25,
                                             'process_accel_std_e': 1.5,
                                             'process_accel_std_n': 1.5,
                                             'process_accel_std_u': 2.0,
                                             'gnss_position_std_horizontal': 1.5,
                                             'gnss_position_std_vertical': 2.5,
                                             'gnss_velocity_std': 0.15,
                                             'gnss_velocity_vertical_scale': 1.0,
                                             'gnss_reacquire_outage_ms': 300,
                                             'baro_std_m': 5.0,
                                             'nis_1d_soft': 6.635,
                                             'nis_1d_hard': 10.828,
                                             'nis_2d_soft': 9.21,
                                             'nis_2d_hard': 13.816,
                                             'nis_3d_soft': 11.345,
                                             'nis_3d_hard': 16.266,
                                             'nis_max_r_scale': 10.0,
                                             'gnss_position_measurement_delay_ms': 0,
                                             'gnss_velocity_measurement_delay_ms': 270,
                                             'baro_measurement_delay_ms': 0,
                                             'gnss_integrity_enable': 1,
                                             'gnss_integrity_max_gap_ms': 120,
                                             'gnss_integrity_error_threshold_m': 10.0,
                                             'gnss_integrity_recovery_threshold_m': 4.0,
                                             'gnss_integrity_suspect_duration_ms': 2000,
                                             'gnss_integrity_reject_duration_ms': 5000,
                                             'gnss_integrity_recovery_duration_ms': 8000,
                                             'gnss_integrity_position_r_scale': 4.0,
                                             'gnss_integrity_hacc_max_m': 6.0,
                                             'gnss_integrity_sacc_max_mps': 1.2,
                                             'nis_soft_enabled': 1,
                                             'nis_hard_enabled': 1}},
 'eskf15': {'plugin_id': 'silverstar.algorithm.estimator.eskf15',
            'plugin_version': '1.0.0',
            'accepted_schema_identities': ['ebd0c2654046a0d23eb59ff712152778a651089f70c7483e9ed7e3bc3ad9b1f0',
                                           'f8874d4727673fa9d37511afe38092d874ecd1ac729a0dfad6256c6b3d624e26'],
            'synthetic_offline_actual_values': {'gravity_mps2': 9.78,
                                                'gyro_noise_density': 0.003,
                                                'accel_noise_density': 0.08,
                                                'gyro_bias_rw': 0.0001,
                                                'accel_bias_rw': 0.001,
                                                'p0_position_e': 4,
                                                'p0_position_n': 4,
                                                'p0_position_u': 9,
                                                'p0_velocity_e': 0.25,
                                                'p0_velocity_n': 0.25,
                                                'p0_velocity_u': 0.25,
                                                'p0_theta_x': 0.030461742,
                                                'p0_theta_y': 0.030461742,
                                                'p0_theta_z': 0.030461742,
                                                'p0_gyro_bias_x': 0.0001,
                                                'p0_gyro_bias_y': 0.0001,
                                                'p0_gyro_bias_z': 0.0001,
                                                'p0_accel_bias_x': 0.01,
                                                'p0_accel_bias_y': 0.01,
                                                'p0_accel_bias_z': 0.01,
                                                'gnss_position_std_horizontal': 1.5,
                                                'gnss_position_std_vertical': 2.5,
                                                'gnss_velocity_std': 0.15,
                                                'baro_std_m': 2.5,
                                                'nis_1d_soft': 6.635,
                                                'nis_1d_hard': 10.828,
                                                'nis_2d_soft': 9.21,
                                                'nis_2d_hard': 13.816,
                                                'nis_max_r_scale': 4,
                                                'lever_arm_body_x_m': 0.0,
                                                'lever_arm_body_y_m': 0.0,
                                                'lever_arm_body_z_m': 0.0,
                                                'gnss_position_measurement_delay_ms': 0,
                                                'gnss_velocity_measurement_delay_ms': 270,
                                                'baro_measurement_delay_ms': 0,
                                                'nis_soft_enabled': 1,
                                                'nis_hard_enabled': 1}}}

def _Before_Get():
    return deepcopy(_BEFORE)


def _Plugin_Get(name):
    return builtin_registry().Algorithm_Get(_Before_Get()[name]["plugin_id"])


@pytest.mark.parametrize("name", ["kf6", "eskf15"])
def test_only_two_estimators_gain_optional_integer_timing_parameter(name):
    plugin = _Plugin_Get(name)
    spec = next(p for p in plugin.metadata.parameter_schema if p.parameter_id == "fusion_timing_mode")
    assert (spec.kind, spec.default, spec.minimum, spec.maximum, spec.unit, spec.required) == (
        "int", 1, 0, 1, "1", False)
    for value in (0, 1):
        spec.Value_Validate(value)
    for value in (True, False, 2, -1, .0, "0"):
        with pytest.raises(ValueError):
            spec.Value_Validate(value)


def test_sf6_pureins_have_no_timing_mode():
    allowed = {_Before_Get()[name]["plugin_id"] for name in ("kf6", "eskf15")}
    for plugin in builtin_registry().algorithms:
        if plugin.metadata.plugin_id in allowed:
            continue
        assert "fusion_timing_mode" not in {p.parameter_id for p in plugin.metadata.parameter_schema}
        with pytest.raises(ValueError, match="unknown"):
            plugin.metadata.Parameters_Validate({"fusion_timing_mode": 0}, complete=False)


@pytest.mark.parametrize("name", ["kf6", "eskf15"])
def test_pre_activation_schema_identities_remain_accepted_but_unknown_does_not(name):
    before = _Before_Get()[name]
    plugin = _Plugin_Get(name)
    assert plugin.metadata.version == before["plugin_version"]
    for identity in before["accepted_schema_identities"]:
        assert plugin.ParameterSchemaCompatible_Is(identity)
    assert not plugin.ParameterSchemaCompatible_Is("0" * 64)


def _Configuration_Create(name, mode=None):
    before = _Before_Get()[name]
    plugin = _Plugin_Get(name)
    values = deepcopy(before["synthetic_offline_actual_values"])
    if mode is not None:
        values["fusion_timing_mode"] = mode
    return {
        "algorithm_id": plugin.metadata.plugin_id,
        "algorithm_version": before["plugin_version"],
        "mode": ReplayMode.OFFLINE.value,
        "input_source": "corrected_imu",
        "actual_values": values,
        "parameter_schema_identity": (before["accepted_schema_identities"][0]
            if mode is None else plugin.metadata.ParameterSchemaIdentity_Get()),
        "provenance": "Algorithm Plugin actual defaults",
    }


@pytest.mark.parametrize("name", ["kf6", "eskf15"])
@pytest.mark.parametrize("mode", [None, 0, 1])
def test_saved_configuration_preserves_absence_or_exact_selected_mode(tmp_path, name, mode):
    configuration = _Configuration_Create(name, mode)
    ReplayConfiguration_Validate(configuration)
    log = StationaryFlight_Build(tmp_path / "SYNTHETIC_current_project.BIN")
    original = log.read_bytes()
    path = tmp_path / "timing.ssflp"
    document = _ProjectDocument_Build(log, path)
    result_id = name + ":offline:1"
    document.replay_configurations[result_id] = deepcopy(configuration)
    Project_Save(document, path)
    loaded = Project_Load(path)
    assert loaded.replay_configurations[result_id] == configuration
    assert log.read_bytes() == original
    assert ("fusion_timing_mode" in loaded.replay_configurations[result_id]["actual_values"]) == (mode is not None)


@pytest.mark.parametrize("name", ["kf6", "eskf15"])
def test_old_recorded_values_do_not_gain_an_offline_default(tmp_path, name):
    opened = ParameterPackage_Open(tmp_path)
    plugin = _Plugin_Get(name)
    recorded = plugin.recorded_parameters(opened.dataset)
    assert "fusion_timing_mode" not in recorded
    original = dict(recorded)
    resolved = plugin.Parameters_Resolve(opened.dataset, ReplayRequest())
    assert "fusion_timing_mode" not in resolved
    assert dict(plugin.recorded_parameters(opened.dataset)) == original
    with pytest.raises(ValueError, match="override_forbidden"):
        plugin.Parameters_Resolve(opened.dataset, ReplayRequest(parameters={"fusion_timing_mode": 0}))


@pytest.mark.parametrize("name", ["kf6", "eskf15"])
def test_project_cannot_select_unimplemented_delayed_predictor(name):
    configuration = _Configuration_Create(name, 2)
    with pytest.raises(ValueError):
        ReplayConfiguration_Validate(configuration)


def _EskfSynthetic_Create(tmp_path, recorded_mode=0):
    """Unit-only composition; exact wire opening is covered in the v2 module."""
    from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
    from silverstar_flp.core.diagnostics import ParserDiagnostics
    from tests.parameter_fixtures import FirmwareSets_Build
    from tests.test_fusion_timing_contract import _TimingDocument, ESKF15
    from tests.test_fusion_timing_records_v2 import _Record_Create
    context = ParameterPackage_Open(tmp_path / 'base').dataset.semantic_context
    document = _TimingDocument(ESKF15, recorded_mode)
    group = next(g for g in FirmwareSets_Build() if g['component'] == ESKF15)
    group['parameters'].extend(document['firmware_algorithm_parameters'][0]['parameters'])
    document['firmware_algorithm_parameters'] = [group]
    context = replace(context, firmware_algorithm_ids=(ESKF15,), raw_metadata=document)
    def record(name, timestamp, payload, sequence=0):
        return DecodedRecord(1, name, 0, 0, sequence, timestamp, 0, payload, sequence)
    p0 = np.array([p['value'] for p in group['parameters'] if p['id'].startswith('p0_')])
    initial = record('ESKF15_INITIAL_STATE', 1_000_000, dict(algorithm_id=2,
        algorithm_revision=1, quality_revision=3, snapshot_id=1, epoch=3,
        source_id=0, calibration_generation=7, position_enu_m=[0, 0, 0],
        velocity_enu_mps=[0, 0, 0], q_nb=[1, 0, 0, 0], gyro_bias_radps=[0, 0, 0],
        accel_bias_mps2=[0, 0, 0]))
    body = tuple(record('ESKF15_BODY_INPUT', 1_000_000+i*10_000,
        dict(interval_start_timestamp_us=1_000_000+(i-1)*10_000,
             interval_end_timestamp_us=1_000_000+i*10_000, dt_s=.01,
             body_gyro_radps=[0, 0, .01, 0, 0, .02],
             body_accel_mps2=[0, 0, 9.78, 0, 0, 9.78],
             source_id=0, calibration_generation=7, quality_flags=0), i)
        for i in range(1, 51))
    observation = _Record_Create('ESKF15_MEASUREMENT', recorded_mode)
    observations = tuple(replace(observation, record_sequence=i+1, payload={**observation.payload,
        'group': i, 'operation_sequence': i+1, 'observation': [.1, -.1]}) for i in range(4))
    initial_p = TimeSeries(np.array([1_000_000]), np.array([np.diag(p0)[np.triu_indices(15)]]),
        'mixed', 'covariance', 'synthetic', np.array([True]), metadata={
            'snapshot_identities': [(1_000_000, 1, 2, 3, 0, 7, 0)]})
    clock = TimeSeries(np.array([1_500_000]), np.array([0]), '1', 'time', 'synthetic', np.array([True]))
    return FlightDataset(tmp_path / 'synthetic-composed', 0, {}, ParserDiagnostics(),
        {'EVENT': (record('EVENT', 1_000_000, {'event_id': 3}),),
         'ESKF15_INITIAL_STATE': (initial,), 'ESKF15_BODY_INPUT': body,
         'ESKF15_MEASUREMENT': observations},
        {'eskf15.initial.covariance.upper_triangle': initial_p, 'synthetic.clock': clock},
        semantic_context=context)


@pytest.mark.parametrize('recorded_mode', [0, 1])
def test_eskf_plugin_current_run_audits_recorded_and_selected_modes_without_replay(tmp_path, monkeypatch, recorded_mode):
    from silverstar_flp.plugins.algorithms.eskf15.replay import DelayedReplay
    from silverstar_flp.plugins.api.algorithm import ReplayFidelity
    dataset = _EskfSynthetic_Create(tmp_path, recorded_mode)
    original = dict(dataset.Records_Get('ESKF15_MEASUREMENT')[0].payload)
    def forbidden(*args, **kwargs):
        raise AssertionError('current plugin entered delayed replay')
    monkeypatch.setattr(DelayedReplay, 'Body_Receive', forbidden)
    monkeypatch.setattr(DelayedReplay, 'Measurement_Receive', forbidden)
    request = ReplayRequest() if recorded_mode == 0 else ReplayRequest(
        mode=ReplayMode.WHAT_IF, parameters={'fusion_timing_mode': 0})
    result = _Plugin_Get('eskf15').run(dataset, request)
    assert not result.diagnostics['failure']
    assert result.parameters['fusion_timing_mode'] == 0
    assert result.diagnostics['recorded_fusion_timing_mode'] == recorded_mode
    assert result.diagnostics['fusion_timing_mode'] == 0
    assert result.diagnostics['history_replay_count'] == result.diagnostics['maximum_history_steps'] == 0
    assert result.fidelity == ReplayFidelity.APPROXIMATE
    operation = result.diagnostics['fusion_timing_operations'][0]
    assert (operation['last_source_us'], operation['last_application_us']) == (1_200_000, 1_500_000)
    assert (operation['source_id'], operation['source_sequence'], operation['calibration_generation']) == (0, 12, 7)
    assert dict(dataset.Records_Get('ESKF15_MEASUREMENT')[0].payload) == original


def test_eskf_plugin_initial_not_ready_and_epoch_rejection_remain_explicit_operations(tmp_path):
    dataset = _EskfSynthetic_Create(tmp_path)
    final = dataset.Records_Get('ESKF15_MEASUREMENT')[0]
    initial = replace(final, record_sequence=0, timestamp_us=1_000_000, payload={**final.payload,
        'operation_sequence': 0, 'measurement_timestamp_us': 1_000_000,
        'receive_timestamp_us': 1_000_000, 'sample_timestamp_us': 1_000_000,
        'evaluation_timestamp_us': 1_000_000, 'application_timestamp_us': 0,
        'timing_flags': 5, 'execution_result': 7, 'update_result': 23})
    final = replace(final, payload={**final.payload, 'epoch': 4,
        'application_timestamp_us': 0, 'timing_flags': 5, 'execution_result': 4,
        'update_result': 20})
    records = tuple(replace(item, record_sequence=offset+i, payload={**item.payload,
        'operation_sequence': offset+i, 'group': i})
        for offset, item in ((0, initial), (4, final)) for i in range(4))
    dataset = replace(dataset, records={**dataset.records, 'ESKF15_MEASUREMENT': records})
    result = _Plugin_Get('eskf15').run(dataset, ReplayRequest())
    operations = result.diagnostics['fusion_timing_operations']
    assert [o['last_execution_result'] for o in operations] == [7]*4 + [4]*4
    assert [o['last_application_us'] for o in operations] == [0]*8
    assert result.diagnostics['failure'] is None


def _KfOperationDataset_Create(prediction_result=0):
    from types import SimpleNamespace
    from silverstar_flp.core.dataset import DecodedRecord
    from tests.test_fusion_timing_records_v2 import _Record_Create
    from tests.test_fusion_timing_contract import _TimingDocument
    baro = _Record_Create('BARO_MEASUREMENT')
    baro = replace(baro, payload={**baro.payload, 'operation_sequence': 2,
        'measurement_timestamp_us': 1_495_000, 'source_timestamp_us': 1_495_000,
        'sample_timestamp_us': 1_495_000, 'receive_timestamp_us': 1_500_000})
    step = DecodedRecord(30, 'ESTIMATOR_STEP', 0, 0, 1, 1_500_000, 0,
        dict(operation_sequence=1, replay_epoch=3, source_sequence=1,
             interval_end_timestamp_us=1_500_000, estimator_present_timestamp_us=1_500_000,
             attitude_result=1, replay_result=prediction_result), 0)
    increment = SimpleNamespace(interval_end_timestamp_us=1_500_000,
        delta_velocity_b=np.array([0, 0, .0978]), delta_theta_b=np.zeros(3), dt_s=.01)
    source = replace(step, record_name='INERTIAL_INCREMENT', payload=dict(
        sequence=1, interval_end_timestamp_us=1_500_000))
    records = {'ESTIMATOR_STEP': (step,), 'INERTIAL_INCREMENT': (source,), 'BARO_MEASUREMENT': (baro,)}
    return SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=_TimingDocument()),
        Records_Get=lambda name: records.get(name, ())), increment


def test_kf_operation_runner_uses_present_state_and_records_distinct_source_application(monkeypatch):
    from silverstar_flp.core.context import TaskContext
    from silverstar_flp.plugins.algorithms.kf6.fixed_lag import Faithful_Run, FixedLagReplay
    from tests.test_fusion_current_state import _KfState_Create
    dataset, increment = _KfOperationDataset_Create()
    def forbidden(*args, **kwargs):
        raise AssertionError('current operation runner entered history replay')
    monkeypatch.setattr(FixedLagReplay, 'Predict', forbidden)
    monkeypatch.setattr(FixedLagReplay, 'Insert', forbidden)
    snapshots, state, audit = Faithful_Run(dataset, _KfState_Create(), np.array([1, 0, 0, 0]),
        [increment], {'gravity_mps2': 9.78, 'fusion_timing_mode': 0}, TaskContext())
    assert len(snapshots) == 1 and not audit['execution_mismatches']
    assert audit['history_replay_count'] == 0
    operation = audit['measurement_operations'][0]
    assert (operation['source_timestamp_us'], operation['application_timestamp_us']) == (1_495_000, 1_500_000)
    assert operation['execution_result'] == 0 and operation['replay_result'] == 255
    assert np.isfinite(state.covariance).all()


@pytest.mark.parametrize('result', [2, 3, 7, 8, 255])
def test_exact_current_step_rejects_unknown_or_unreachable_adapter_results(result):
    from silverstar_flp.core.context import TaskContext
    from silverstar_flp.plugins.algorithms.kf6.fixed_lag import Faithful_Run
    from tests.test_fusion_current_state import _KfState_Create
    dataset, increment = _KfOperationDataset_Create(result)
    with pytest.raises(ValueError, match='fusion_timing_current_prediction_result_invalid'):
        Faithful_Run(dataset, _KfState_Create(), np.array([1, 0, 0, 0]),
            [increment], {'gravity_mps2': 9.78, 'fusion_timing_mode': 0}, TaskContext())


@pytest.mark.parametrize('recorded_mode', [0, 1])
@pytest.mark.parametrize('change', ['missing', 'reordered', 'sequence', 'receive'])
def test_current_numeric_admission_refuses_incomplete_or_mixed_eskf_packet(tmp_path, recorded_mode, change):
    from silverstar_flp.decoder_profiles.errors import DecoderProfileError
    dataset = _EskfSynthetic_Create(tmp_path, recorded_mode)
    records = list(dataset.Records_Get('ESKF15_MEASUREMENT'))
    if change == 'missing':
        records.pop(1)
    elif change == 'reordered':
        records[1], records[2] = records[2], records[1]
    else:
        field = 'source_sequence' if change == 'sequence' else 'receive_timestamp_us'
        records[2] = replace(records[2], payload={**records[2].payload, field: records[2].payload[field]+1})
    dataset = replace(dataset, records={**dataset.records, 'ESKF15_MEASUREMENT': tuple(records)})
    with pytest.raises((DecoderProfileError, ValueError), match='current_packet'):
        _Plugin_Get('eskf15').run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF,
            parameters={'fusion_timing_mode': 0}))


def test_eskf_current_numeric_failure_does_not_publish_a_successful_state(tmp_path, monkeypatch):
    from silverstar_flp.plugins.algorithms.eskf15.filter import Eskf15Filter, EskfMeasurementResult
    dataset = _EskfSynthetic_Create(tmp_path)
    def broken(candidate, *args, **kwargs):
        candidate.state.p[:] = 700
        return EskfMeasurementResult(4, np.zeros(2), 0, np.ones(2))
    monkeypatch.setattr(Eskf15Filter, 'Measurement_Apply', broken)
    result = _Plugin_Get('eskf15').run(dataset, ReplayRequest())
    assert result.diagnostics['failure'] == {'timestamp_us': 1_500_000, 'reason': 'eskf_current_numeric_failure'}
    assert result.channels['navigation.position_enu'].timestamp_us[-1] == 1_490_000
    assert [op['last_execution_result'] for op in result.diagnostics['fusion_timing_operations']] == [6, 7, 7, 7]
    assert result.missing_inputs == ('eskf15_replay_stopped:eskf_current_numeric_failure',)


def test_kf_v2_quality_preserves_a_b_a_inputs_and_never_merges_same_sequence_sources():
    from types import SimpleNamespace
    from tests.test_fusion_timing_records_v2 import _Record_Create
    base = _Record_Create('GNSS_MEASUREMENT')
    schedule = tuple(SimpleNamespace(kind='gnss', record=replace(base,
        payload={**base.payload, 'source_id': source, 'valid_group_mask': mask,
                 'position_variance_m2': [variance]*3}))
        for source, mask, variance in ((0, 15, 1.), (1, 3, 4.), (0, 12, 9.)))
    # Two native producers share sequence and times. They must never overwrite
    # each other's recorded numerical R or mask through the legacy key shape.
    natives = tuple(replace(base, record_name='GNSS_NATIVE', payload=dict(
        instance_id=source, sequence=12, sample_timestamp_us=1_200_000,
        receive_timestamp_us=1_490_000, supported_fields=4, valid_fields=4,
        satellite_count=5 if source == 0 else 20)) for source in (0, 1))
    qualities = tuple(replace(base, record_name='NAV_QUALITY', payload=dict(
        source_id=source, native_sequence=12, receive_us=1_490_000,
        evaluation_us=1_500_000, calibration_generation=7,
        quality_revision=3, variance_scale=scale)) for source, scale in ((0, 2.), (1, 1.)))
    dataset = SimpleNamespace(Records_Get=lambda name: natives if name == 'GNSS_NATIVE'
                              else qualities if name == 'NAV_QUALITY' else ())
    from dataclasses import dataclass
    @dataclass
    class Scheduled:
        kind: str
        record: object
    schedule = tuple(Scheduled(item.kind, item.record) for item in schedule)
    output, audit = _Plugin_Get('kf6')._TimingQualitySchedule_Apply(dataset, schedule, 3)
    assert audit['quality_input_scope'] == 'recorded_v2'
    assert not audit['health_quality_scale_unavailable']
    for old, new in zip(schedule, output, strict=True):
        for key in ('position_variance_m2', 'velocity_variance_m2ps2', 'valid_group_mask', 'source_id'):
            assert new.record.payload[key] == old.record.payload[key]
    assert output[0].record.payload['_quality_variance_scales'] == output[2].record.payload['_quality_variance_scales']
    assert output[0].record.payload['_quality_variance_scales'] != output[1].record.payload['_quality_variance_scales']
    dataset = SimpleNamespace(Records_Get=lambda name: natives + (natives[0],)
        if name == 'GNSS_NATIVE' else qualities if name == 'NAV_QUALITY' else ())
    _, audit = _Plugin_Get('kf6')._TimingQualitySchedule_Apply(dataset, schedule, 3)
    assert audit['health_quality_scale_unavailable']


@pytest.mark.parametrize('parameter', ['gnss_integrity_enable', 'gnss_position_std_horizontal',
                                      'gnss_velocity_std', 'gnss_integrity_max_gap_ms', 'baro_std_m'])
def test_kf_v2_rejects_unimplemented_quality_changes_before_numerical_work(tmp_path, parameter):
    from tests.parameter_fixtures import FirmwareSets_Build
    from tests.test_fusion_timing_contract import _TimingDocument, KF6
    from tests.test_fusion_timing_records_v2 import _Record_Create
    dataset = ParameterPackage_Open(tmp_path).dataset
    document = _TimingDocument()
    document['metadata_declarations']['navigation_replay'] = {'gnss_integrity_revision': 3}
    group = next(g for g in FirmwareSets_Build() if g['component'] == KF6)
    group['parameters'].extend(document['firmware_algorithm_parameters'][0]['parameters'])
    document['firmware_algorithm_parameters'] = [group]
    context = replace(dataset.semantic_context, firmware_algorithm_ids=(KF6,), raw_metadata=document)
    dataset = replace(dataset, semantic_context=context,
        records={**dataset.records, 'GNSS_MEASUREMENT': (_Record_Create('GNSS_MEASUREMENT'),),
                 'BARO_MEASUREMENT': (_Record_Create('BARO_MEASUREMENT'),)})
    plugin = _Plugin_Get('kf6')
    values = dict(plugin.recorded_parameters(dataset))
    plugin._TimingQualityParameters_Validate(dataset, values)
    values[parameter] += 1
    reason = ('parameter_dynamic_uncertainty_missing:BARO_NATIVE_logical_producer_identity'
              if parameter == 'baro_std_m' else 'fusion_timing_v2_quality_recompute_unavailable:' + parameter)
    with pytest.raises(ValueError, match=reason):
        plugin._TimingQualityParameters_Validate(dataset, values)


@pytest.mark.parametrize('algorithm', ['kf6', 'eskf15'])
def test_v2_delay_override_requires_explicit_timestamp_trust_evidence(algorithm):
    from types import SimpleNamespace
    from tests.test_fusion_timing_records_v2 import _Record_Create
    if algorithm == 'eskf15':
        item = _Record_Create('ESKF15_MEASUREMENT')
        item = replace(item, payload={**item.payload, 'timing_flags': 0,
            'measurement_timestamp_us': 0, 'application_timestamp_us': 0, 'execution_result': 1})
        dataset = SimpleNamespace(Records_Get=lambda name: (item,) if name == 'ESKF15_MEASUREMENT' else ())
        with pytest.raises(ValueError, match='timestamp_trust_evidence_missing'):
            _Plugin_Get(algorithm)._Measurements_Build(dataset,
                {'gnss_velocity_measurement_delay_ms': 0}, 1_000_000, 2_000_000,
                ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={'gnss_velocity_measurement_delay_ms': 0}))
    else:
        from dataclasses import dataclass
        from silverstar_flp.plugins.algorithms.kf6.measurement_time import MeasurementDelays_Apply
        @dataclass
        class Item:
            record: object
        item = _Record_Create('BARO_MEASUREMENT')
        item = replace(item, payload={**item.payload, 'timing_flags': 0, 'source_timestamp_us': 0})
        with pytest.raises(ValueError, match='timestamp_trust_evidence_missing'):
            MeasurementDelays_Apply(SimpleNamespace(Records_Get=lambda name: ()), (Item(item),),
                {'baro_measurement_delay_ms': 5}, {'baro_measurement_delay_ms': 0})


@pytest.mark.parametrize('parameter', ['gnss_position_std_horizontal', 'gnss_position_std_vertical',
                                      'gnss_velocity_std', 'baro_std_m'])
def test_eskf_v2_noise_override_requires_proven_dynamic_input(tmp_path, parameter):
    dataset = _EskfSynthetic_Create(tmp_path)
    plugin = _Plugin_Get('eskf15')
    values = dict(plugin.recorded_parameters(dataset))
    unchanged, _, _ = plugin._Measurements_Build(dataset, values, 1_000_000, 2_000_000,
        ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={parameter: values[parameter]}))
    for event, record in zip(unchanged, dataset.Records_Get('ESKF15_MEASUREMENT'), strict=True):
        assert np.array_equal(event[2].variance, record.payload['base_variance'][:len(event[2].variance)])
    values[parameter] += 1
    reason = ('parameter_dynamic_uncertainty_missing:BARO_NATIVE_logical_producer_identity'
              if parameter == 'baro_std_m' else 'fusion_timing_v2_noise_recompute_unavailable:' + parameter)
    with pytest.raises(ValueError, match=reason):
        plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={parameter: values[parameter]}))


@pytest.mark.parametrize('override', [{'quality_policy_revision': 2}, {'process_model_revision': 2}])
def test_eskf_v2_refuses_unsupported_policy_or_model_override(tmp_path, override):
    with pytest.raises(ValueError, match=next(iter(override)) + '_unsupported'):
        _Plugin_Get('eskf15').run(_EskfSynthetic_Create(tmp_path), ReplayRequest(mode=ReplayMode.WHAT_IF, **override))


def _EskfTwoPackets_Create(tmp_path, first_operation=1):
    dataset = _EskfSynthetic_Create(tmp_path)
    first = dataset.Records_Get('ESKF15_MEASUREMENT')
    records = tuple(replace(first[i % 4], record_sequence=i + 1,
        payload={**first[i % 4].payload,
                 'source_sequence': 12 + i // 4,
                 'operation_sequence': (first_operation + i) & 0xffffffff}) for i in range(8))
    return replace(dataset, records={**dataset.records, 'ESKF15_MEASUREMENT': records})


@pytest.mark.parametrize('change', ['repeat', 'gap', 'reorder', 'baro_gap'])
def test_eskf_current_complete_packets_require_global_operation_order_but_raw_remains_readable(tmp_path, change):
    from silverstar_flp.decoder_profiles.errors import DecoderProfileError
    from silverstar_flp.decoder_profiles.fusion_timing_records import FusionTimingRecords_Validate
    dataset = _EskfTwoPackets_Create(tmp_path)
    records = list(dataset.Records_Get('ESKF15_MEASUREMENT'))
    if change == 'reorder':
        records = records[4:] + records[:4]
    elif change == 'baro_gap':
        records.append(replace(records[-1], payload={**records[-1].payload,
            'group': 4, 'source_id': 1, 'operation_sequence': 10}))
    else:
        delta = -4 if change == 'repeat' else 1
        records[4:] = [replace(r, payload={**r.payload,
            'operation_sequence': r.payload['operation_sequence'] + delta}) for r in records[4:]]
    dataset = replace(dataset, records={**dataset.records, 'ESKF15_MEASUREMENT': tuple(records)})
    FusionTimingRecords_Validate(dataset)  # Honest gaps are numerical blockers, not corrupt raw bytes.
    with pytest.raises((ValueError, DecoderProfileError), match='current_packet_operation_discontinuity'):
        _Plugin_Get('eskf15').run(dataset, ReplayRequest())


def test_eskf_current_plugin_preserves_full_packet_uint32_operation_wrap(tmp_path):
    dataset = _EskfTwoPackets_Create(tmp_path, 0xfffffffc)
    result = _Plugin_Get('eskf15').run(dataset, ReplayRequest())
    operations = result.diagnostics['fusion_timing_operations']
    assert result.diagnostics['failure'] is None
    assert [op['operation_sequence'] for op in operations] == [0xfffffffc, 0xfffffffd,
        0xfffffffe, 0xffffffff, 0, 1, 2, 3]
    assert [op['group'] for op in operations] == [0, 1, 2, 3] * 2
    assert [op['source_sequence'] for op in operations] == [12] * 4 + [13] * 4
    assert all(op['last_execution_result'] == 0 for op in operations)
