"""Synthetic tamper tests of the exact input gate, never an MCU stack proof."""
import hashlib
import json

import pytest
from test_stack_budget import stacks


def Fixture_Create(root, monkeypatch):
    files = {'Makefile': 'fixed build\n', 'Targets/Test/target.mk': 'cpu=fixed\n',
        'BuildSystem/vendor.mk': 'strict vendor flags\n',
        'Generated/project_sources.mk': 'C_SOURCES += example.c\n',
        'example.c': '#include "config.h"\n', 'config.h': '#define VALUE 1\n',
        'Drivers/system.h': 'vendor input omitted by -MMD\n',
        'startup.s': 'known assembly\n', 'layout.ld': 'known linker\n'}
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf8')
    (root/'SilverStar.ssproject').write_text(json.dumps({'build':{'target_profile':'Test'}}),encoding='utf8')
    build = root/'build/FCCG/Test/Release'
    build.mkdir(parents=True)
    (build/'example.d').write_text('example.o: example.c config.h\n',encoding='utf8')
    hashes = {name:stacks.H743InputHash_Get(root,name) for name in files}
    case = {'name':'fixture','target_profile':'Test','configuration':'Release', 'compiler':'fixture gcc',
        'build_declarations':{name:value for name,value in hashes.items() if name=='Makefile' or name.endswith('.mk')},
        'sources':['example.c'], 'header_assembly_linker_inputs':['config.h','Drivers/system.h','startup.s','layout.ld'],
        'file_hashes':hashes,'compiled_input_closures':{'example.c': stacks.BindingClosureHash_Get(
            'example.c',hashes['example.c'],[[name,hashes[name]] for name in ('example.c','config.h')])}}
    review = {'schema':'silverstar.astra-stack-inputs/1','review_revision':'test-only','cases':[case]}
    path = root/'review.json'
    path.write_text(json.dumps(review),encoding='utf8')
    monkeypatch.setattr(stacks,'ASTRA_INPUT_REVIEW_PATH',path)
    monkeypatch.setattr(stacks,'ASTRA_INPUT_REVIEW_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(stacks,'Command_Read',lambda command,cwd: 'fixture gcc\n')
    return build,review,path


def test_exact_case_and_compiler_inputs_are_paired(tmp_path,monkeypatch):
    build,_,_ = Fixture_Create(tmp_path,monkeypatch)
    proof = stacks.AstraCompilationInputs_Verify(tmp_path,['example.c'],build)
    assert proof[0]['review_case']=='fixture'
    assert proof[0]['dependencies']==['example.c','config.h']


@pytest.mark.parametrize('mutation',['manifest','source','header','system_header','extra_header',
    'assembly','linker','dependency_order','missing_dependency','declaration','extra_declaration',
    'configuration','compiler','source_set','mixed_source_header'])
def test_unknown_or_mixed_inputs_fail_closed(tmp_path,monkeypatch,mutation):
    build,review,path=Fixture_Create(tmp_path,monkeypatch)
    targets={'manifest':path,'source':tmp_path/'example.c','header':tmp_path/'config.h',
        'system_header':tmp_path/'Drivers/system.h','extra_header':tmp_path/'extra.h',
        'assembly':tmp_path/'startup.s','linker':tmp_path/'layout.ld',
        'declaration':tmp_path/'BuildSystem/vendor.mk','extra_declaration':tmp_path/'extra.mk'}
    sources=['example.c']
    if mutation in targets:
        item=targets[mutation]
        item.write_bytes((item.read_bytes() if item.exists() else b'')+b'changed\n')
    elif mutation=='dependency_order':
        (build/'example.d').write_text('example.o: config.h example.c\n',encoding='utf8')
    elif mutation=='missing_dependency': (build/'example.d').unlink()
    elif mutation=='configuration': build=build.parent/'Debug'
    elif mutation=='compiler': monkeypatch.setattr(stacks,'Command_Read',lambda command,cwd:'different gcc')
    elif mutation=='source_set': sources=[]
    else:
        (tmp_path/'example.c').write_text('a separately known source revision\n',encoding='utf8')
        review['cases'][0]['file_hashes']['example.c']=stacks.H743InputHash_Get(tmp_path,'example.c')
        path.write_text(json.dumps(review),encoding='utf8')
        monkeypatch.setattr(stacks,'ASTRA_INPUT_REVIEW_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    if mutation in ('declaration','extra_declaration'):
        # No new case is selected; the original verifier still rejects the input.
        with pytest.raises(ValueError): stacks.BindingSources_Verify(tmp_path,sources,build)
    else:
        with pytest.raises(ValueError): stacks.AstraCompilationInputs_Verify(tmp_path,sources,build)
