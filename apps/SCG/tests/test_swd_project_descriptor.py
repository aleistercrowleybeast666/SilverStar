"""Root descriptors are generated host metadata, never firmware or hardware evidence."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from silverstar_diagnostics.contract import DiagnosticError
from silverstar_diagnostics.project_descriptor import (ProjectDescriptor_Create,
    ProjectDescriptor_Validate,ProjectDescriptor_Relative,ProjectDescriptor_GeneratedMatch,
    ProjectDescriptor_Begin,ProjectDescriptor_Resolve)


@pytest.mark.parametrize('role,name',[('flight','Flight.ssdiag'),('ground','Ground.ssdiag')])
def test_generated_entries_have_no_fabricated_elf_or_hash(role,name,tmp_path):
    doc=ProjectDescriptor_Create('Test','STM32F407VET6',role)
    assert ProjectDescriptor_Validate(doc)==doc
    assert doc['state']=='pending_build' and doc['builds']=={} and doc['schema']['binding'] is None
    assert 'sha256' not in json.dumps(doc)
    path=tmp_path/name;path.write_text(json.dumps(doc))
    with pytest.raises(DiagnosticError,match='pending_build'):ProjectDescriptor_Resolve(path)
    ProjectDescriptor_Begin(path)
    assert json.loads(path.read_text())['state']=='pending_build'


@pytest.mark.parametrize('path',['../x.elf','/x.elf','C:/x.elf','a\\x.elf','a/../x.elf','a//x.elf','a/./x.elf','a.hex','', 'a:bad.elf'])
def test_automatic_paths_are_contained_and_canonical(path):
    with pytest.raises(DiagnosticError):ProjectDescriptor_Relative(path)


def test_only_build_owned_fields_may_change_during_ground_regeneration():
    expected=ProjectDescriptor_Create('Test','STM32F103C8','ground')
    current=deepcopy(expected);current.update(state='unavailable',detail='Missing compiler output')
    assert ProjectDescriptor_GeneratedMatch(current,expected)
    current['project']='Another user project'
    assert not ProjectDescriptor_GeneratedMatch(current,expected)


def test_optional_project_and_protocol_metadata_preserve_v1_legacy_semantics():
    legacy=ProjectDescriptor_Create('Test','STM32F407VET6')
    declaration=dict(component='silverstar.protocol.maintenance.serial',package_version='0.1.0',profile='maintenance.serial.0_1')
    current=ProjectDescriptor_Create('Test','STM32F407VET6',project_file='SilverStar.ssproject',maintenance=declaration)
    assert ProjectDescriptor_Validate(current)==current and current['version']==legacy['version']==1
    assert 'maintenance' not in ProjectDescriptor_Validate(legacy)
    assert ProjectDescriptor_GeneratedMatch(legacy,current)
    conflict=deepcopy(current);conflict['maintenance']['profile']='maintenance.serial.0_0'
    assert not ProjectDescriptor_GeneratedMatch(conflict,current)
    disabled=deepcopy(current);disabled['maintenance']=None
    assert ProjectDescriptor_Validate(disabled)['maintenance'] is None


@pytest.mark.parametrize('field,value',[
    ('project_file','../SilverStar.ssproject'),('project_file',[]),
    ('maintenance',True),('maintenance',{'profile':'maintenance.serial.0_1'}),
    ('maintenance',{'component':'plugin','package_version':'0.1.0','profile':'bad\nprofile'}),
    ('unexpected','metadata'),
])
def test_optional_metadata_is_bounded_data_with_no_path_or_unknown_fields(field,value):
    doc=ProjectDescriptor_Create('Test','STM32F407VET6');doc[field]=value
    with pytest.raises(DiagnosticError):ProjectDescriptor_Validate(doc)


def test_ground_metadata_and_artifact_receipt_have_actual_target_and_no_host_runtime(builtin_catalog,tmp_path):
    from test_f103_ground_reference import _GroundF103Model_Get
    from silverstar_fccg.generator.multi_target import GroundFiles_Render
    from silverstar_fccg.core.workspace import WorkspacePolicy
    model=_GroundF103Model_Get(builtin_catalog)
    files=GroundFiles_Render(model,builtin_catalog,WorkspacePolicy(tmp_path))
    doc=json.loads(files['Ground.ssdiag'])
    assert doc['role']=='ground' and doc['schema']['target'].startswith('STM32F103C8')
    assert doc['state']=='pending_build' and doc['schema']['binding'] is None
    assert 'Flight.ssdiag' not in files
    make=files['Makefile'].decode()
    assert 'FCCG_BUILD_ARTIFACT|ELF|$(BUILD_DIR)/ground.elf' in make
    assert 'ifneq ($(ANALYZE),1)' in make
    assert 'ssdiag_bind.py' not in make
    assert not any('ssdiag_runtime' in path or 'ssdiag_bind.py' in path for path in files)
    graph=json.loads(files['Generated/ground_source_graph.json'])
    assert 'ssdiag' not in json.dumps(graph)


def test_ground_build_metadata_can_regenerate_but_user_source_is_preserved(builtin_catalog,tmp_path):
    from test_f103_ground_reference import _GroundF103Model_Get
    from silverstar_fccg.generator.multi_target import TargetGeneration_Apply,TargetScope
    from silverstar_fccg.core.workspace import WorkspacePolicy
    model=_GroundF103Model_Get(builtin_catalog);policy=WorkspacePolicy(tmp_path);root=tmp_path/'project'
    result=TargetGeneration_Apply(model,builtin_catalog,policy,root,TargetScope.GROUND)
    ground=result.project_root/'Ground_Station';path=ground/'Ground.ssdiag'
    original=(ground/'Ground/Core/Src/ground_bridge.c').read_bytes()
    doc=json.loads(path.read_text());doc.update(state='unavailable',detail='A previous build failed');path.write_text(json.dumps(doc))
    TargetGeneration_Apply(model,builtin_catalog,policy,root,TargetScope.GROUND)
    assert json.loads(path.read_text())['state']=='pending_build'
    assert (ground/'Ground/Core/Src/ground_bridge.c').read_bytes()==original
    doc=json.loads(path.read_text());doc['project']='Foreign';path.write_text(json.dumps(doc));foreign=path.read_bytes()
    with pytest.raises(ValueError,match='local changes'):TargetGeneration_Apply(model,builtin_catalog,policy,root,TargetScope.GROUND)
    assert path.read_bytes()==foreign


def test_flight_regeneration_resets_build_state_without_overwriting_user_payload(builtin_catalog,tmp_path):
    from silverstar_fccg.generator.assembler import ProjectAssembler
    from silverstar_fccg.core.workspace import WorkspacePolicy
    from silverstar_fccg.project.reference import ReferenceProject_Create
    from silverstar_fccg.project.model import ProjectModel_Load
    assembler=ProjectAssembler(WorkspacePolicy(tmp_path),builtin_catalog)
    root=tmp_path/'Flight';model=ReferenceProject_Create('FlightRoot',catalog=builtin_catalog)
    plan=assembler.Plan(model,root);assert plan.valid
    assembler.Apply(model,plan)
    path=root/'Flight.ssdiag';doc=json.loads(path.read_text());doc.update(state='unavailable',detail='Previous build failed');path.write_text(json.dumps(doc))
    source=root/'Devices/IMU/JY901B/Src/jy901b_device.c';source.write_bytes(source.read_bytes()+b'\n/* USER OWNED RETAINED */\n');retained=source.read_bytes()
    reopened=ProjectModel_Load(root/'SilverStar.ssproject');plan=assembler.Plan(reopened,root);assert plan.valid
    assembler.Apply(reopened,plan)
    assert source.read_bytes()==retained
    assert json.loads(path.read_text())['state']=='pending_build'
