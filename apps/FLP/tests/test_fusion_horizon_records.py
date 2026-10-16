"""Separate horizon record evidence; never synthesize Recorded parameters."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.catalog import RecordLayout
from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.fusion_horizon_records import (
    RECORDS, MEASUREMENT, STATUS, FusionHorizonLayout_Validate, FusionHorizonRecords_Validate,
)


def _Dataset(*records):
    return SimpleNamespace(Records_Get=lambda name: tuple(r for r in records if r.record_name == name))


def _Record(name, **updates):
    row = RECORDS[name]
    p = {f['name']: [0] * f['count'] if 'count' in f else 0 for f in row['fields']}
    p.update(algorithm_id=1, algorithm_revision=2, numerical_revision=1, fusion_timing_mode=2,
        epoch=7, calibration_generation=3)
    if name == MEASUREMENT:
        p.update(sample_timestamp_us=1000000, receive_timestamp_us=1010000,
            measurement_timestamp_us=1005000, evaluation_timestamp_us=1020000,
            operation_sequence=1, source_sequence=8, physically_valid=1,
            update_result=255, execution_result=11, timing_flags=5, nis=-1,
            observation=[1., 2.], prepared_variance=[1., 1.],
            quality_scale=1., consistency_scale=1., robust_scale=1.)
    else:
        p.update(input_present_timestamp_us=1040000, primary_timestamp_us=1010000,
            output_state_timestamp_us=1040000, output_covariance_timestamp_us=1040000,
            horizon_us=30000, phase=1, horizon_initialized=1, work_count=10, maximum_work=11)
    p.update(updates)
    now = p['evaluation_timestamp_us'] if name == MEASUREMENT else 1040000
    return DecodedRecord(int(row['id'], 0), name, 1, row['payload_size'], 1, now, 0, p, 0)


def _Completed(request, **updates):
    p = dict(request.payload)
    p.update(phase=1, admitted=1, update_result=0, effective_update=1, execution_result=0,
        application_timestamp_us=p['measurement_timestamp_us'], evaluation_timestamp_us=1040000,
        timing_flags=p['timing_flags'] | 2, nis=1., innovation=[1., 1.], effective_variance=[1., 1.])
    p.update(updates)
    return replace(request, payload=p, timestamp_us=p['evaluation_timestamp_us'], file_offset=1)


def test_owned_pair_and_status_keep_original_records():
    request = _Record(MEASUREMENT); completed = _Completed(request)
    status = replace(_Record(STATUS), file_offset=2)
    before = deepcopy(dict(request.payload))
    evidence = FusionHorizonRecords_Validate(_Dataset(request, completed, status), algorithm_id=1, horizon_us=30000)
    assert evidence.requests == (request,) and evidence.completions == (completed,)
    assert not evidence.pending and not evidence.replay_blockers
    assert dict(request.payload) == before


@pytest.mark.parametrize('name', [MEASUREMENT, STATUS])
def test_layout_requires_exact_contract_identity(name):
    row = RECORDS[name]; layout = RecordLayout.FromDocument(row, 0)
    FusionHorizonLayout_Validate(layout)
    with pytest.raises(DecoderProfileError, match='layout_identity_invalid'):
        FusionHorizonLayout_Validate(replace(layout, record_version=2))
    with pytest.raises(DecoderProfileError, match='layout_field_invalid'):
        FusionHorizonLayout_Validate(replace(layout, fields=(replace(layout.fields[0], scale=2), *layout.fields[1:])))


@pytest.mark.parametrize('updates', [
    {'admitted': 1}, {'effective_update': 1}, {'update_result': 0}, {'nis': 0},
    {'application_timestamp_us': 1005000}, {'timing_flags': 7}, {'group': 5},
    {'fusion_timing_mode': 0}, {'numerical_revision': 2}, {'algorithm_id': True},
    {'source_id': 4}, {'receive_timestamp_us': 1050000}, {'quality_scale': 0},
    {'prepared_variance': [0, 1]}, {'observation': [float('nan'), 1]},
    {'prepared_variance': [1e300, 1]}, {'prepared_variance': [1e-300, 1]},
    {'observation': [1e300, 1]}, {'kf_recovery_valid': 2},
])
def test_queued_request_rejects_false_execution_or_value_evidence(updates):
    with pytest.raises(DecoderProfileError):
        FusionHorizonRecords_Validate(_Dataset(_Record(MEASUREMENT, **updates)))


@pytest.mark.parametrize('updates', [
    {'observation': [2., 2.]}, {'source_sequence': 9}, {'measurement_timestamp_us': 1006000},
    {'epoch': 8}, {'effective_update': 1, 'update_result': 2}, {'application_timestamp_us': 0},
    {'innovation': [float('nan'), 0]}, {'effective_variance': [0, 1]}, {'nis': -1},
    {'kf_recovery_generation': 1}, {'kf_consistent_count': 1},
])
def test_completion_cannot_change_owned_request_or_publish_false_success(updates):
    request = _Record(MEASUREMENT)
    with pytest.raises(DecoderProfileError):
        FusionHorizonRecords_Validate(_Dataset(request, _Completed(request, **updates)))


def test_incomplete_and_fault_evidence_remain_inspectable_with_replay_blockers():
    request = _Record(MEASUREMENT)
    pending = FusionHorizonRecords_Validate(_Dataset(request, replace(_Record(STATUS), file_offset=2)))
    assert pending.pending == (request,)
    assert pending.replay_blockers == ('fusion_horizon_completion_missing',)
    # A pending event beyond the final primary is legitimate at log end.
    status = replace(_Record(STATUS, primary_timestamp_us=1000000), file_offset=2)
    assert not FusionHorizonRecords_Validate(_Dataset(request, status)).replay_blockers
    # An internal corrupt count is evidence of the fault, not an invented valid count.
    fault = _Record(STATUS, phase=2, execution_result=6, body_count=161)
    assert FusionHorizonRecords_Validate(_Dataset(fault)).replay_blockers == ('fusion_horizon_fault_recorded',)
    preinit = _Record(STATUS, phase=2, execution_result=5, horizon_initialized=0,
        input_present_timestamp_us=0, primary_timestamp_us=0, horizon_us=0)
    assert FusionHorizonRecords_Validate(_Dataset(preinit)).statuses == (preinit,)


def test_wrapped_operation_zero_is_owned_and_duplicate_completion_rejected():
    first = _Record(MEASUREMENT, operation_sequence=0xffffffff)
    second = replace(_Record(MEASUREMENT, operation_sequence=0), file_offset=2)
    done = replace(_Completed(second), file_offset=3)
    evidence = FusionHorizonRecords_Validate(_Dataset(first, _Completed(first), second, done))
    assert len(evidence.completions) == 2
    with pytest.raises(DecoderProfileError, match='completion_request_missing_or_duplicate'):
        FusionHorizonRecords_Validate(_Dataset(second, done, replace(done, file_offset=4)))


def test_rejected_external_input_keeps_nan_without_fabricated_fusion():
    rejected = _Record(MEASUREMENT, physically_valid=0, execution_result=1, observation=[float('nan'), 0.])
    assert FusionHorizonRecords_Validate(_Dataset(rejected)).requests == (rejected,)


def test_operation_namespace_includes_body_admissions_and_preserves_forward_order():
    first = _Record(MEASUREMENT, operation_sequence=2)
    later = replace(_Record(MEASUREMENT, operation_sequence=18), file_offset=2)
    assert len(FusionHorizonRecords_Validate(_Dataset(first, later)).requests) == 2
    backwards = replace(_Record(MEASUREMENT, operation_sequence=1), file_offset=2)
    with pytest.raises(DecoderProfileError, match='operation_discontinuity'):
        FusionHorizonRecords_Validate(_Dataset(first, backwards))


@pytest.mark.parametrize('component', ['kf6', 'eskf15'])
@pytest.mark.parametrize('present', [False, True])
def test_explicit_horizon_build_metadata_is_preserved_without_admitting_old_logs_to_mode2(component, present):
    from silverstar_flp.decoder_profiles.algorithm_parameters import FirmwareParameters_CheckPlugins
    from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
    from silverstar_flp.plugins.algorithms.eskf15.plugin import Eskf15AlgorithmPlugin
    from tests.test_fusion_timing_contract import _TimingDocument
    document = _TimingDocument('silverstar.algorithm.estimator.' + component)
    group = document['firmware_algorithm_parameters'][0]
    if present:
        group['parameters'].append(dict(id='fusion_horizon_ms', value=300, unit='ms',
            representation='value', storage_type='int32', description='Explicit build lag'))
    before = deepcopy(document)
    FirmwareParameters_CheckPlugins([group])
    plugin = Kf6AlgorithmPlugin() if component == 'kf6' else Eskf15AlgorithmPlugin()
    context = SimpleNamespace(FirmwareParameters_Get=lambda _: {p['id']: p for p in group['parameters']},
        FirmwareAlgorithm_IsMember=lambda _: True, raw_metadata=document)
    dataset = SimpleNamespace(semantic_context=context, Records_Get=lambda _: (), header={})
    recorded = plugin.recorded_parameters(dataset)
    assert ('fusion_horizon_ms' in recorded) is present
    if present:
        assert recorded['fusion_horizon_ms'] == 300
    # The implemented mode2 field moved into the tunable schema. Explicit old
    # values remain recorded actuals; the field is no longer build-only.
    assert 'fusion_horizon_ms' not in plugin.FirmwareBuildParameters_Get(dataset)
    plugin.metadata.Parameters_Validate({'fusion_horizon_ms': 300}, complete=False)
    from silverstar_flp.decoder_profiles.fusion_timing import FusionTimingRun_Resolve
    with pytest.raises(ValueError, match='fusion_horizon_recorded_mode2_identity_required'):
        FusionTimingRun_Resolve(dataset, {'fusion_timing_mode': 2, 'fusion_horizon_ms': 300})
    assert document == before
