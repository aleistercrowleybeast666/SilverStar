"""Frozen H7 input-contract checks; synthetic fixtures do not prove MCU stacks."""
import hashlib
import json
from pathlib import Path

import pytest
from test_stack_budget import stacks


def ContractFixture_Create(root, monkeypatch):
    data = {
        'Makefile': 'CFLAGS = fixed\n',
        'Targets/SilverStar_H743ZI/target.mk': 'MCU = cortex-m7\n',
        'Generated/project_sources.mk': 'C_SOURCES += example.c\n',
        'example.c': '#include "config.h"\n',
        'config.h': '#define VALUE 1\n',
        'Drivers/vendor.h': '#define UNLISTED_BY_MMD 0\n',
        'startup.s': 'known assembly\n',
        'layout.ld': 'known memory layout\n',
    }
    for name, text in data.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf8')
    build = root/'build/FCCG/SilverStar_H743ZI/Release'
    build.mkdir(parents=True)
    (build/'example.d').write_text('example.o: example.c config.h\n', encoding='utf8')
    hashes = {name: stacks.H743InputHash_Get(root, name) for name in data}
    inputs = [[name, hashes[name]] for name in ('example.c','config.h')]
    review = {
        'schema':'silverstar.h743-stack-inputs/1', 'review_revision':'test-only',
        'build_declarations':[{'configuration':'Release','files':{name:hashes[name] for name in
            ('Makefile','Targets/SilverStar_H743ZI/target.mk','Generated/project_sources.mk')}}],
        'header_assembly_linker_inputs':['config.h','Drivers/vendor.h','startup.s','layout.ld'],
        'file_versions':{name:[value] for name,value in hashes.items()},
        'compiled_input_closures':{'example.c':[stacks.BindingClosureHash_Get('example.c',hashes['example.c'],inputs)]},
    }
    tool = root/'Tools/h743_stack_inputs.json'
    tool.parent.mkdir()
    tool.write_text(json.dumps(review,sort_keys=True),encoding='utf8')
    monkeypatch.setattr(stacks,'H743_INPUT_REVIEW_SHA256',hashlib.sha256(tool.read_bytes()).hexdigest())
    monkeypatch.setattr(stacks,'H743_INPUT_REVIEW_PATH',tool)
    return build, review, tool


def test_complete_paired_inputs_and_omitted_system_headers_are_verified(tmp_path, monkeypatch):
    build, _, _ = ContractFixture_Create(tmp_path,monkeypatch)
    proof = stacks.H743CompilationInputs_Verify(tmp_path,['example.c'],build)
    assert proof[0]['review_revision'] == 'test-only'
    assert proof[0]['dependencies'] == ['example.c','config.h']


@pytest.mark.parametrize('mutation',['manifest','source','header','system_header','extra_header',
                                    'assembly','linker','dependency','declaration','configuration','missing_dependency'])
def test_changed_compilation_input_is_never_inferred_or_defaulted(tmp_path, monkeypatch, mutation):
    build, _, tool = ContractFixture_Create(tmp_path,monkeypatch)
    changes = {'manifest':tool, 'source':tmp_path/'example.c', 'header':tmp_path/'config.h',
               'system_header':tmp_path/'Drivers/vendor.h', 'extra_header':tmp_path/'unexpected.h',
               'assembly':tmp_path/'startup.s','linker':tmp_path/'layout.ld',
               'declaration':tmp_path/'Targets/SilverStar_H743ZI/target.mk'}
    if mutation in changes:
        path = changes[mutation]
        path.write_bytes((path.read_bytes() if path.exists() else b'')+b'\nchanged\n')
    elif mutation == 'dependency':
        (build/'example.d').write_text('example.o: config.h example.c\n',encoding='utf8')
    elif mutation == 'missing_dependency':
        (build/'example.d').unlink()
    else:
        build = build.parent/'Debug'
        build.mkdir()
    with pytest.raises(ValueError):
        stacks.H743CompilationInputs_Verify(tmp_path,['example.c'],build)


def test_individually_known_file_versions_cannot_be_mixed_into_a_new_closure(tmp_path, monkeypatch):
    build, review, tool = ContractFixture_Create(tmp_path,monkeypatch)
    source = tmp_path/'example.c'
    source.write_text('#include "config.h"\n/* second reviewed revision */\n',encoding='utf8')
    review['file_versions']['example.c'].append(stacks.H743InputHash_Get(tmp_path,'example.c'))
    tool.write_text(json.dumps(review,sort_keys=True),encoding='utf8')
    monkeypatch.setattr(stacks,'H743_INPUT_REVIEW_SHA256',hashlib.sha256(tool.read_bytes()).hexdigest())
    # Both source versions are known, but this source/header pair was never approved.
    with pytest.raises(ValueError,match='paired H743 source/compiler input closure'):
        stacks.H743CompilationInputs_Verify(tmp_path,['example.c'],build)
