from copy import deepcopy
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from silverstar_fccg.project.mission_process import MissionProcess_Default, MissionProcess_Require, MissionProcessRunner
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfile_Read, MissionProfile_Write
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.generator.render import _FlightConfigHeader_Render

ROOT = Path(__file__).resolve().parents[3]
API = runpy.run_path(str(ROOT/'tools/silverstar_mission_profile.py'))


def _Sample(time, *events, valid=True, altitude=None, velocity=None):
    return dict(time_us=time, valid=valid, events=list(events), altitude_agl_m=altitude, vertical_velocity_mps=velocity)


def test_published_contract_matches_runtime_and_portable_example(builtin_catalog):
    process=json.loads((ROOT/'contracts/mission_process_v1.json').read_text(encoding='utf-8'))
    implementation=runpy.run_path(str(ROOT/'tools/silverstar_mission_process.py'))
    assert process['signal_units']==implementation['SIGNALS']
    assert tuple(process['event_ids'])==implementation['EVENTS']
    assert tuple(process['actions'])==implementation['ACTIONS']
    assert set(process['root_fields'])==set(MissionProcess_Default())
    model=ProjectModel_Parse(json.loads((ROOT/'apps/SCG/examples/Uncontrolled_Desktop_Reference.ssproject').read_text(encoding='utf-8')))
    assert MissionProfile_Build(model,builtin_catalog)==MissionProfile_Read(ROOT/'apps/SCG/examples/Uncontrolled_Desktop_Reference.ssmission')
    assert 'path' not in model.reference_provenance


def test_uncontrolled_reference_has_separate_start_predeployment_and_no_hardware_actions(tmp_path, builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    legacy = model.Dictionary_Get()
    assert legacy['format_version'] == 14
    model.mission_process = MissionProcess_Default()
    deploy = next(row for row in model.mission_process['stages'] if row['stage_id']=='deploy')
    deploy['action'] = {'kind':'request_recovery','target':'parachute_pyro0'}
    deploy['condition'] = {'signal':'stage_elapsed_s','operator':'>=','value':0.5,'unit':'s'}
    custom = {'stage_id':'prepare_recovery', 'name':'预开伞等待', 'condition':
        {'signal':'event','operator':'is','value':'apogee_confirmed','unit':'event_id'}, 'hold_ms':0,
        'action':{'kind':'none','target':''}}
    model.mission_process['stages'].insert(4,custom)
    data = model.Dictionary_Get()
    assert data['format_version'] == 22
    restored = ProjectModel_Parse(deepcopy(data))
    assert restored.Dictionary_Get() == data
    bad = deepcopy(data); bad['format_version'] = 21
    with pytest.raises(ProjectModelError,match='format_version 22'): ProjectModel_Parse(bad)
    assert ProjectModel_Parse(legacy).Dictionary_Get() == legacy
    profile = MissionProfile_Build(restored,builtin_catalog)
    path = tmp_path/'custom.ssmission'; MissionProfile_Write(path,profile)
    assert MissionProfile_Read(path) == profile and profile['schema_version'] == 2
    with pytest.raises(ValueError,match='firmware_binding_unavailable'):
        _FlightConfigHeader_Render(restored,builtin_catalog)
    samples = [_Sample(0,'ready'),_Sample(1000000,'start_accepted'),_Sample(2000000,'launch_detected'),
        _Sample(3000000,'burnout_detected'),_Sample(4000000,'apogee_confirmed'),_Sample(4100000),
        _Sample(4600000),_Sample(4700000),_Sample(5000000,'deployment_confirmed'),
        _Sample(6000000,'landed_confirmed'),_Sample(7000000,'recovery_complete')]
    runner = MissionProcessRunner(model.mission_process); events=[]
    for sample in samples:
        _result, records=runner.Sample_Step(sample);events.extend(records)
    assert runner.index == 7
    assert [r['time_us'] for r in events if r['stage_id']=='prepare_recovery']==[4000000]
    assert [r['time_us'] for r in events if r['stage_id']=='deploy' and r['kind']=='stage_entered']==[4600000]
    assert len([r for r in events if r['stage_id']=='deploy' and r['kind']=='simulated_action_request'])==1
    assert all(r['kind'] in ('stage_entered','simulated_action_request') for r in events)
    assert runner.Sample_Step(_Sample(8000000))[1]==[]
    trace={'schema_id':'silverstar.mission-trace/1','profile_sha256':profile['sha256'],
        'session_id':'synthetic_uncontrolled','source':'desktop_reference','events':events}
    trace_path=tmp_path/'reference.ssmissiontrace'
    API['MissionTrace_Write'](trace_path,trace,profile)
    assert API['MissionTrace_Read'](trace_path,profile)==trace
    for mutation in ('digest','sequence','time','source','stage','same_stage_time','action_time','missing_action','truncated_action'):
        invalid=deepcopy(trace)
        if mutation=='digest': invalid['profile_sha256']='0'*64
        elif mutation=='sequence': invalid['events'][1]['sequence']+=1
        elif mutation=='time': invalid['events'][0]['time_us']=-1
        elif mutation=='source': invalid['source']='onboard_recorded'
        elif mutation=='stage': invalid['events'][0]['stage_id']='missing'
        elif mutation=='same_stage_time': invalid['events'][2]['time_us']=invalid['events'][0]['time_us']
        elif mutation=='action_time': invalid['events'][1]['time_us']+=1
        elif mutation=='missing_action':
            invalid['events'].pop(1)
            for sequence, row in enumerate(invalid['events'], 1): row['sequence']=sequence
        elif mutation=='truncated_action': invalid['events'].pop()
        with pytest.raises(ValueError): API['MissionTrace_Require'](invalid,profile)
    input_path=tmp_path/'samples.jsonl'
    input_path.write_text('\n'.join(json.dumps(row) for row in samples)+'\n',encoding='utf-8')
    result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/replay_mission_process.py'),str(path),
        str(input_path),str(tmp_path/'cli.ssmissiontrace')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['hardware_actions']==0
    assert API['MissionTrace_Read'](tmp_path/'cli.ssmissiontrace',profile)['events']==events


def test_default_ends_at_landing_and_deployment_waits_for_apogee(builtin_catalog):
    process = MissionProcess_Default()
    assert [row['stage_id'] for row in process['stages']] == [
        'ready','mission_start','ascent','coast','deploy','descent','landed']
    runner = MissionProcessRunner(process)
    for index, event in enumerate(('ready','start_accepted','launch_detected','burnout_detected')):
        runner.Sample_Step(_Sample(index*1000000,event))
    assert runner.Sample_Step(_Sample(4000000))[1] == []
    assert runner.index == 3
    _, records = runner.Sample_Step(_Sample(5000000,'apogee_confirmed'))
    assert records[0]['stage_id'] == 'deploy'
    # Saved custom phases remain explicit user data, even if absent from defaults.
    model = ReferenceProject_Create(catalog=builtin_catalog)
    old = deepcopy(process)
    pre = deepcopy(old['stages'][4]); pre.update(stage_id='predeploy', name='User pre-deployment')
    old['stages'].insert(4, pre)
    recovery = deepcopy(old['stages'][-1]); recovery.update(stage_id='recovery', name='User recovery')
    recovery['condition']['value'] = 'recovery_complete'
    old['stages'].append(recovery)
    model.mission_process = old
    assert ProjectModel_Parse(model.Dictionary_Get()).mission_process == old


def test_missing_data_gap_and_bad_time_do_not_advance_confirmation_or_state():
    process=MissionProcess_Default()
    process['stages']=[{'stage_id':'one','name':'hold','condition':{
        'signal':'altitude_agl_m','operator':'>=','value':100,'unit':'m'},'hold_ms':500,
        'action':{'kind':'none','target':''}}]
    runner=MissionProcessRunner(process)
    assert runner.Sample_Step(_Sample(100,altitude=110))[1]==[]
    with pytest.raises(ValueError,match='monotonic'):runner.Sample_Step(_Sample(100,altitude=110))
    assert runner.last_time_us==100
    with pytest.raises(ValueError,match='sample_number'):
        runner.Sample_Step(_Sample(200,altitude=10**1000))
    assert runner.last_time_us==100
    assert runner.Sample_Step(_Sample(400000,altitude=110,valid=False))[1]==[]
    assert runner.hold_start_us is None
    assert runner.Sample_Step(_Sample(500000,altitude=110))[1]==[]
    assert runner.Sample_Step(_Sample(2000000,altitude=110))[1]==[]  # Excessive gap resets hold.
    assert runner.Sample_Step(_Sample(2200000,altitude=None))[1]==[]
    assert runner.Sample_Step(_Sample(2300000,altitude=110))[1]==[]
    assert len(runner.Sample_Step(_Sample(2800000,altitude=110))[1])==1


@pytest.mark.parametrize('mutation',['duplicate','unit','nan','huge_int','bool','script','unknown','missing_target','source'])
def test_process_strict_validation(mutation):
    process=MissionProcess_Default(); stage=process['stages'][0]
    if mutation=='duplicate':process['stages'].append(deepcopy(stage))
    elif mutation=='unit':stage['condition']['unit']='NED'
    elif mutation=='nan':stage['condition'].update(signal='altitude_agl_m',operator='>=',value=float('nan'),unit='m')
    elif mutation=='huge_int':stage['condition'].update(signal='altitude_agl_m',operator='>=',value=10**1000,unit='m')
    elif mutation=='bool':stage['hold_ms']=True
    elif mutation=='script':stage['condition']['value']='__import__("os")'
    elif mutation=='unknown':stage['script']='run anything'
    elif mutation=='missing_target':stage['action']={'kind':'request_recovery','target':'missing_device'}
    elif mutation=='source':process['execution']='onboard_qualified'
    with pytest.raises(ValueError):MissionProcess_Require(process,set())
