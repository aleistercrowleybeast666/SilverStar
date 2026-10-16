from copy import deepcopy
import json
from pathlib import Path

import pytest

from silverstar_flp.decoder_profiles.errors import DecoderProfileError
from silverstar_flp.decoder_profiles.fusion_horizon_identity import (
    ALGORITHMS, CONSTANTS, VERSIONS, FusionHorizonActual_Validate, FusionHorizonDeclaration_Validate,
)
from silverstar_flp.decoder_profiles.fusion_timing import FusionTiming_FromSemantics, FusionTimingVersionKnown_Is


def _Declaration(component):
    numerical, work = ALGORITHMS[component]
    return {**CONSTANTS, 'component': component, 'horizon_us': 300000,
            'numerical_revision': numerical, 'maximum_work': work}


@pytest.mark.parametrize('component', VERSIONS)
def test_horizon_identity_agrees_with_shared_contract_and_never_infers_old_versions(component):
    authority = json.loads((Path(__file__).resolve().parents[3] /
        'contracts/navigation_fusion_horizon_v1.json').read_text(encoding='utf-8'))
    kind = component.rsplit('.', 1)[1]
    assert VERSIONS == authority['component_versions']
    assert ALGORITHMS[component] == (authority[kind]['numerical_revision'], authority['maximum_work'][kind])
    declaration = _Declaration(component)
    before = deepcopy(declaration)
    assert FusionHorizonDeclaration_Validate(declaration, component, VERSIONS[component]) == (300000, ALGORITHMS[component][0])
    assert declaration == before
    for version in ('0.1.0', '0.2.0', '99.0.0', None):
        with pytest.raises(DecoderProfileError, match='component_version_unsupported'):
            FusionHorizonDeclaration_Validate(declaration, component, version)


@pytest.mark.parametrize('field,value', [('mode', 1), ('mode', True), ('revision', True),
    ('horizon_us', 300000.), ('horizon_us', 300001), ('horizon_us', 0), ('body_capacity', 161),
    ('event_capacity', 65), ('output_feedback', True), ('replays_history', True),
    ('numerical_revision', 99), ('application_time', 'estimator_present'),
    ('output_covariance_time', 'delayed_primary'), ('maximum_work', 513)])
def test_horizon_declaration_is_a_closed_timing_and_work_contract(field, value):
    component = 'silverstar.algorithm.estimator.kf6'
    with pytest.raises(DecoderProfileError):
        FusionHorizonDeclaration_Validate({**_Declaration(component), field: value}, component, VERSIONS[component])


@pytest.mark.parametrize('change', [lambda p: p.update(value=True), lambda p: p.update(value=300.),
    lambda p: p.update(value=299), lambda p: p.update(unit='us'), lambda p: p.update(storage_type='float'),
    lambda p: p.update(representation='standard_deviation')])
def test_horizon_lag_must_match_exact_typed_recorded_actual(change):
    component = 'silverstar.algorithm.estimator.kf6'
    parameter = {'id': 'fusion_horizon_ms', 'value': 300, 'storage_type': 'int32',
                 'unit': 'ms', 'representation': 'value'}
    sets = [{'component': component, 'parameters': [parameter]}]
    FusionHorizonActual_Validate(sets, component, 300000)
    change(parameter)
    with pytest.raises(DecoderProfileError, match='actual_mismatch'):
        FusionHorizonActual_Validate(sets, component, 300000)


def test_missing_duplicate_or_other_owner_actual_never_receives_a_default():
    component = 'silverstar.algorithm.estimator.kf6'
    for rows in ([], [{'component': component, 'parameters': []}],
                 [{'component': component, 'parameters': [{'id': 'fusion_horizon_ms'}] * 2}],
                 [{'component': 'silverstar.algorithm.estimator.eskf15', 'parameters': [{'id': 'fusion_horizon_ms'}]}]):
        with pytest.raises(DecoderProfileError, match='actual_missing_or_ambiguous'):
            FusionHorizonActual_Validate(rows, component, 300000)


@pytest.mark.parametrize('component', VERSIONS)
def test_main_identity_resolver_reads_separate_schema_and_exact_actuals(component):
    from tests.test_fusion_timing_contract import _Document
    document = _Document(component, VERSIONS[component], 1)
    document['metadata_declarations']['fusion_timing'] = _Declaration(component)
    document['firmware_algorithm_parameters'] = [{'component': component, 'parameters': [
        {'id': 'fusion_timing_mode', 'value': 2, 'unit': '1', 'storage_type': 'int32', 'representation': 'value'},
        {'id': 'fusion_horizon_ms', 'value': 300, 'unit': 'ms', 'storage_type': 'int32', 'representation': 'value'},
    ]}]
    before = deepcopy(document)
    identity = FusionTiming_FromSemantics(document)
    assert identity.mode == 2 and identity.horizon_us == 300000
    assert identity.numerical_revision == ALGORITHMS[component][0] and not identity.unavailable_reason
    assert FusionTimingVersionKnown_Is(identity)
    assert document == before
    document['firmware_algorithm_parameters'][0]['parameters'].pop()
    with pytest.raises(DecoderProfileError, match='actual_missing_or_ambiguous'):
        FusionTiming_FromSemantics(document)


def test_ambiguous_unknown_identity_cannot_become_known_by_two_missing_versions():
    from silverstar_flp.decoder_profiles.fusion_timing import FusionTimingIdentity
    assert not FusionTimingVersionKnown_Is(FusionTimingIdentity('', None, None, None, 'unknown'))


@pytest.mark.parametrize('plugin_id', ['silverstar.algorithm.kf6', 'silverstar.algorithm.estimator.eskf15'])
def test_old_recorded_configuration_does_not_acquire_the_new_lag_default(plugin_id):
    from types import SimpleNamespace
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.plugins.api.algorithm import ReplayRequest
    plugin = builtin_registry().Algorithm_Get(plugin_id)
    records = {spec.parameter_id: {'value': spec.default, 'unit': spec.unit, 'representation': spec.representation}
               for spec in plugin.metadata.parameter_schema if spec.parameter_id != 'fusion_horizon_ms'}
    context = SimpleNamespace(raw_metadata={'metadata_declarations': {'navigation_replay': {'gnss_integrity_revision': 3}}},
        FirmwareAlgorithm_IsMember=lambda ignored: True, FirmwareParameters_Get=lambda ignored: records)
    dataset = SimpleNamespace(semantic_context=context, Series_Get=lambda ignored: None)
    before = deepcopy(records)
    assert 'fusion_horizon_ms' not in plugin.recorded_parameters(dataset)
    assert 'fusion_horizon_ms' not in plugin.Parameters_Resolve(dataset, ReplayRequest())
    assert records == before
