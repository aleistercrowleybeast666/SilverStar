"""Independent SCG-resolved synthetic values; no real-log or Recorded claim."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import struct

import numpy as np
import pytest

from silverstar_flp.plugins.algorithms.navigation_reference_v1.firmware_configuration import (
    ScgWhatIfRequest_Build, ScgWhatIfRequest_FromDataset, ScgRecordedBlockers_Get)
from silverstar_flp.plugins.algorithms.navigation_reference_v1.plugin import (
    _Configuration_Read, Eskf20AlgorithmPlugin, InEkf15AlgorithmPlugin, InEkf20AlgorithmPlugin)
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.parameter_fixtures import ParameterPackage_Open, FirmwareSets_Build
from tests.synthetic_parameter_navigation import NavigationPair_Open

FIXTURE=json.loads((Path(__file__).parent/'fixtures/navigation_augmented_actual_parameters_v1.json').read_text())
MODELS=('eskf20','inekf15','inekf20')
PLUGINS=(Eskf20AlgorithmPlugin,InEkf15AlgorithmPlugin,InEkf20AlgorithmPlugin)

def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def group(model):return copy.deepcopy(FIXTURE['models'][model])
def initial():return copy.deepcopy(FIXTURE['initial_navigation'])
def assumption():return {'provenance':'user_configuration','quality_flags':0,'calibration_generation':0}
def item(values,name):return next(p for p in values['parameters'] if p['id']==name)


@pytest.mark.parametrize('model',MODELS)
def test_scg_binary32_actual_values_map_complete_model_state_and_noise(model):
    request=ScgWhatIfRequest_Build(model,group(model),initial())
    assert request.mode is ReplayMode.WHAT_IF
    state,gravity,density,observations=_Configuration_Read(model,request.parameters['configuration_json'])
    config=json.loads(request.parameters['configuration_json']);size=15 if model=='inekf15' else 20
    np.testing.assert_array_equal(gravity,[0,0,-f32(9.78)])
    np.testing.assert_array_equal(np.diag(state.covariance),[.25+i*.03125 for i in range(size)])
    assert np.count_nonzero(state.covariance-np.diag(np.diag(state.covariance)))==0
    np.testing.assert_array_equal(density,[f32(base*i) for base in (.001,.1,.00001,.0001) for i in (1,2,3)])
    np.testing.assert_array_equal(state.gyro_bias,[f32(.01),f32(-.02),f32(.03)])
    np.testing.assert_array_equal(state.accel_bias,[f32(.1),f32(-.2),f32(.3)])
    np.testing.assert_allclose(config['initial']['rotation'],[[2**-.5,-2**-.5,0],[2**-.5,2**-.5,0],[0,0,1]],atol=6e-8)
    assert config['initial']['velocity']==[1.25,-2.5,.125] and config['initial']['position']==[0,0,0]
    assert observations==[]
    if size==20:
        np.testing.assert_allclose(state.installation,[[0,0,1],[0,1,0],[-1,0,0]],atol=1e-14)
        assert state.inclination==f32(.35) and state.declination==f32(-.45)
    else:assert 'installation' not in config['initial']


@pytest.mark.parametrize('model',MODELS)
@pytest.mark.parametrize('mutation',[
    'wrong_unit','wrong_variance_unit','wrong_storage','wrong_representation','not_binary32',
    'missing','duplicate','unknown','manifest','zero_prior','unconfirmed','not_colocated'])
def test_malformed_or_unconfirmed_actual_contract_rejected(model,mutation):
    values=group(model)
    if mutation=='wrong_unit':item(values,'gyro_bias_rw_density_x')['unit']='rad/s/sqrt(Hz)'
    elif mutation=='wrong_variance_unit':item(values,'initial_variance_0')['unit']='1'
    elif mutation=='wrong_storage':item(values,'gravity_mps2')['storage_type']='float64'
    elif mutation=='wrong_representation':item(values,'initial_variance_0')['representation']='sigma'
    elif mutation=='not_binary32':item(values,'gravity_mps2')['value']=9.78
    elif mutation=='missing':values['parameters'].pop()
    elif mutation=='duplicate':values['parameters'].append(copy.deepcopy(values['parameters'][0]))
    elif mutation=='unknown':values['parameters'][0]['id']='unknown'
    elif mutation=='manifest':values['manifest_sha256']='0'*64
    elif mutation=='zero_prior':item(values,'initial_variance_0')['value']=0.
    elif mutation=='unconfirmed':item(values,'initialization_confirmed')['value']=0
    elif mutation=='not_colocated':item(values,'gnss_imu_colocated_confirmed')['value']=0
    with pytest.raises(ValueError):ScgWhatIfRequest_Build(model,values,initial())


@pytest.mark.parametrize('bad',[{}, {'q_nb_wxyz':[0,0,0,0],'origin_velocity_enu_mps':[0,0,0],'provenance':'user_configuration'},
    {'q_nb_wxyz':[1,0,0,0],'origin_velocity_enu_mps':[0,0,0],'provenance':'recorded'},
    {'q_nb_wxyz':[True,0,0,0],'origin_velocity_enu_mps':[0,0,0],'provenance':'user_configuration'}])
def test_missing_or_fabricated_initial_navigation_is_rejected(bad):
    with pytest.raises(ValueError):ScgWhatIfRequest_Build('inekf15',group('inekf15'),bad)


def observation(kind='position'):
    return {'kind':kind,'epoch':1,'source':7,'calibration':2,'sample_us':1020000,'receive_us':1020000,
            'sequence':1,'time_basis':'explicit_cotimed_assumption','provenance':'user_configuration',
            'value':[0,0,0],'covariance':np.eye(3).tolist()}


def test_gates_and_field_policy_bound_without_implicit_calibration_or_retiming():
    magnetic=observation('magnetic');magnetic.update(value=[0,48,0],stage=1,hard_iron_uT=[0,0,0],soft_iron=np.eye(3).tolist())
    request=ScgWhatIfRequest_Build('eskf20',group('eskf20'),initial(),[observation(),observation('velocity'),magnetic])
    rows=json.loads(request.parameters['configuration_json'])['observations']
    assert [r['gate'] for r in rows]==[f32(11.3),f32(12.4),13.]
    assert rows[-1]['reference_strength_uT']==48. and rows[-1]['ratio_bounds']==[.5,1.5]
    assert all(r['sample_us']==r['receive_us']==1020000 for r in rows)
    with pytest.raises(ValueError,match='override'):
        ScgWhatIfRequest_Build('eskf20',group('eskf20'),initial(),[{**observation(),'gate':1.}])
    with pytest.raises(ValueError,match='instance'):
        ScgWhatIfRequest_Build('eskf20',group('eskf20'),initial(),[{**magnetic,'source':8}])
    with pytest.raises(ValueError,match='no_magnetic'):
        ScgWhatIfRequest_Build('inekf15',group('inekf15'),initial(),[magnetic])


def test_edit_cannot_keep_stale_conversion_provenance_or_claim_offline():
    request=ScgWhatIfRequest_Build('inekf15',group('inekf15'),initial())
    config=json.loads(request.parameters['configuration_json']);config['gravity_enu'][2]=-9.81
    with pytest.raises(ValueError,match='origin_mismatch'):_Configuration_Read('inekf15',json.dumps(config))
    with pytest.raises(ValueError,match='requires_what_if'):
        InEkf15AlgorithmPlugin().Parameters_Resolve(None,replace(request,mode=ReplayMode.OFFLINE))
    with pytest.raises(ValueError,match='recorded_navigation_journal_required'):
        InEkf15AlgorithmPlugin().Parameters_Resolve(None,replace(request,mode=ReplayMode.RECORDED_CONFIGURATION))


@pytest.mark.parametrize('model',MODELS)
def test_exact_package_actual_parameters_are_available_without_recorded_promotion(tmp_path,model):
    opened=ParameterPackage_Open(tmp_path,[group(model)])
    request=ScgWhatIfRequest_FromDataset(opened.dataset,model,initial())
    origin=json.loads(request.parameters['configuration_json'])['configuration_origin']
    assert origin['dataset_identity']['package_sha256']==opened.package.package_sha256
    assert origin['dataset_identity']['parse_identity']==opened.dataset.metadata['parse_identity']
    plugin=builtin_registry().Algorithm_Get('silverstar.algorithm.estimator.'+model)
    plugin.Parameters_Resolve(opened.dataset,request)
    changed=replace(opened.dataset,metadata={**opened.dataset.metadata,'source_log_sha256':'0'*64})
    with pytest.raises(ValueError,match='dataset_mismatch'):plugin.Parameters_Resolve(changed,request)
    readiness=plugin.ConfigurationAvailability_Get(opened.dataset)
    assert not readiness.recorded_available
    assert plugin.metadata.firmware_component_ids==('silverstar.algorithm.estimator.'+model,)
    assert readiness.missing_recorded_parameters==('navigation_complete_journal_missing',)
    if model=='inekf15':assert all('magnetic' not in r for r in readiness.missing_recorded_parameters)
    with pytest.raises(ValueError,match='membership'):
        ScgWhatIfRequest_FromDataset(replace(opened.dataset,semantic_context=replace(opened.dataset.semantic_context,firmware_algorithm_ids=())),model,initial())


@pytest.mark.parametrize('plugin_type',PLUGINS)
def test_explicit_conversion_runs_engine_and_preserves_actual_parameter_provenance(tmp_path,plugin_type):
    opened=NavigationPair_Open(tmp_path,flight_samples=7);plugin=plugin_type()
    request=ScgWhatIfRequest_Build(plugin.model,group(plugin.model),initial(),body_input_assumption=assumption())
    result=plugin.run(opened.dataset,request)
    assert result.provenance=='What-if' and result.channels['attitude.q_nb'].count==4
    assert result.diagnostics['configuration_origin']['parameter_group']==group(plugin.model)
    assert result.diagnostics['configuration_origin']['provenance']=='Derived/user configuration'
    assert len(result.diagnostics['scg_actual_parameters_sha256'])==64


def test_original_four_fixture_membership_and_missing_new_fields_stay_unchanged():
    assert len(FirmwareSets_Build())==4
    assert [p.metadata.plugin_id for p in builtin_registry().algorithms[:4]]==[
        'silverstar.algorithm.pure_ins','silverstar.algorithm.sf6','silverstar.algorithm.kf6','silverstar.algorithm.estimator.eskf15']
    with pytest.raises(ValueError,match='parameter_missing'):
        InEkf15AlgorithmPlugin().Parameters_Resolve(None,ReplayRequest(ReplayMode.WHAT_IF))


def test_scg_cli_opens_exact_package_runs_engine_and_keeps_derived_provenance(tmp_path,monkeypatch):
    from silverstar_flp.plugins.algorithms.navigation_reference_v1.cli import main
    from silverstar_flp.core.artifacts import Artifact_Read
    from tests import synthetic_parameter_navigation as synthetic
    original=synthetic._PackageFiles_Build
    def package_with_explicit_new_owner(*args,**kwargs):
        semantics=copy.deepcopy(kwargs['semantics_document'])
        semantics['algorithms'].append('silverstar.algorithm.estimator.inekf15')
        semantics['firmware_algorithm_parameters'].append(group('inekf15'))
        return original(*args,**{**kwargs,'semantics_document':semantics})
    monkeypatch.setattr(synthetic,'_PackageFiles_Build',package_with_explicit_new_owner)
    opened=NavigationPair_Open(tmp_path/'p',flight_samples=7)
    supplied=tmp_path/'i.json'
    supplied.write_text(json.dumps({'initial_navigation':initial(),'observations':[],
                                   'body_input_assumption':assumption()}))
    output=tmp_path/'d.json'
    # Full SHA artifact filenames exceed legacy MAX_PATH in the long task root.
    # The Win32 extended absolute path stays in this test-owned directory.
    if os.name=='nt' and not str(output).startswith('\\\\?\\'):
        output=Path('\\\\?\\'+str(output.resolve()))
    args=['--log',str(opened.dataset.source_path),'--decoder',str(opened.source_package_path),
        '--scg-initialization',str(supplied),'--output',str(output),'--cache',str(tmp_path/'c'),
        '--model','inekf15']
    with pytest.raises(ValueError,match='requires_what_if'):main(args)
    assert not output.exists()
    before=opened.dataset.source_path.read_bytes()
    assert main(args+['--mode','what_if'])==0
    manifest=json.loads(output.read_text());result=Artifact_Read(output,manifest['artifact'])
    assert manifest['configuration_source_mode']=='scg_actual_parameters_explicit_what_if'
    assert manifest['provenance']=='Derived/user configuration' and result.provenance=='What-if'
    assert result.diagnostics['configuration_origin']['parameter_group']==group('inekf15')
    assert result.diagnostics['configuration_origin']['dataset_identity']['package_sha256']==opened.package.package_sha256
    assert result.channels['attitude.q_nb'].count==4
    assert opened.dataset.source_path.read_bytes()==before
