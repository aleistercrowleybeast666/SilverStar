from copy import deepcopy
from dataclasses import replace
import pytest
from silverstar_fccg.project.resources import ResourceAssignments_Resolve
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.model import GroundRadioConfiguration
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.radio_variants import RADIO_PLUGIN
from ebyte_variant_fixture import RadioVariantFixture_Create, RadioVariantFixture_Apply

@pytest.fixture(scope='module')
def pa_seed(tmp_path_factory,builtin_catalog):
    return RadioVariantFixture_Apply(RadioVariantFixture_Create(builtin_catalog,tmp_path_factory.mktemp('pa')), 'e28_2g4m27sx')

@pytest.mark.parametrize('role',['flight','ground'])
@pytest.mark.parametrize('fault',['spi','startup','same_gpio','missing_gpio'])
def test_pa_constraint_validation(pa_seed,builtin_catalog,role,fault):
    model=deepcopy(pa_seed)
    target=model if role=='flight' else model.ground_target
    resources=list(target.hardware.resources)
    if fault=='spi':
        index=next(i for i,r in enumerate(resources) if r.resource_id==target.resource_assignments['telemetry0:radio_bus' if role=='flight' else 'radio0:radio_bus'])
        resources[index]=replace(resources[index],metadata={**resources[index].metadata,'clock_hz':18_000_000})
    elif fault=='startup':
        index=next(i for i,r in enumerate(resources) if r.resource_id=='RF_RX_EN')
        resources[index]=replace(resources[index],metadata={**resources[index].metadata,'initial_level':'high'})
    elif fault=='same_gpio':
        target.resource_assignments[('telemetry0' if role=='flight' else 'radio0')+':radio_tx_en']='RF_RX_EN'
    else:
        del target.resource_assignments[('telemetry0' if role=='flight' else 'radio0')+':radio_tx_en']
    hardware=replace(target.hardware,resources=tuple(resources))
    if role=='flight':model.hardware=hardware
    else:model.ground_target=replace(target,hardware=hardware)
    if role=='flight':
        errors=ResourceAssignments_Resolve(model,builtin_catalog).errors
    else:errors=tuple(issue.message for issue in GroundTargetIssues_Get(model,builtin_catalog))
    assert errors
    if fault=='spi':assert any('spi.maximum_clock_hz' in error for error in errors)
    elif fault=='startup':assert any('initial' in error or 'startup' in error for error in errors)
    elif fault=='same_gpio':assert any('radio_tx_en' in error for error in errors)
    else:assert any('radio_tx_en' in error for error in errors)

def test_cold_pa_is_not_skipped(pa_seed,builtin_catalog):
    model=deepcopy(pa_seed)
    radios=(GroundRadioConfiguration('radio0',RADIO_PLUGIN,'e28_2g4m12sx',12),
            GroundRadioConfiguration('radio1',RADIO_PLUGIN,'e28_2g4m20sx',20))
    model.ground_target=GroundRadiosConfiguration_Apply(model.ground_target,radios,'radio0')
    issues=GroundTargetIssues_Get(model,builtin_catalog)
    assert any(item.code=='GROUND_RADIO_RESOURCE_UNBOUND' and 'radio1 radio_rx_en' in item.message for item in issues)
    assert any(item.code=='GROUND_RADIO_RESOURCE_UNBOUND' and 'radio1 radio_tx_en' in item.message for item in issues)

@pytest.mark.parametrize('role',['flight','ground'])
def test_mixed_variant_requirements_survive_catalog_resolution(pa_seed,builtin_catalog,role):
    from silverstar_fccg.project.model import DeviceInstance
    from silverstar_fccg.generator.multi_target import _GroundModel_Get
    from silverstar_fccg.project.radio_variants import FRONTEND_RESOURCES
    model=deepcopy(pa_seed)
    if role=='flight':
        model.device_instances=[DeviceInstance('radio0',RADIO_PLUGIN,module_variant='e28_2g4m12sx',tx_power_dbm=12),
                                DeviceInstance('radio1',RADIO_PLUGIN,module_variant='e28_2g4m27sx',tx_power_dbm=27)]
    else:
        radios=(GroundRadioConfiguration('radio0',RADIO_PLUGIN,'e28_2g4m12sx',12),
                GroundRadioConfiguration('radio1',RADIO_PLUGIN,'e28_2g4m27sx',27))
        model.ground_target=GroundRadiosConfiguration_Apply(model.ground_target,radios,'radio0')
        model=_GroundModel_Get(model,builtin_catalog)
    view=builtin_catalog.ProjectView_Get(model)
    m12=view.InstanceIdComponent_Get('radio0')
    pa=view.InstanceIdComponent_Get('radio1')
    assert not FRONTEND_RESOURCES & {r.name for r in m12.resource_requirements}
    assert FRONTEND_RESOURCES <= {r.name for r in pa.resource_requirements if r.required}
    assert not FRONTEND_RESOURCES & {f.requirement for f in m12.instance_resource_binding.fields}
    assert FRONTEND_RESOURCES <= {f.requirement for f in pa.instance_resource_binding.fields}
