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






