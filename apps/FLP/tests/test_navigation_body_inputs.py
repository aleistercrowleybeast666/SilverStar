"""Real decoder/log boundary and independent analytic body-half integration."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import pytest

from silverstar_flp.core.mission import MissionReplayBounds_Get
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.algorithms.navigation_reference_v1.body_inputs import BodySteps_Build
from silverstar_flp.plugins.algorithms.navigation_reference_v1.plugin import (
    Eskf20AlgorithmPlugin, InEkf15AlgorithmPlugin, InEkf20AlgorithmPlugin, _BodyInputs_Get)
from tests import synthetic_parameter_navigation as synthetic
from tests.parameter_fixtures import FirmwareSets_Build
from tests.sslog_synthetic import SyntheticSslogBuilder
from tests.test_decoder_profiles import _DescriptorPayload_Build, _PackageFiles_Build, _Package_Write
from tests.test_navigation_plugins import config

PLUGINS=(Eskf20AlgorithmPlugin,InEkf15AlgorithmPlugin,InEkf20AlgorithmPlugin)
ASSUMPTION={'provenance':'user_configuration','quality_flags':0,'calibration_generation':13}
CASES=[([0,500,1001],[0,500,1001]),([0,5000,10001],[0,5000,10001]),
       ([0,333,1001],[0,800,-200]),([0,3901,10001],[-.25,300,-400])]


def pair_open(directory,times,values,*,aggregation=2,exact=False,quality=0,origin=2**53+9):
    directory.mkdir(parents=True,exist_ok=True)
    fixtures=Path(synthetic.__file__).parent/'fixtures/parameter_contracts'
    catalog=json.loads((fixtures/'synthetic_navigation_catalog.json').read_text(encoding='utf-8'))
    semantics=json.loads((fixtures/'synthetic_navigation_semantics.json').read_text(encoding='utf-8'))
    semantics['firmware_algorithm_parameters']=[g for g in FirmwareSets_Build() if g['component'] in semantics['algorithms']]
    if exact:
        extra=json.loads((Path(__file__).parent/'fixtures/navigation_legacy_body_catalog_v1.json').read_text())
        catalog['records'].extend(extra['records'])
    files,hashes=_PackageFiles_Build(catalog_document=catalog,semantics_document=semantics)
    decoder,_=_Package_Write(directory/'SYNTHETIC_halves.ssdecoder',files=files)
    catalog={row['name']:row for row in catalog['records']};builder=SyntheticSslogBuilder()
    def add(name,timestamp,values,flags=0):
        record=catalog[name];payload=bytearray();formats={'f32':'f','u8':'B','u16':'H','u32':'I','u64':'Q','i32':'i'}
        for field in record['fields']:
            count=field.get('count',1);kind=field['type']
            if kind=='pad':payload.extend(bytes(count));continue
            value=values.get(field['name'],0 if count==1 else [0]*count)
            payload.extend(struct.pack('<'+formats[kind]*count,*([value] if count==1 else value)))
        builder.Record_Add(int(record['id'],0),bytes(payload),timestamp,valid_flags=flags,record_version=record['version'])
    builder.Record_Add(0x1d,_DescriptorPayload_Build(hashes),origin-4)
    add('CALIBRATION_RESULT',origin-3,dict(source_id=1,virtual_imu_id=1,state=4,ready=1,
        start_sequence=13,accel_scale=[1]*3,gyro_scale=[1]*3))
    add('SYSTEM_CONFIG',origin-2,dict(configured_imu_rate_hz=200,mechanization_subsample_count=aggregation,
        mechanization_min_sample_rate_hz=50,mechanization_max_sample_rate_hz=500))
    add('INITIAL_STATE',origin-1,dict(q_nb=[1,0,0,0]))
    add('EVENT',origin,dict(event_id=3))
    if exact:
        add('ESKF15_INITIAL_STATE',origin,dict(source_id=1,calibration_generation=13,q_nb=[1,0,0,0],p_diagonal=[1]*15))
        add('ESKF15_BODY_INPUT',origin+times[-1],dict(interval_start_timestamp_us=origin,
            interval_end_timestamp_us=origin+times[-1],source_id=1,calibration_generation=13,
            quality_flags=quality,dt_s=times[-1]*1e-6,body_gyro_radps=[0]*6,
            body_accel_mps2=[values[0],0,0,values[-1],0,0]))
    else:
        for index,(time,value) in enumerate(zip(times,values)):
            add('IMU_CORRECTED',origin+time,dict(sample_timestamp_us=origin+time,receive_timestamp_us=origin+time,
                sequence=index+1,source_id=1,virtual_imu_id=1,valid_mask=3,correction_valid=1,
                gyro_b_radps=[0,0,0],accel_b_mps2=[value,0,0]),3)
    log=builder.File_Write(directory/'SYNTHETIC_halves.BIN')
    return LogOpenCoordinator(builtin_registry(),cache=DecoderProfileCache(directory/'cache')).Open(
        LogOpenRequest(log_path=log,decoder_package_path=decoder))


def integral(times,values,left,right):
    # Independent polynomial antiderivative (not the implementation's trapezoid).
    result=0.
    for index in range(len(times)-1):
        a,b=times[index:index+2];low,high=max(left,a),min(right,b)
        if high<=low:continue
        slope=(values[index+1]-values[index])/(b-a)
        result+=values[index]*(high-low)+.5*slope*((high-a)**2-(low-a)**2)
    return result


@pytest.mark.parametrize('times,values',CASES)
@pytest.mark.parametrize('plugin_type',PLUGINS)
def test_exact_log_open_uneven_corrected_samples_integrate_two_physical_halves(tmp_path,times,values,plugin_type):
    opened=pair_open(tmp_path,times,values);dataset=opened.dataset;plugin=plugin_type()
    before=hashlib.sha256(dataset.source_path.read_bytes()).hexdigest()
    assert dataset.metadata['parse_identity'] and not plugin.availability(dataset).available
    steps,audit=_BodyInputs_Get(dataset,ASSUMPTION);assert len(steps)==1
    step=steps[0];half=times[-1]/2
    rounded=[float(np.float32(value)) for value in values]
    expected=[float(np.float32(integral(times,rounded,a,b)/half)) for a,b in ((0,half),(half,times[-1]))]
    np.testing.assert_array_equal([step.accel1[0],step.accel2[0]],expected)
    assert step.start_us==2**53+9 and step.end_us==2**53+9+times[-1]
    assert audit['exact_body_record'] is False and audit['body_input_assumption']==ASSUMPTION
    value=config(plugin.model);value['gravity_enu']=[0,0,0];value['body_input_assumption']=ASSUMPTION
    result=plugin.run(dataset,ReplayRequest(ReplayMode.WHAT_IF,'corrected_imu',{'configuration_json':json.dumps(value)}))
    actual=result.channels['navigation.velocity_enu'].values[-1,0]
    assert abs(actual-integral(times,rounded,0,times[-1])*1e-6) <= 2e-6*max(1,abs(actual))
    assert result.channels['attitude.q_nb'].timestamp_us[-1]==step.end_us
    assert result.diagnostics['input_contract']['body_input_provenance']=='Derived/unverified user assumption'
    assert hashlib.sha256(dataset.source_path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('duration',[1,10001,20000])
def test_count_one_endpoint_binary32_order_and_analytic_linear_integral(tmp_path,duration):
    opened=pair_open(tmp_path,[0,duration],[-.125,19.25],aggregation=1)
    step=_BodyInputs_Get(opened.dataset,ASSUMPTION)[0][0]
    np.testing.assert_array_equal([step.accel1[0],step.accel2[0]],[4.71875,14.40625])
    assert (float(step.accel1[0])+float(step.accel2[0]))*.5*duration*1e-6 == 9.5625*duration*1e-6


@pytest.mark.parametrize('duration',[1000,10000])
def test_legacy_even_exact_record_retains_source_generation_quality_contract(tmp_path,duration):
    opened=pair_open(tmp_path,[0,duration],[0,0],exact=True)
    steps,audit=_BodyInputs_Get(opened.dataset)
    assert len(steps)==1 and audit['exact_body_record'] and audit['body_input_assumption'] is None
    plugin=InEkf15AlgorithmPlugin();assert plugin.availability(opened.dataset).available
    value=config('inekf15');value['gravity_enu']=[0,0,0]
    result=plugin.run(opened.dataset,ReplayRequest(ReplayMode.OFFLINE,'corrected_imu',{'configuration_json':json.dumps(value)}))
    assert result.provenance=='Offline'
    value['initial']['rotation']=[[0,-1,0],[1,0,0],[0,0,1]]
    with pytest.raises(ValueError,match='attitude_change_requires_what_if'):
        plugin.run(opened.dataset,ReplayRequest(ReplayMode.OFFLINE,'corrected_imu',{'configuration_json':json.dumps(value)}))


@pytest.mark.parametrize('duration',[1,1001,10001])
def test_legacy_odd_exact_mean_semantics_rejected_even_with_assumption(tmp_path,duration):
    opened=pair_open(tmp_path,[0,duration],[0,0],exact=True)
    for assumption in (None,ASSUMPTION):
        with pytest.raises(ValueError,match='legacy_odd_body_half_semantics_unproven'):
            _BodyInputs_Get(opened.dataset,assumption)


@pytest.mark.parametrize('quality',[1,4,0x10,0x80000000])
def test_all_recorded_quality_bits_reject_without_assumption_override(tmp_path,quality):
    opened=pair_open(tmp_path,[0,1000],[0,0],exact=True,quality=quality)
    with pytest.raises(ValueError,match='quality_policy_unsupported'):_BodyInputs_Get(opened.dataset,ASSUMPTION)


def test_missing_wire_evidence_never_defaulted_and_assumption_is_what_if_only(tmp_path):
    dataset=pair_open(tmp_path,[0,500,1000],[0,1,2]).dataset
    assert 'quality_flags' not in dataset.Records_Get('IMU_CORRECTED')[0].payload
    assert 'calibration_generation' not in dataset.Records_Get('IMU_CORRECTED')[0].payload
    with pytest.raises(ValueError,match='evidence_missing'):_BodyInputs_Get(dataset)
    with pytest.raises(ValueError,match='assumed_generation_mismatch'):
        _BodyInputs_Get(dataset,{**ASSUMPTION,'calibration_generation':0})
    value=config('inekf15');value['body_input_assumption']=ASSUMPTION
    with pytest.raises(ValueError,match='assumption_requires_what_if'):
        InEkf15AlgorithmPlugin().run(dataset,ReplayRequest(ReplayMode.OFFLINE,'corrected_imu',{'configuration_json':json.dumps(value)}))


@pytest.mark.parametrize('field,value',[('source_id',None),('source_id',2),('valid_mask',0),('correction_valid',0),
    ('quality_flags',4),('calibration_generation',14),('gyro_b_radps',[float('inf'),0,0])])
def test_corrected_invalid_evidence_cannot_be_repaired_by_assumption(tmp_path,field,value):
    dataset=pair_open(tmp_path,[0,500,1000],[0,1,2]).dataset
    records=dict(dataset.records);samples=list(records['IMU_CORRECTED']);payload=dict(samples[1].payload)
    if value is None:payload.pop(field)
    else:payload[field]=value
    samples[1]=replace(samples[1],payload=payload);records['IMU_CORRECTED']=tuple(samples)
    # Deliberately corrupted parsed data is a rejection test, never evidence.
    with pytest.raises(ValueError):_BodyInputs_Get(replace(dataset,records=records),ASSUMPTION)


@pytest.mark.parametrize('times',[[0,500,20001],[0,0,1000],[0,1000,500]])
def test_bad_interval_domain_rejected(tmp_path,times):
    dataset=pair_open(tmp_path,times,[0,1,2]).dataset
    with pytest.raises(ValueError):_BodyInputs_Get(dataset,ASSUMPTION)
