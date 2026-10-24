import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.replay_execution import Replay_Execute
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.algorithms.navigation_reference_v1.plugin import (
    CONFIG_SOURCE, Eskf20AlgorithmPlugin, InEkf15AlgorithmPlugin, InEkf20AlgorithmPlugin,
    _Configuration_Read,
)
from tests.synthetic_parameter_navigation import NavigationPair_Open


@pytest.fixture(scope='module')
def opened(tmp_path_factory):
    # The old fixture builder assumes all installed offline algorithms own firmware
    # parameter packages. Filter only its fixture assembly; LogOpen still uses all 7.
    firmware = tuple(p for p in builtin_registry().algorithms if p.metadata.firmware_component_ids)
    with patch('tests.parameter_fixtures.builtin_registry', return_value=SimpleNamespace(algorithms=firmware)):
        return NavigationPair_Open(tmp_path_factory.mktemp('strict_synthetic_pair'), flight_samples=7)


def config(model):
    size = 15 if model == 'inekf15' else 20
    initial = dict(rotation=np.eye(3).tolist(), position=[0,0,0], velocity=[0,0,0],
        gyro_bias=[0,0,0], accel_bias=[0,0,0], covariance=(np.eye(size)*.01).tolist())
    if size == 20:
        initial.update(installation=np.eye(3).tolist(), inclination=.3, declination=.1)
    return {'schema':'silverstar.navigation.host-reference/1', 'initial':initial,
        'gravity_enu':[0,0,-9.78], 'noise_density':{
            'gyro_radps_per_sqrt_hz':[.001,.002,.003],
            'accel_mps2_per_sqrt_hz':[.1,.2,.3],
            'gyro_bias_rw_radps2_per_sqrt_hz':[.0001]*3,
            'accel_bias_rw_mps3_per_sqrt_hz':[.001]*3}, 'observations':[]}


def request(value, mode=ReplayMode.WHAT_IF):
    value = copy.deepcopy(value)
    if mode is ReplayMode.WHAT_IF:
        # Current corrected wire omits quality and generation: explicit test assumption.
        value["body_input_assumption"] = {"provenance":"user_configuration",
            "quality_flags":0, "calibration_generation":0}
    return ReplayRequest(mode, 'corrected_imu', {'configuration_json':json.dumps(value)})


@pytest.mark.parametrize('plugin_type', [Eskf20AlgorithmPlugin,InEkf15AlgorithmPlugin,InEkf20AlgorithmPlugin])
def test_real_exact_open_replay_lifecycle_and_full_covariance(opened, plugin_type):
    plugin=plugin_type(); dataset=opened.dataset
    before=hashlib.sha256(dataset.source_path.read_bytes()).hexdigest()
    assert not plugin.availability(dataset).available  # Missing wire evidence, no automatic assumption.
    result=Replay_Execute(plugin,dataset,request(config(plugin.model)))
    store=ReplayResultStore(); first=store.Result_Add(result); second=store.Result_Add(result)
    assert first.analysis_ready and second.result_id != first.result_id
    assert first.mode is ReplayMode.WHAT_IF
    assert result.diagnostics['config_source']==CONFIG_SOURCE
    assert result.diagnostics['input_identity']==dataset.metadata['parse_identity']
    assert result.diagnostics['engine_identity']
    assert result.diagnostics['model_source_sha256']['plugin.py']
    assert not plugin.ConfigurationAvailability_Get(dataset).recorded_available
    size=15 if plugin.model=='inekf15' else 20
    assert result.channels[f'{plugin.model}.covariance.upper_triangle'].values.shape[1]==size*(size+1)//2
    assert result.channels['attitude.q_nb'].count==4
    assert result.channels['attitude.q_nb'].timestamp_us[1:].tolist()==[
        row['end_us'] for row in result.diagnostics['output_row_to_input_interval']]
    assert hashlib.sha256(dataset.source_path.read_bytes()).hexdigest()==before
    if size==20:
        assert 'magnetic_no_observation_full_covariance_retained' in result.warnings
    else:
        assert not any('magnetic' in item for item in result.missing_inputs)


def observation(dataset, kind='position', **changes):
    t=dataset.start_timestamp_us+20000
    row=dict(kind=kind,epoch=1,source=2,calibration=0,sample_us=t,receive_us=t,sequence=1,
        time_basis='explicit_cotimed_assumption',provenance='user_configuration',value=[.1,0,0],
        covariance=(np.eye(3)*.01).tolist(),gate=20.)
    row.update(changes)
    return row


@pytest.mark.parametrize('plugin_type',[Eskf20AlgorithmPlugin,InEkf15AlgorithmPlugin,InEkf20AlgorithmPlugin])
def test_vector_updates_consume_once_and_late_is_not_retimed(opened,plugin_type):
    plugin=plugin_type(); value=config(plugin.model)
    row=observation(opened.dataset)
    value['observations']=[row,copy.deepcopy(row),observation(opened.dataset,sequence=2,
        receive_us=opened.dataset.start_timestamp_us+40000)]
    result=plugin.run(opened.dataset,request(value,ReplayMode.WHAT_IF))
    outcomes=result.diagnostics['measurement_outcomes']
    assert [row['result'] for row in outcomes]==['ok','DUPLICATE','OUT_OF_ORDER']
    assert result.provenance=='What-if'
    assert result.channels['navigation.position_enu'].values[1,0] > .01


def test_no_magnetic_or_9_state_alias_and_ids_preserved():
    algorithms=builtin_registry().algorithms
    assert [p.metadata.plugin_id for p in algorithms]==[
        'silverstar.algorithm.pure_ins','silverstar.algorithm.sf6','silverstar.algorithm.kf6',
        'silverstar.algorithm.estimator.eskf15','silverstar.algorithm.estimator.eskf20',
        'silverstar.algorithm.estimator.inekf15','silverstar.algorithm.estimator.inekf20']
    assert all('9' not in p.metadata.plugin_id for p in algorithms)
    assert not InEkf15AlgorithmPlugin().metadata.required_semantic_roles


def test_missing_configuration_not_defaulted_or_recorded(opened):
    plugin=InEkf15AlgorithmPlugin()
    with pytest.raises(ValueError,match='parameter_missing'):
        plugin.run(opened.dataset,ReplayRequest(ReplayMode.OFFLINE))
    with pytest.raises(ValueError,match='explicit_configuration_required'):
        plugin.run(opened.dataset,ReplayRequest(ReplayMode.OFFLINE,parameters={'configuration_json':''}))
    with pytest.raises(ValueError,match='recorded_navigation_journal_required'):
        plugin.run(opened.dataset,request(config('inekf15'),ReplayMode.RECORDED_CONFIGURATION))


@pytest.mark.parametrize('mutator',[
    lambda d: replace(d,metadata={}),
    lambda d: replace(d,semantic_context=None),
    lambda d: replace(d,semantic_context=replace(d.semantic_context,
        calibration=replace(d.semantic_context.calibration,ready=False))),
])
def test_unverified_dataset_rejected(opened,mutator):
    plugin=InEkf15AlgorithmPlugin(); dataset=mutator(opened.dataset)
    assert not plugin.availability(dataset).available
    with pytest.raises(ValueError): plugin.run(dataset,request(config('inekf15')))


def test_nonspd_initial_covariance_no_jitter(opened):
    value=config('inekf15');value['initial']['covariance'][0][0]=-1
    with pytest.raises(ValueError): InEkf15AlgorithmPlugin().run(opened.dataset,request(value))


def test_initial_attitude_change_requires_what_if(opened):
    value=config('inekf15');value['initial']['rotation']=[[0,-1,0],[1,0,0],[0,0,1]]
    result=InEkf15AlgorithmPlugin().run(opened.dataset,request(value))
    assert result.provenance=='What-if'


def test_explicit_observation_never_claims_recorded_time_or_frame(opened):
    value=config('inekf15');value['observations']=[observation(opened.dataset)]
    with pytest.raises(ValueError,match='require_what_if'):
        InEkf15AlgorithmPlugin().run(opened.dataset,request(value,ReplayMode.OFFLINE))
    value['observations'][0]['provenance']='recorded'
    with pytest.raises(ValueError,match='provenance'):
        InEkf15AlgorithmPlugin().run(opened.dataset,request(value,ReplayMode.WHAT_IF))


def test_magnetic_field_label_cannot_be_used_as_sensor_correction(opened):
    value=config('eskf20'); row=observation(opened.dataset,'magnetic',value=[4,45,-15])
    row.update(stage=3,hard_iron_uT=[0,0,0],soft_iron=np.eye(3).tolist(),
        reference_strength_uT=48,ratio_bounds=[.5,1.5]);value['observations']=[row]
    result=Eskf20AlgorithmPlugin().run(opened.dataset,request(value,ReplayMode.WHAT_IF))
    assert result.diagnostics['measurement_outcomes'][0]['result']=='WRONG_STAGE'


def test_named_nonisotropic_noise_uses_canonical_order():
    for name in ('eskf20','inekf15','inekf20'):
        _,_,density,_=_Configuration_Read(name,json.dumps(config(name)))
        np.testing.assert_array_equal(density[:6],[.001,.002,.003,.1,.2,.3])


@pytest.mark.parametrize('model', ['eskf20','inekf15','inekf20'])
@pytest.mark.parametrize('duration_us', [1,10001,20000])
def test_pair_uses_equal_fractional_half_durations(model,duration_us):
    from silverstar_flp.plugins.algorithms.navigation_reference_v1.input_reference import ReferenceSession,Result
    state,gravity,density,_=_Configuration_Read(model,json.dumps(config(model)))
    session=ReferenceSession(model,state,2**53,{})
    force=np.array([[1.,0.,9.78],[3.,0.,9.78]])
    assert session.predict_pair(2**53,2**53+duration_us,np.zeros((2,3)),force,gravity,density) is Result.OK
    actual=session.state
    velocity=actual.velocity if model=='eskf20' else actual.group[:3,3]
    position=actual.position if model=='eskf20' else actual.group[:3,4]
    dt=duration_us/1_000_000
    np.testing.assert_allclose(velocity,[2*dt,0,0],atol=1e-14,rtol=1e-12)
    np.testing.assert_allclose(position,[.75*dt**2,0,0],atol=1e-14,rtol=1e-12)
    assert session.state_us==2**53+duration_us and actual.time_s==dt


def test_pair_second_half_failure_preserves_state_and_clock(monkeypatch):
    from silverstar_flp.plugins.algorithms.navigation_reference_v1 import input_reference as adapter
    state,gravity,density,_=_Configuration_Read('inekf15',json.dumps(config('inekf15')))
    session=adapter.ReferenceSession('inekf15',state,100,{})
    original=adapter.inv15.InEkf15_Predict
    def fail_second(candidate,*args):
        if candidate is not state:
            return SimpleNamespace(result=SimpleNamespace(value='injected_numeric_failure'))
        return original(candidate,*args)
    monkeypatch.setattr(adapter.inv15,'InEkf15_Predict',fail_second)
    assert session.predict_pair(100,101,np.zeros((2,3)),np.zeros((2,3)),gravity,density)=='injected_numeric_failure'
    assert session.state is state and session.state_us==100


def test_vector_schema_is_explicit_imu_origin_without_lever_arm(opened):
    plugin=InEkf15AlgorithmPlugin()
    assert plugin.metadata.coordinate_frame_contract['vector_observation_point']=='IMU origin; no antenna lever-arm correction'
    result=plugin.run(opened.dataset,request(config('inekf15')))
    assert 'IMU-origin ENU' in result.diagnostics['vector_observation_contract']


def test_cancelled_replay_does_not_publish(opened):
    from silverstar_flp.core.context import TaskContext, TaskCancelledError
    context=TaskContext();context.Cancel_Request()
    with pytest.raises(TaskCancelledError):
        InEkf15AlgorithmPlugin().run(opened.dataset,request(config('inekf15')),context)


def test_new_plugin_result_project_persistence(opened,tmp_path):
    from silverstar_flp.core.project import Project_Save,Project_Load,ProjectResults_Load
    from tests.test_project_artifacts import _Document_Build
    plugin=InEkf15AlgorithmPlugin()
    result=Replay_Execute(plugin,opened.dataset,request(config('inekf15')))
    store=ReplayResultStore();store.Result_Add(result)
    path=tmp_path/'p.ssflp';document=_Document_Build(opened,path)
    Project_Save(document,path,replay_store=store,dataset=opened.dataset)
    restored=ProjectResults_Load(Project_Load(path)).Entries_Get()[0]
    assert restored.result.provenance=='What-if'
    assert restored.diagnostics['config_source']==CONFIG_SOURCE
    np.testing.assert_array_equal(restored.channels['inekf15.covariance.upper_triangle'].values,
                                  result.channels['inekf15.covariance.upper_triangle'].values)


def test_strict_cli_writes_derived_artifact_and_preserves_sources(opened,tmp_path):
    from silverstar_flp.plugins.algorithms.navigation_reference_v1.cli import main
    from silverstar_flp.core.artifacts import Artifact_Read
    configuration=tmp_path/'configuration.json';configuration.write_text(request(config('inekf15')).parameters['configuration_json'])
    output=tmp_path/'d.json'
    assert main(['--log',str(opened.dataset.source_path),'--decoder',str(opened.source_package_path),
        '--configuration',str(configuration),'--output',str(output),'--cache',str(tmp_path/'cache'),
        '--model','inekf15','--mode','what_if'])==0
    manifest=json.loads(output.read_text())
    assert manifest['provenance']=='Derived/user configuration'
    assert manifest['source_log_sha256']==opened.dataset.metadata['source_log_sha256']
    result=Artifact_Read(output,manifest['artifact'])
    assert result.algorithm_id.endswith('inekf15')
    assert result.channels['attitude.q_nb'].count==4


def test_seven_real_plugins_roundtrip_with_explicit_new_configurations(opened,tmp_path,monkeypatch):
    from silverstar_flp.core.project import Project_Save,Project_Load,ProjectResults_Load
    from tests.test_project_artifacts import _Document_Build,_Assert_Result
    registry=builtin_registry();store=ReplayResultStore()
    for plugin in registry.algorithms:
        if hasattr(plugin,'model'):
            replay_request=request(config(plugin.model))
        else:
            replay_request=ReplayRequest(mode=ReplayMode.WHAT_IF,
                process_model_revision=2 if plugin.metadata.plugin_id.endswith('kf6') else None)
        result=Replay_Execute(plugin,opened.dataset,replay_request)
        assert result.channels and not result.missing_inputs
        store.Result_Add(result)
    path=tmp_path/'s.ssflp';document=_Document_Build(opened,path)
    Project_Save(document,path,replay_store=store,dataset=opened.dataset)
    for plugin in registry.algorithms:
        monkeypatch.setattr(type(plugin),'run',lambda *a: pytest.fail('Restore must not replay'))
    restored=ProjectResults_Load(Project_Load(path))
    assert len(restored.Entries_Get())==7
    for before,after in zip(store.Entries_Get(),restored.Entries_Get()):
        _Assert_Result(before.result,after.result)
