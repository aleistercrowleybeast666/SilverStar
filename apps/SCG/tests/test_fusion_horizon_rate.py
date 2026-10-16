"""Nominal capacity and declaration work; mode2 remains closed until admission."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.fusion_horizon import FusionHorizonRatePlan_Build
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.rate_plan import InertialRatePlan_Resolve

OWNERS = ('silverstar.algorithm.estimator.kf6', 'silverstar.algorithm.estimator.eskf15')


def _Model(catalog, owner):
    model = ReferenceProject_Create('HorizonCapacity', catalog=catalog)
    model.device_instances[0] = DeviceInstance('imu0', 'silverstar.device.imu.mpu6050')
    model.device_instances.append(DeviceInstance('baro0', 'silverstar.device.barometer.bmp280'))
    model.strategies['estimator'] = owner
    model = ProjectConfiguration_Reconcile(model, catalog).model
    actual = next(row for row in AlgorithmParameters_Resolve(model, catalog) if row['component'] == owner)
    values = {row['id']: row['value'] for row in actual['parameters']}
    return model, values


@pytest.mark.parametrize('owner,numerical,work', [(OWNERS[0], 1, 512), (OWNERS[1], 2, 832)])
def test_nominal_reference_capacity_uses_all_actual_physical_rates(builtin_catalog, owner, numerical, work):
    model, values = _Model(builtin_catalog, owner)
    propagation = InertialRatePlan_Resolve(model, builtin_catalog).effective_propagation_rate_hz
    plan = FusionHorizonRatePlan_Build(model, builtin_catalog, values, propagation)
    assert (plan.horizon_us, plan.numerical_revision, plan.maximum_work) == (300000, numerical, work)
    assert (plan.body_capacity, plan.event_capacity, plan.required_body_slots) == (160, 64, 31)
    assert sorted((rate, groups) for _, rate, groups in plan.producer_rates) == [(20, 1), (25, 4)]
    assert plan.required_event_slots == 43 and not plan.issues


@pytest.mark.parametrize('owner', OWNERS)
def test_horizon_shorter_than_configured_delay_is_explicit_failure(builtin_catalog, owner):
    model, values = _Model(builtin_catalog, owner)
    values['fusion_horizon_ms'] = 260
    plan = FusionHorizonRatePlan_Build(model, builtin_catalog, values, 100)
    assert [row.code for row in plan.issues] == ['FUSION_HORIZON_DELAY_UNCOVERED']


def test_fast_physical_imu_capacity_and_multisource_event_capacity_are_independent(builtin_catalog):
    model, values = _Model(builtin_catalog, OWNERS[0])
    model.device_instances[0] = DeviceInstance('imu0', 'silverstar.device.imu.bmi088', 'i2c', 'bosch_sync_400_hz')
    model.algorithm_parameters['silverstar.algorithm.ins.coning2_sculling2']['mechanization_aggregation'] = 1
    rate = InertialRatePlan_Resolve(model, builtin_catalog)
    assert rate.effective_propagation_rate_hz == 400
    values['fusion_horizon_ms'] = 550
    plan = FusionHorizonRatePlan_Build(model, builtin_catalog, values, rate.effective_propagation_rate_hz)
    assert plan.required_body_slots == 221
    assert 'FUSION_HORIZON_BODY_CAPACITY' in [row.code for row in plan.issues]
    gnss = next(row for row in model.device_instances if row.plugin == 'silverstar.device.gnss.neo_m9n')
    model.device_instances.append(replace(gnss, instance_id='gnss_extra'))
    values['fusion_horizon_ms'] = 300
    plan = FusionHorizonRatePlan_Build(model, builtin_catalog, values, 100)
    assert plan.required_event_slots == 79
    assert [row.code for row in plan.issues] == ['FUSION_HORIZON_EVENT_CAPACITY']


def test_combined_module_without_declared_barometer_rate_stays_unproven(builtin_catalog):
    model = ReferenceProject_Create('UnprovenPhysicalRate', catalog=builtin_catalog)
    owner = model.strategies['estimator']
    actual = next(row for row in AlgorithmParameters_Resolve(model, builtin_catalog) if row['component'] == owner)
    values = {row['id']: row['value'] for row in actual['parameters']}
    plan = FusionHorizonRatePlan_Build(model, builtin_catalog, values, 100)
    assert [row.code for row in plan.issues] == ['FUSION_HORIZON_RATE_UNPROVEN']
    assert 'imu0' in plan.issues[0].message and 'SYSTEM_BAROMETER_OUTPUT_RATE_HZ' in plan.issues[0].message


@pytest.mark.parametrize('owner', OWNERS)
def test_separate_declaration_builder_binds_actual_lag_and_shared_bounds(builtin_catalog, monkeypatch, owner):
    from silverstar_fccg.generator.fusion_timing import _HorizonDeclaration_Get, _HORIZON_CAPABILITY
    model, values = _Model(builtin_catalog, owner)
    # This tests the closed contract builder while public mode2 admission remains
    # deferred. It does not claim a normally generated mode2 package or firmware.
    monkeypatch.setitem(builtin_catalog.Component_Get(owner).metadata, 'fusion_horizon_contract', _HORIZON_CAPABILITY)
    actual = {'parameters': [{'id': key, 'value': value} for key, value in values.items()]}
    declaration = _HorizonDeclaration_Get(model, builtin_catalog, owner, actual)
    authority = json.loads((Path(__file__).resolve().parents[3] /
        'contracts/navigation_fusion_horizon_v1.json').read_text(encoding='utf-8'))
    kind = owner.rsplit('.', 1)[1]
    assert declaration['schema_id'] == authority['schema_id']
    assert declaration['horizon_us'] == 300000
    assert declaration['numerical_revision'] == authority[kind]['numerical_revision']
    assert declaration['maximum_work'] == authority['maximum_work'][kind]
    assert declaration['body_capacity'] == authority[kind]['body_capacity']
    assert declaration['event_capacity'] == authority[kind]['event_capacity']
    assert declaration['output_feedback'] is False and declaration['replays_history'] is False
    values['fusion_horizon_ms'] = 260
    actual['parameters'] = [{'id': key, 'value': value} for key, value in values.items()]
    with pytest.raises(ValueError, match='cannot cover'):
        _HorizonDeclaration_Get(model, builtin_catalog, owner, actual)


@pytest.mark.parametrize('value', [True, 0, 551, 300., '300'])
def test_lag_never_coerces_missing_or_mistyped_actual(builtin_catalog, value):
    model, values = _Model(builtin_catalog, OWNERS[0])
    values['fusion_horizon_ms'] = value
    with pytest.raises(ValueError):
        FusionHorizonRatePlan_Build(model, builtin_catalog, values, 100)


@pytest.mark.parametrize('value', [True, 0, float('nan'), float('inf')])
def test_unknown_propagation_rate_cannot_receive_nominal_capacity_claim(builtin_catalog, value):
    model, values = _Model(builtin_catalog, OWNERS[0])
    with pytest.raises(ValueError):
        FusionHorizonRatePlan_Build(model, builtin_catalog, values, value)
