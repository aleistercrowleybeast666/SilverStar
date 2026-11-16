"""Actual STM32F103xB runtime bytes and fail-closed mutations; no MCU tests."""
import hashlib
import importlib
import json
from copy import deepcopy

import pytest


@pytest.fixture
def runtime(workspace_root, monkeypatch):
    monkeypatch.syspath_prepend(str(workspace_root / 'plugins/builtin/silverstar_core_0_1_0/payload/Tools'))
    monkeypatch.syspath_prepend(str(workspace_root / 'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools'))
    return importlib.import_module('ground_stack_runtime_m3')


@pytest.fixture
def machine(workspace_root, tmp_path):
    data = json.loads((workspace_root / 'tests/fixtures/f103_runtime_20261117.json').read_bytes())
    entries = deepcopy(data['function_entries'])
    for entry in entries.values():
        entry['memory'] = {int(k): v for k, v in entry.get('memory', {}).items()}
        entry['rows'] = [tuple(row) for row in entry.get('rows', ())]
    proofs = data['assembly_proofs']
    for proof in proofs.values():
        proof['successors'] = {int(k): v for k, v in proof['successors'].items()}
        proof['indirect'] = [tuple(row) for row in proof['indirect']]
    elf = tmp_path / 'fixture.elf'
    elf.write_bytes(bytes(512))  # Bound only: all machine inputs come from the recorded ARM fixture.
    graph = {'function_entries': entries, 'assembly_proofs': proofs, 'nm': data['nm'], 'elf': elf,
             'indirect': {'__libc_init_array', 'deregister_tm_clones', 'register_tm_clones'},
             'unbounded': set(), 'edges': {name: set() for name in entries}}
    device = tmp_path / 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xb.h'
    device.parent.mkdir(parents=True)
    device.write_text('#define __NVIC_PRIO_BITS 4U\n#include "core_cm3.h"\nUSBWakeUp_IRQn = 42,\n')
    core = tmp_path / 'Drivers/CMSIS/Include/core_cm3.h'
    core.parent.mkdir(parents=True)
    core.write_text('#define __CORTEX_M (3U)\n')
    def table_read(_root, _prefix, _elf, start, size):
        result = bytes.fromhex(data['tables'][str(start)])
        assert len(result) == size
        return result
    return graph, table_read, lambda *_args: data['sections'], tmp_path


def test_actual_m3_reset_crt_and_complete_vectors(runtime, machine):
    graph, read, command, root = machine
    runtime.ResetStack_Resolve(graph)
    result = runtime.CrtCallbacks_Resolve(root, graph, '', read)
    assert not graph['indirect'] and not graph['unbounded'] and len(result) == 4
    raw = runtime.VectorTable_Get(root, graph, '', read, command)
    assert len(raw) == 0x10C and int.from_bytes(raw[-4:], 'little') == 0xF108F85F


@pytest.mark.parametrize('mutation', ['unknown_sp', 'psp', 'msp', 'control'])
def test_m3_rejects_software_stack_switches(runtime, machine, mutation):
    graph, _, _, _ = machine
    if mutation == 'unknown_sp':
        graph['assembly_proofs']['Reset_Handler']['unknown_sp'] = [0]
    else:
        graph['function_entries']['bad'] = {'rows': [(0, 4, 'msr', mutation + ', r0')]}
    with pytest.raises(ValueError):
        runtime.ResetStack_Resolve(graph)


@pytest.mark.parametrize('mutation', ['endpoint', 'missing_literal', 'stride', 'counter', 'branch',
                                     'callback_count', 'target', 'thumb_bit', 'short_table'])
def test_m3_initializer_requires_exact_finite_machine_code(runtime, machine, mutation):
    graph, read, _, root = machine
    entry = graph['function_entries']['__libc_init_array']
    if mutation in ('endpoint', 'missing_literal'):
        address, _, _, args = entry['rows'][2]
        import re
        offset = int(re.search(r'#(\d+)', args)[1])
        pointer = ((address + 4) & ~3) + offset
        if mutation == 'endpoint': entry['memory'][pointer] ^= 4
        else: del entry['memory'][pointer]
    elif mutation in ('stride', 'counter', 'branch'):
        index, operand = {'stride': (17, 'r3, [r5], #8'), 'counter': (1, 'r6, #1'),
                          'branch': (7, '0 <outside>')}[mutation]
        address, size, op, _ = entry['rows'][index]
        entry['rows'][index] = (address, size, op, operand)
    elif mutation == 'callback_count':
        graph['assembly_proofs']['__libc_init_array']['indirect'].append((0, 'blx', 'r3'))
    else:
        original = read
        def altered(*args):
            raw = original(*args)
            if mutation == 'short_table': return raw[:-1]
            value = int.from_bytes(raw, 'little')
            return ((value & ~1) if mutation == 'thumb_bit' else 1).to_bytes(len(raw), 'little')
        read = altered
    with pytest.raises(ValueError):
        runtime.CrtCallbacks_Resolve(root, graph, '', read)


@pytest.mark.parametrize('mutation', ['writable', 'size', 'initial_sp', 'reset', 'reserved',
                                     'boot', 'short', 'priority', 'core', 'irq_count'])
def test_m3_vector_extent_and_boot_trailer_are_not_skipped(runtime, machine, mutation):
    graph, read, command, root = machine
    if mutation in ('writable', 'size'):
        text = command()
        text = text.replace('CONTENTS, ALLOC, LOAD, READONLY, DATA', 'CONTENTS, ALLOC, LOAD, DATA') if mutation == 'writable' else text.replace('0000010c', '00000108')
        command = lambda *_args: text
    elif mutation in ('priority', 'core', 'irq_count'):
        path = root / ('Drivers/CMSIS/Include/core_cm3.h' if mutation == 'core' else
                       'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xb.h')
        path.write_text(path.read_text().replace('4U', '2U') if mutation == 'priority' else
                        path.read_text().replace('(3U)', '(4U)') if mutation == 'core' else
                        path.read_text().replace('42,', '43,'))
    else:
        original = read
        def altered(*args):
            raw = bytearray(original(*args))
            if mutation == 'short': return bytes(raw[:-4])
            offset = {'initial_sp': 0, 'reset': 4, 'reserved': 59 * 4, 'boot': 66 * 4}[mutation]
            raw[offset] ^= 4
            return bytes(raw)
        read = altered
    with pytest.raises(ValueError):
        runtime.VectorTable_Get(root, graph, '', read, command)


def test_m3_all_sixteen_levels_and_insufficient_original_msp_block_acceptance(runtime, machine):
    graph, read, command, root = machine
    raw = runtime.VectorTable_Get(root, graph, '', read, command)
    contract = {'priority_bits': 4, 'priority_levels': 16, 'vector_sha256': hashlib.sha256(raw).hexdigest()}
    budget = lambda name: (100, [name])
    result = runtime.WholeProgram_Build(root, graph, contract, '', read, budget, 256, command)
    assert result['worst_known_bytes'] == 100 + 16 * (100 + 36) + 200 + 2 * 36
    assert result['configured_bytes'] == 1024 and not result['passes']
    for changed in ({**contract, 'priority_levels': 4}, {**contract, 'priority_bits': 2},
                    {**contract, 'vector_sha256': '0' * 64}):
        with pytest.raises(ValueError):
            runtime.WholeProgram_Build(root, graph, changed, '', read, budget, 256, command)


def test_m3_unknown_hardware_vector_still_rejected(runtime, machine):
    graph, read, command, root = machine
    original = read
    def changed(*args):
        raw = bytearray(original(*args))
        raw[16 * 4:17 * 4] = b'\x01\x00\x00\x00'
        return bytes(raw)
    raw = changed(None, None, None, 0x8000000, 0x10C)
    contract = {'priority_bits': 4, 'priority_levels': 16, 'vector_sha256': hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError):
        runtime.WholeProgram_Build(root, graph, contract, '', changed, lambda name: (0, [name]), 256, command)
