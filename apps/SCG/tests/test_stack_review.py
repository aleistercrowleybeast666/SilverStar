"""Negative sealed-review and whole-exception model checks, not MCU evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload/Tools'

def _Load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

review = _Load('stack_review')
runtime = _Load('stack_runtime')

def test_review_document_actual_contents_are_required(tmp_path):
    document = tmp_path / 'Tools/review.md'
    document.parent.mkdir()
    document.write_bytes(b'Reviewed exact source/object contract.\n')
    case = {'review_document': 'Tools/review.md', 'review_document_sha256': hashlib.sha256(document.read_bytes()).hexdigest(),
            'runtime_contract': {'reviewed': True}}
    review.ReviewDocument_Verify(tmp_path, case)
    document.write_bytes(b'Changed meaningful source contract.\n')
    with pytest.raises(ValueError, match='Changed software runtime'):
        review.ReviewDocument_Verify(tmp_path, case)
    with pytest.raises(ValueError, match='Missing software runtime'):
        review.ReviewDocument_Verify(tmp_path, {'review_document_sha256': 'nonempty', 'runtime_contract': True})

def test_artifact_closure_includes_assembly_and_all_c_compiler_reports(tmp_path):
    path = tmp_path / 'Generated/project_sources.mk'
    path.parent.mkdir()
    path.write_text('ASM_SOURCES += \\\n  startup.s\n\n')
    graph = {'sources': ['APP/task.c'], 'elf': tmp_path / 'firmware.elf'}
    assert review.ArtifactPaths_Get(tmp_path, graph) == ['APP/task.d', 'APP/task.o', 'APP/task.su',
        'firmware.elf', 'firmware.map', 'startup.o']


def test_enabled_control_requires_real_task_reachability_not_just_a_linked_symbol(tmp_path):
    path = tmp_path / 'Generated/control_research.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'schema_id': 'silverstar.control-research-runtime/1',
        'enabled': True, 'kind': 'pid', 'period_us': 10000}), encoding='utf8')
    contract = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'enabled': True, 'kind': 'pid'}
    required = {'ControlResearch_Process', 'ControlResearchBackend_Step', 'ControlPid_Step'}
    graph = {'instructions': required}
    with pytest.raises(ValueError, match='actual Flight task closure'):
        runtime.ControlTask_Verify(tmp_path, graph, contract, lambda entry: required - {'ControlPid_Step'})
    assert runtime.ControlTask_Verify(tmp_path, graph, contract, lambda entry: required)['reachable']
    path.write_text(path.read_text() + '\n', encoding='utf8')
    with pytest.raises(ValueError, match='Changed reviewed control task contract'):
        runtime.ControlTask_Verify(tmp_path, graph, contract, lambda entry: required)


def test_disabled_control_case_rejects_a_linked_unbudgeted_kernel(tmp_path):
    path = tmp_path / 'Generated/control_research.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'schema_id': 'silverstar.control-research-runtime/1',
        'enabled': False, 'kind': None, 'period_us': 10000}), encoding='utf8')
    contract = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'enabled': False, 'kind': None}
    with pytest.raises(ValueError, match='Unexpected linked control kernel'):
        runtime.ControlTask_Verify(tmp_path, {'instructions': {'ControlPid_Step'}}, contract, lambda entry: set())

def _ExceptionFixture_Create(tmp_path):
    header = tmp_path / 'Drivers/device.h'
    header.parent.mkdir()
    header.write_text('#define __NVIC_PRIO_BITS 4U\n')
    entries = [0x20020000, 0x08000101, 0x08000201, 0x08000201] + [0] * 11 + [0x08000301]
    raw = b''.join(value.to_bytes(4, 'little') for value in entries)
    graph = {'nm': '08000000 00000040 R g_pfnVectors\n20020000 R _estack\n00000900 A _Min_Stack_Size\n',
        'elf': tmp_path / 'firmware.elf', 'function_entries': {
            'Reset_Handler': {'start': 0x08000100}, 'Fault_Handler': {'start': 0x08000200},
            'SysTick_Handler': {'start': 0x08000300}}}
    contract = {'vector_sha256': hashlib.sha256(raw).hexdigest(), 'cmsis_device_header': 'Drivers/device.h',
        'priority_bits': 4, 'priority_levels': 4, 'raw_priority_domain': [0, 5, 6, 15],
        'priority_write_review': 'All selected priority writes sealed and independently reviewed.'}
    counts = {'Reset_Handler': 596, 'Fault_Handler': 0, 'SysTick_Handler': 172}
    def Build():
        return runtime.WholeProgram_Build(tmp_path, graph, contract, '', lambda *args: raw,
            lambda name: (counts[name], [name]), 256)
    return graph, contract, Build

def test_whole_exception_model_retains_main_all_nested_fp_frames_and_fixed_faults(tmp_path):
    _, _, build = _ExceptionFixture_Create(tmp_path)
    report = build()
    assert report['worst_known_bytes'] == 596 + 4 * (172 + 108) + 2 * 108 == 1932
    assert report['margin_bytes'] == 372 and report['passes']

def test_prior_1024_msp_really_fails_unchanged_256_margin(tmp_path):
    graph, _, build = _ExceptionFixture_Create(tmp_path)
    graph['nm'] = graph['nm'].replace('00000900 A', '00000400 A')
    assert build()['passes'] is False

@pytest.mark.parametrize('change', ['vector', 'bits', 'levels', 'domain', 'review'])
def test_unreviewed_exception_domain_is_rejected(tmp_path, change):
    _, contract, build = _ExceptionFixture_Create(tmp_path)
    key, value = {'vector': ('vector_sha256', 'bad'), 'bits': ('priority_bits', 3),
        'levels': ('priority_levels', 3), 'domain': ('raw_priority_domain', [0, 5, 6]),
        'review': ('priority_write_review', None)}[change]
    contract[key] = value
    with pytest.raises(ValueError):
        build()
