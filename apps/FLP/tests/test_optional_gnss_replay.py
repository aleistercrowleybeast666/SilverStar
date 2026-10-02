"""Offline GNSS absence versus contradictory measurement evidence; no hardware."""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.analysis.navigation_revision3 import QualitySchedule_Apply
from silverstar_flp.plugins.algorithms.kf6.plugin import _ScheduledMeasurement
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.synthetic_parameter_navigation import NavigationPair_Open, SyntheticOperations_Attach
from tests.test_gnss_integrity import Dataset_Build


def build(origin, native_kind, logged_mask=None):
    dataset = Dataset_Build()
    initial = replace(dataset.initial_state, payload={**dataset.initial_state.payload,
        'origin_valid_flags': int(origin), 'gnss_origin_position_std_m': (0., 0., 0.)})
    native = replace(dataset.Records_Get('GNSS_NATIVE')[1], payload={
        **dataset.Records_Get('GNSS_NATIVE')[1].payload, 'supported_fields': 1023,
        'valid_fields': 1023, 'online': 1, 'fix_ok': int(native_kind == 'valid'),
        'fix_type': 3 if native_kind == 'valid' else 0,
        'valid_group_mask': 15 if native_kind == 'valid' else 0,
        'position_usable': int(native_kind == 'valid'), 'receive_timestamp_us': 40000})
    natives = () if native_kind == 'absent' else (native,)
    records = {'INITIAL_STATE': (initial,), 'GNSS_NATIVE': natives}
    baro = replace(native, record_name='BARO_MEASUREMENT', payload={'test_sentinel': 1})
    schedule = [_ScheduledMeasurement(40000, 2, 'baro', baro, False)]
    if logged_mask is not None:
        measured = replace(native, record_name='GNSS_MEASUREMENT', payload={
            **native.payload, 'valid_group_mask': logged_mask, 'fusion_allowed': 1,
            'position_variance_m2': (1., 1., 1.), 'velocity_variance_m2ps2': (1., 1., 1.)})
        records['GNSS_MEASUREMENT'] = (measured,)
        schedule.append(_ScheduledMeasurement(40000, 1, 'gnss', measured, False))
    return replace(dataset, records=records), tuple(schedule)


@pytest.mark.parametrize('revision', [2, 3])
@pytest.mark.parametrize('origin', [False, True])
@pytest.mark.parametrize('native_kind', ['absent', 'no_fix'])
def test_absent_gnss_keeps_baro_schedule_and_reports_unavailable(revision, origin, native_kind):
    dataset, schedule = build(origin, native_kind)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    actual, diagnostics = plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)
    assert actual == schedule and actual[0] is schedule[0]
    assert diagnostics['gnss_available'] is False
    assert diagnostics['gnss_unavailable_reason']
    assert dataset.initial_state.payload['origin_valid_flags'] == int(origin)


@pytest.mark.parametrize('origin', [False, True])
def test_revision3_without_native_is_available_for_inertial_only_replay(origin):
    dataset, schedule = build(origin, 'absent')
    actual, diagnostics = QualitySchedule_Apply(dataset, schedule, builtin_registry().Algorithm_Get('silverstar.algorithm.kf6').OfflineParameters_Get())
    assert actual == schedule and not diagnostics['gnss_available']
    assert diagnostics['window_evidence'] == []


@pytest.mark.parametrize('revision', [2, 3])
def test_invalid_fix_operation_is_explicitly_excluded_without_mutating_record(revision):
    dataset, schedule = build(False, 'no_fix', 0)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    actual, diagnostics = plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)
    assert actual[0] is schedule[0]
    assert actual[1].record.payload['valid_group_mask'] == 0
    assert actual[1].record.payload['fusion_allowed'] == 0
    assert schedule[1].record.payload['fusion_allowed'] == 1
    assert diagnostics['gnss_excluded_operation_count'] == 1


@pytest.mark.parametrize('revision', [2, 3])
@pytest.mark.parametrize('native_kind,error', [('absent', 'gnss_integrity_native_evidence_missing'), ('no_fix', 'gnss_physical_evidence_contradiction')])
def test_admitted_observation_needs_valid_evidence(revision, native_kind, error):
    dataset, schedule = build(False, native_kind, 15)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    with pytest.raises(ValueError, match=error):
        plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)


@pytest.mark.parametrize('revision', [2, 3])
def test_valid_native_still_requires_origin(revision):
    dataset, schedule = build(False, 'valid', 15)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    with pytest.raises(ValueError, match='gnss_origin_unavailable'):
        plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)


@pytest.mark.parametrize('revision', [2, 3])
def test_unmatched_admitted_observation_is_not_silently_skipped(revision):
    dataset, schedule = build(True, 'valid', 15)
    unmatched = replace(schedule[1].record, payload={**schedule[1].record.payload, 'sequence': 999})
    schedule = (schedule[0], replace(schedule[1], record=unmatched))
    dataset = replace(dataset, records={**dataset.records, 'GNSS_MEASUREMENT': (unmatched,)})
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    with pytest.raises(ValueError, match='gnss_(?:integrity_native_evidence_missing|native_unavailable)'):
        plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)


@pytest.mark.parametrize('revision', [2, 3])
def test_valid_origin_and_native_still_perform_gnss_quality_evaluation(revision):
    dataset, schedule = build(True, 'valid', 15)
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    actual, diagnostics = plugin._IntegritySchedule_Apply(dataset, schedule, plugin.OfflineParameters_Get(), revision_override=revision)
    assert diagnostics.get('gnss_available') is not False
    assert actual[1].record.payload['valid_group_mask'] == 15
    assert actual[1].record.payload['fusion_allowed'] == 1


@pytest.mark.parametrize('revision', [2, 3])
def test_full_kf6_without_gnss_replays_finite_prediction_and_baro(tmp_path, revision):
    original = NavigationPair_Open(tmp_path / 'input').dataset
    initial = replace(original.initial_state, payload={**original.initial_state.payload, 'origin_valid_flags': 2})
    records = {**original.records, 'INITIAL_STATE': (initial,), 'GNSS_NATIVE': (), 'GNSS_MEASUREMENT': ()}
    # Rebuild a coherent synthetic operation sequence after removing its GNSS.
    metadata = {**original.semantic_context.raw_metadata, 'metadata_declarations': {
        **original.semantic_context.raw_metadata.get('metadata_declarations', {}),
        'navigation_replay': {'gnss_integrity_revision': revision}}}
    context = replace(original.semantic_context, raw_metadata=metadata)
    dataset = SyntheticOperations_Attach(replace(original, records=records, semantic_context=context))
    plugin = builtin_registry().Algorithm_Get('silverstar.algorithm.kf6')
    result = plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, parameters={'gnss_integrity_enable': 1}))
    assert result.diagnostics['gnss_integrity']['gnss_available'] is False
    assert 'gnss_unavailable' in result.warnings
    assert result.diagnostics['measurement_events']
    assert all(item['group'] == 'baro' for item in result.diagnostics['measurement_events'])
    for key in ('navigation.position_enu', 'navigation.velocity_enu'):
        series = result.channels[key]
        assert len(series.values) > 0 and np.isfinite(series.values[series.valid]).all()
