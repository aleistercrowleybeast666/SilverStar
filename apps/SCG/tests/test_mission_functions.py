from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from silverstar_fccg.generator.render import _FlightConfigHeader_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.mission_process import MissionProcess_Default
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfile_Require
from silverstar_fccg.project.mission_functions import (
    FunctionCoverage_Get, Functions_Derive, Functions_Update, Functions_Issues,
    Functions_Require, FunctionsCanonical_Get, FunctionsReferenceRunner,
    ParameterProfile_Build, ParameterProfile_Preview, ParameterProfile_Apply,
    ParameterProfile_Read, ParameterProfile_Write, FunctionsStrategies_Synchronize, FunctionsCatalog_Get)
from silverstar_fccg.project.validation import Project_EditValidate, Project_Validate

APP = Path(__file__).resolve().parents[1]


def _Configured(catalog):
    model = ReferenceProject_Create('Functions', catalog=catalog)
    return Functions_Update(model,catalog,Functions_Derive(model,catalog))


def test_legacy_display_is_read_only_and_exact_system_adapters_preserve_generated_header(builtin_catalog):
    model = ReferenceProject_Create('Legacy',catalog=builtin_catalog)
    before = deepcopy(model.Dictionary_Get())
    header = _FlightConfigHeader_Render(model,builtin_catalog)
    graph = SourceGraph_Resolve(model,builtin_catalog)
    functions = Functions_Derive(model,builtin_catalog)
    assert model.Dictionary_Get() == before and model.mission_process is None
    assert len([f for f in functions['functions'] if f['instance_id']=='estimator']) == 1
    estimator=next(f for f in functions['functions'] if f['instance_id']=='estimator')
    stages=[s['stage_id'] for s in MissionProcess_Default()['stages']]
    coverage=FunctionCoverage_Get(estimator,stages)
    assert 'ready' not in coverage and coverage['mission_start']=='start' and coverage['ascent']=='active'
    no_marker=[identity for identity in stages if identity!='mission_start']
    assert FunctionCoverage_Get(estimator,no_marker)=={'landed':'stop'}
    candidate = Functions_Update(model,builtin_catalog,functions)
    assert candidate.Dictionary_Get()['format_version'] == 23
    assert _FlightConfigHeader_Render(candidate,builtin_catalog) == header
    assert SourceGraph_Resolve(candidate,builtin_catalog) == graph
    assert Functions_Issues(candidate,builtin_catalog) == ()
    assert Project_Validate(candidate,builtin_catalog).valid
    document = json.loads(json.dumps(candidate.Dictionary_Get()))
    schema = json.loads((APP/'schemas/project.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(document)
    assert ProjectModel_Parse(document).Dictionary_Get() == document
    document['format_version'] = 22
    with pytest.raises(ProjectModelError,match='format_version 23'): ProjectModel_Parse(document)
    profile = MissionProfile_Build(candidate,builtin_catalog)
    assert profile['schema_version']==3 and 'process' not in profile
    assert MissionProfile_Require(profile) == profile
    assert MissionProfile_Build(model,builtin_catalog)['schema_version']==1


def test_interval_references_survive_rename_insert_and_keep_invalid_boundary_as_draft(builtin_catalog):
    model = _Configured(builtin_catalog)
    model.mission_process = MissionProcess_Default()
    function = next(f for f in model.mission_functions['functions'] if f['instance_id']=='estimator')
    function['start']={'kind':'stage_enter','stage_id':'ascent'}
    function['stop']={'kind':'stage_enter','stage_id':'landed'}
    ids = [s['stage_id'] for s in model.mission_process['stages']]
    coverage = FunctionCoverage_Get(function,ids)
    assert coverage['ascent']=='start' and coverage['coast']=='active' and coverage['landed']=='stop'
    model.mission_process['stages'][2]['name']='Renamed flight phase'
    assert FunctionCoverage_Get(function,ids)==coverage
    inserted=deepcopy(model.mission_process['stages'][3]);inserted['stage_id']='extra_coast'
    model.mission_process['stages'].insert(4,inserted)
    ids=[s['stage_id'] for s in model.mission_process['stages']]
    assert FunctionCoverage_Get(function,ids)['extra_coast']=='active'
    assert any(i.code=='FUNCTION_REFERENCE_ONLY' for i in Functions_Issues(model,builtin_catalog))
    with pytest.raises(ValueError,match='FUNCTION_REFERENCE_ONLY'): _FlightConfigHeader_Render(model,builtin_catalog)
    model.mission_process['stages']=[s for s in model.mission_process['stages'] if s['stage_id']!='ascent']
    restored=ProjectModel_Parse(model.Dictionary_Get())
    assert any(i.code=='FUNCTION_STAGE_MISSING' for i in Functions_Issues(restored,builtin_catalog))
    assert Project_EditValidate(restored,builtin_catalog).valid
    assert not Project_Validate(restored,builtin_catalog).valid
    function['start'],function['stop']=function['stop'],function['start']
    function['stop']={'kind':'stage_enter','stage_id':'ready'}
    assert any(i.code=='FUNCTION_INTERVAL_INVALID' for i in Functions_Issues(model,builtin_catalog))


@pytest.mark.parametrize('mutation,code',[
    ('singleton','FUNCTION_SINGLETON'),('omitted','FUNCTION_SELECTED_UNBOUND'),
    ('cycle','FUNCTION_DEPENDENCY_CYCLE'),('input','FUNCTION_INPUT_MISSING'),
    ('output','FUNCTION_OUTPUT_CONFLICT')])
def test_runtime_conflicts_are_located_without_destroying_a_draft(builtin_catalog,mutation,code):
    model=_Configured(builtin_catalog)
    functions=model.mission_functions['functions']
    estimator=next(row for row in functions if row['instance_id']=='estimator')
    ins=next(row for row in functions if row['instance_id']=='ins')
    if mutation=='singleton':
        duplicate=deepcopy(estimator);duplicate['instance_id']='second_estimator';functions.append(duplicate)
    elif mutation=='omitted': functions.remove(estimator)
    elif mutation=='cycle': ins['depends_on']=['estimator']
    elif mutation=='input': ins['input_bindings']['imu.acceleration']='missing_device'
    elif mutation=='output': estimator['output']=ins['output']
    assert Functions_Require(model.mission_functions)==model.mission_functions
    issues=Functions_Issues(model,builtin_catalog)
    assert any(i.code==code and i.function_id for i in issues)
    with pytest.raises(ValueError,match=code): _FlightConfigHeader_Render(model,builtin_catalog)


def test_reference_snapshot_stops_before_active_and_never_restarts_or_completes_once_implicitly(builtin_catalog):
    model=_Configured(builtin_catalog)
    stages=[s['stage_id'] for s in MissionProcess_Default()['stages']]
    runner=FunctionsReferenceRunner(model.mission_functions,stages)
    first=runner.Snapshot_Step(1,system_prepared=True)
    assert first['pending_once']==['alignment']
    start=runner.Snapshot_Step(2,stage_id='ascent',system_prepared=True,mission_started=True)
    assert start['start_requests'].count('ins')==1 and start['start_requests'].count('estimator')==1
    repeat=runner.Snapshot_Step(3,stage_id='coast',system_prepared=True,mission_started=True)
    assert repeat['start_requests']==[] and {'ins','estimator'}<=set(repeat['active'])
    assert repeat['pending_once']==['alignment']
    runner.Completion_Report('alignment','completed')
    with pytest.raises(ValueError): runner.Completion_Report('alignment','completed')
    stopped=runner.Snapshot_Step(4,stage_id='landed',system_prepared=True,mission_started=True)
    assert set(stopped['stop_requests'])=={'ins','estimator'}
    assert not {'ins','estimator'} & set(stopped['active'])
    assert 'recording' in stopped['active'] and not stopped['pending_once']
    with pytest.raises(ValueError,match='monotonic'): runner.Snapshot_Step(4,stage_id='landed')
    with pytest.raises(ValueError,match='stage_not_monotonic'): runner.Snapshot_Step(5,stage_id='ascent')
    with pytest.raises(ValueError): runner.Completion_Report('recording','completed')


def test_parameter_profile_preserves_unedited_precision_and_updates_only_actual_parameters(builtin_catalog,tmp_path):
    model=_Configured(builtin_catalog);plugin=model.strategies['estimator']
    model.algorithm_parameters[plugin]['baro_std_m']=1.234567890123
    before=deepcopy(model.Dictionary_Get())
    profile=ParameterProfile_Build(model,builtin_catalog,plugin)
    path=tmp_path/'kf6.ssparameters';ParameterProfile_Write(path,profile)
    assert ParameterProfile_Read(path)==profile
    assert ParameterProfile_Preview(model,builtin_catalog,plugin,profile)==[]
    parameter=next(p for p in profile['parameters'] if p['id']=='baro_std_m');parameter['value']=2.75
    preview=ParameterProfile_Preview(model,builtin_catalog,plugin,profile)
    assert any(row['parameter_id']=='baro_std_m' and row['after']==2.75 for row in preview)
    changed=ParameterProfile_Apply(model,builtin_catalog,plugin,profile)
    assert changed.algorithm_parameters[plugin]['baro_std_m']==2.75
    original=changed.Dictionary_Get();original['algorithm_parameters']=before['algorithm_parameters']
    assert original==before and model.Dictionary_Get()==before
    ParameterProfile_Write(path,profile,replace_existing=True)
    assert ParameterProfile_Read(path.with_suffix('.ssparameters.bak'))['parameters']!=profile['parameters']


@pytest.mark.parametrize('mutation',['version','schema','unit','unknown','bool','nan','plugin'])
def test_parameter_profile_rejects_mismatch_and_never_changes_project(builtin_catalog,mutation):
    model=_Configured(builtin_catalog);plugin=model.strategies['estimator']
    before=deepcopy(model.Dictionary_Get());profile=ParameterProfile_Build(model,builtin_catalog,plugin)
    parameter=next(p for p in profile['parameters'] if p['id']=='baro_std_m')
    if mutation=='version': profile['plugin_version']='9.9.9'
    elif mutation=='schema': profile['parameter_schema']='unknown/1'
    elif mutation=='unit': parameter['unit']='feet'
    elif mutation=='unknown': parameter['script']='anything'
    elif mutation=='bool': parameter['value']=True
    elif mutation=='nan': parameter['value']=float('nan')
    elif mutation=='plugin': profile['plugin_id']='other.plugin'
    with pytest.raises(ValueError): ParameterProfile_Apply(model,builtin_catalog,plugin,profile)
    assert model.Dictionary_Get()==before


def test_parameter_file_faults_preserve_good_file_and_backup(builtin_catalog,tmp_path,monkeypatch):
    from silverstar_fccg.project import function_parameters as module
    model=_Configured(builtin_catalog);plugin=model.strategies['estimator']
    profile=ParameterProfile_Build(model,builtin_catalog,plugin)
    path=tmp_path/'good.ssparameters';ParameterProfile_Write(path,profile);good=path.read_bytes()
    real_replace=module.os.replace
    def Replace_Fail(source,target):
        if Path(target)==path: raise OSError('injected replace failure')
        return real_replace(source,target)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'replace',Replace_Fail)
        with pytest.raises(ValueError,match='injected'): ParameterProfile_Write(path,profile,replace_existing=True)
    assert path.read_bytes()==good and path.with_suffix('.ssparameters.bak').read_bytes()==good
    path.write_text('{"schema_id":1,"schema_id":2}',encoding='utf-8')
    with pytest.raises(ValueError,match='duplicate'): ParameterProfile_Write(path,profile,replace_existing=True)
    assert path.read_text(encoding='utf-8')=='{"schema_id":1,"schema_id":2}'
    assert not list(tmp_path.glob('.parameters-*'))


def test_valid_parameter_import_can_repair_selected_owner_draft_with_visible_removals(builtin_catalog):
    model=_Configured(builtin_catalog);plugin=model.strategies['estimator']
    profile=ParameterProfile_Build(model,builtin_catalog,plugin)
    model.algorithm_parameters[plugin]['baro_std_m']=1e9
    model.algorithm_parameters[plugin]['obsolete_parameter']=2.0
    changes=ParameterProfile_Preview(model,builtin_catalog,plugin,profile)
    assert any(row['parameter_id']=='obsolete_parameter' and row['after'] is None for row in changes)
    repaired=ParameterProfile_Apply(model,builtin_catalog,plugin,profile)
    assert repaired.algorithm_parameters[plugin]['baro_std_m']<1e9
    assert 'obsolete_parameter' not in repaired.algorithm_parameters[plugin]
    assert 'obsolete_parameter' in model.algorithm_parameters[plugin]


@pytest.mark.parametrize('case',['self','stopped','missing','external'])
def test_numeric_trigger_sources_have_no_startup_self_wait_and_are_ready_before_sampling(builtin_catalog,case):
    model=_Configured(builtin_catalog);model.mission_process=MissionProcess_Default()
    stage=next(s for s in model.mission_process['stages'] if s['stage_id']=='ascent')
    stage['condition']={'signal':'altitude_agl_m','operator':'>=','value':10,'unit':'m'}
    estimator=next(f for f in model.mission_functions['functions'] if f['instance_id']=='estimator')
    if case=='self': estimator['start']={'kind':'stage_enter','stage_id':'ascent'}
    elif case=='stopped': estimator['stop']={'kind':'stage_enter','stage_id':'mission_start'}
    elif case=='missing': model.mission_functions['functions'].remove(estimator)
    elif case=='external':
        stage['condition']={'signal':'event','operator':'is','value':'launch_detected','unit':'event_id'}
        estimator['start']={'kind':'stage_enter','stage_id':'ascent'}
    issues=Functions_Issues(model,builtin_catalog)
    triggers=[i for i in issues if i.code.startswith('FUNCTION_TRIGGER_')]
    if case=='self': assert any(i.code=='FUNCTION_TRIGGER_DEPENDENCY_CYCLE' and i.stage_id=='ascent' for i in triggers)
    elif case in ('stopped','missing'): assert any(i.code=='FUNCTION_TRIGGER_INPUT_NOT_READY' and i.stage_id=='ascent' for i in triggers)
    else: assert not triggers  # External producer dependency is not guessed.


def test_explicit_strategy_changes_sync_singletons_but_keep_ranges_and_noncanonical_bindings(builtin_catalog):
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    previous=_Configured(builtin_catalog);previous.mission_process=MissionProcess_Default()
    old=next(row for row in previous.mission_functions['functions'] if row['instance_id']=='estimator')
    old['start']={'kind':'stage_enter','stage_id':'ascent'}
    old['input_bindings']['user.explicit.source']='missing_device'
    changed=deepcopy(previous);changed.strategies['estimator']='silverstar.algorithm.estimator.sf6'
    changed=ProjectConfiguration_Reconcile(changed,builtin_catalog).model
    updated=FunctionsStrategies_Synchronize(previous,changed,builtin_catalog)
    function=next(row for row in updated.mission_functions['functions'] if row['instance_id']=='estimator')
    assert function['plugin_id']=='silverstar.algorithm.estimator.sf6'
    assert function['start']==old['start'] and function['input_bindings']==old['input_bindings']
    assert updated.algorithm_parameters==changed.algorithm_parameters
    assert previous.strategies['estimator']!='silverstar.algorithm.estimator.sf6'
    removed=deepcopy(updated);removed.strategies['estimator']=None
    removed=ProjectConfiguration_Reconcile(removed,builtin_catalog).model
    removed=FunctionsStrategies_Synchronize(updated,removed,builtin_catalog)
    assert not any(row['instance_id']=='estimator' for row in removed.mission_functions['functions'])
    legacy=ReferenceProject_Create(catalog=builtin_catalog);legacy_candidate=deepcopy(legacy)
    legacy_candidate.strategies['estimator']=None
    assert FunctionsStrategies_Synchronize(legacy,legacy_candidate,builtin_catalog).mission_functions is None


def test_new_plugin_version_cannot_inherit_a_reviewed_old_lifecycle_adapter(builtin_catalog):
    model=_Configured(builtin_catalog);identity=model.strategies['estimator']
    changed=replace(builtin_catalog.Component_Get(identity),version='99.0.0')
    class VersionCatalog:
        def __getattr__(self,name): return getattr(builtin_catalog,name)
        def Component_Get(self,plugin): return changed if plugin==identity else builtin_catalog.Component_Get(plugin)
        def All_Get(self): return tuple(changed if row.component_id==identity else row for row in builtin_catalog.All_Get())
    catalog=VersionCatalog()
    assert identity not in {row['plugin_id'] for row in FunctionsCatalog_Get(catalog)}
    assert any(issue.code=='FUNCTION_SELECTED_ADAPTER_UNAVAILABLE' for issue in Functions_Issues(model,catalog))


def test_reference_process_is_a_generation_issue_but_remains_a_saveable_draft(builtin_catalog):
    from silverstar_fccg.generator.multi_target import _GroundModel_Get
    from silverstar_fccg.project.validation import MissionProcessIssues_Get
    from test_f103_ground_reference import _GroundF103Model_Get
    model=_Configured(builtin_catalog)
    assert not any(row.code=='MISSION_PROCESS_REFERENCE_ONLY' for row in Project_Validate(model,builtin_catalog).issues)
    model.mission_process=MissionProcess_Default()
    generation=Project_Validate(model,builtin_catalog)
    issue=next(row for row in generation.issues if row.code=='MISSION_PROCESS_REFERENCE_ONLY')
    assert issue.level=='error' and not generation.valid and 'consumer' in issue.message
    draft=Project_EditValidate(model,builtin_catalog)
    assert draft.valid
    assert next(row for row in draft.issues if row.code=='MISSION_PROCESS_REFERENCE_ONLY').level=='warning'
    assert ProjectModel_Parse(model.Dictionary_Get()).mission_process==model.mission_process
    with pytest.raises(ValueError,match='mission_process_firmware_binding_unavailable'):
        _FlightConfigHeader_Render(model,builtin_catalog)
    model.ground_target=_GroundF103Model_Get(builtin_catalog).ground_target
    ground=_GroundModel_Get(model,builtin_catalog)
    assert ground.mission_process is None and ground.mission_functions is None
    assert MissionProcessIssues_Get(ground)==()
