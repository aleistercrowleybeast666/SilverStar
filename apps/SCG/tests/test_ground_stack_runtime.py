"""Actual C071 ARM runtime bytes and adversarial proof mutations."""
import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def runtime(workspace_root, monkeypatch):
    common = workspace_root / 'plugins/builtin/silverstar_core_0_1_0/payload/Tools'
    ground = workspace_root / 'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools'
    monkeypatch.syspath_prepend(str(common))
    monkeypatch.syspath_prepend(str(ground))
    return importlib.import_module('ground_stack_runtime')


@pytest.fixture
def machine(workspace_root, tmp_path):
    data = json.loads((workspace_root / 'tests/fixtures/c071_runtime_20261117.json').read_text())
    entries = deepcopy(data['function_entries'])
    for entry in entries.values():
        entry['memory'] = {int(k): v for k, v in entry.get('memory', {}).items()}
        entry['rows'] = [tuple(row) for row in entry.get('rows', ())]
    proofs = data['assembly_proofs']
    for proof in proofs.values():
        proof['successors'] = {int(k): v for k, v in proof['successors'].items()}
        proof['indirect'] = [tuple(row) for row in proof['indirect']]
    elf = tmp_path / 'test.elf'
    elf.write_bytes(bytes(256))  # Size bound only; machine inputs are the recorded fixture.
    graph = {'function_entries': entries, 'assembly_proofs': proofs, 'nm': data['nm'],
             'elf': elf, 'indirect': {'__libc_init_array', 'deregister_tm_clones', 'register_tm_clones'},
             'unbounded': {'Reset_Handler'}, 'edges': {name: set() for name in entries}}
    def table_read(_root, _prefix, _elf, start, size):
        result = bytes.fromhex(data['tables'][str(start)])
        assert len(result) == size
        return result
    return graph, table_read


def test_actual_c071_runtime_shapes_resolve_without_task_or_fp_assumptions(runtime, machine):
    graph, read = machine
    runtime.ResetStack_Resolve(graph)
    result = runtime.CrtCallbacks_Resolve(Path('.'), graph, '', read)
    assert not graph['unbounded'] and not graph['indirect']
    assert len(result) == 4
    assert graph['edges']['__libc_init_array']


@pytest.mark.parametrize('mutation', ['literal', 'unknown_sp', 'bypass', 'psp'])
def test_reset_rejects_unproved_stack_selection(runtime, machine, mutation):
    graph, _ = machine
    entry = graph['function_entries']['Reset_Handler']
    proof = graph['assembly_proofs']['Reset_Handler']
    if mutation == 'literal':
        pointer = ((entry['rows'][0][0] + 4) & ~3) + 52
        entry['memory'][pointer] ^= 4
    elif mutation == 'unknown_sp':
        proof['unknown_sp'].append(entry['rows'][4][0])
    elif mutation == 'bypass':
        proof['successors'][0] = [entry['rows'][1][0]]
    else:
        graph['function_entries']['evil'] = {'rows': [(0, 4, 'msr', 'control, r0')]}
    with pytest.raises(ValueError):
        runtime.ResetStack_Resolve(graph)


@pytest.mark.parametrize('mutation', ['pointer', 'comparison', 'bypass', 'array_target', 'loop'])
def test_crt_rejects_changed_pointer_guard_table_or_loop(runtime, machine, mutation):
    graph, read = machine
    entry = graph['function_entries']['deregister_tm_clones']
    if mutation == 'pointer':
        pointer = ((entry['rows'][5][0] + 4) & ~3) + 16
        entry['memory'][pointer] = 1
    elif mutation == 'comparison':
        address, size, op, _ = entry['rows'][6]
        entry['rows'][6] = (address, size, op, 'r3, #1')
    elif mutation == 'bypass':
        graph['assembly_proofs']['deregister_tm_clones']['successors'][0] = [entry['rows'][8][0]]
    elif mutation == 'array_target':
        read = lambda *_args: b'\x01\x00\x00\x00'
    else:
        init = graph['function_entries']['__libc_init_array']
        address, size, op, _ = init['rows'][20]
        init['rows'][20] = (address, size, op, 'r6, #2')
    with pytest.raises(ValueError):
        runtime.CrtCallbacks_Resolve(Path('.'), graph, '', read)


def test_m0_all_priority_levels_and_alignment_are_charged(runtime, machine, tmp_path):
    graph, read = machine
    device = tmp_path / 'Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h'
    device.parent.mkdir(parents=True)
    device.write_text('#define __NVIC_PRIO_BITS 2\n#include "core_cm0plus.h"\n')
    core = tmp_path / 'Drivers/CMSIS/Include/core_cm0plus.h'
    core.parent.mkdir(parents=True)
    core.write_text('#define __CORTEX_M (0U)\n')
    import hashlib
    vector = runtime.runtime.Symbols_Get(graph['nm'])['g_pfnVectors']
    raw = read(None, None, None, vector['address'], vector['size'])
    contract = {'priority_bits': 2, 'priority_levels': 4, 'vector_sha256': hashlib.sha256(raw).hexdigest()}
    result = runtime.WholeProgram_Build(tmp_path, graph, contract, '', read, lambda name: (100, [name]), 256)
    assert result['worst_known_bytes'] == 100 + 4 * (100 + 36) + 200 + 2 * 36
    assert result['exception_frame_bytes'] == 36
    for changed in ({**contract, 'priority_levels': 1}, {**contract, 'priority_bits': 4},
                    {**contract, 'vector_sha256': '0' * 64}):
        with pytest.raises(ValueError):
            runtime.WholeProgram_Build(tmp_path, graph, changed, '', read, lambda name: (100, [name]), 256)
