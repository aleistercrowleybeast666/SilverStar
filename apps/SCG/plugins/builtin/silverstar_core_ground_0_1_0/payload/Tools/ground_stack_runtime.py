"""Cortex-M0+ runtime proof, after complete source and linked-input sealing.

This is separate from the M4/M7 FreeRTOS adapter: Ground has no PSP task
switching, two implemented priority bits and no floating-point extension.
"""
import hashlib
import re

import stack_runtime as runtime


def ResetStack_Resolve(graph):
    for definition in graph['function_entries'].values():
        for _, _, op, args in definition.get('rows', ()):
            if op == 'msr' and args.split(',', 1)[0].strip().lower() in ('control', 'msp', 'psp'):
                raise ValueError('Unreviewed Ground stack/control register switch')
    entry = graph['function_entries']['Reset_Handler']
    rows = entry['rows']
    proof = graph['assembly_proofs']['Reset_Handler']
    symbols = runtime.Symbols_Get(graph['nm'])
    if (runtime.Instructions_Normalize(rows[:2]) != ['ldr r0,[pc,#52]', 'mov sp,r0'] or
            runtime.Literal_Read(entry, rows[0]) != symbols['_estack']['address'] or
            proof['unknown_sp'] != [rows[1][0]]):
        raise ValueError('Unreviewed Cortex-M0+ initial MSP assignment')
    predecessors = {address for address, targets in proof['successors'].items()
                    if rows[1][0] in targets}
    if predecessors != {rows[0][0]}:
        raise ValueError('Initial MSP literal assignment can be bypassed')
    graph['unbounded'].remove('Reset_Handler')
    return {'initial_msp': hex(symbols['_estack']['address']),
            'method': 'Entry LDR literal _estack, sole-predecessor MOV SP; no PSP/RTOS handoff.'}


def CrtCallbacks_Resolve(root, graph, prefix, table_read):
    result = []
    for name in ('deregister_tm_clones', 'register_tm_clones'):
        if name not in graph['indirect']:
            continue
        entry = graph['function_entries'][name]
        rows = entry['rows']
        proof = graph['assembly_proofs'][name]
        sites = proof['indirect']
        if len(sites) != 1 or sites[0][1:] != ('blx', 'r3'):
            raise ValueError('Unreviewed Cortex-M0+ CRT weak callback')
        index = next(i for i, row in enumerate(rows) if row[0] == sites[0][0])
        branch = rows[index - 1]
        target = re.fullmatch(r'([0-9a-f]+)\s+<[^>]+>', branch[3])
        if (index < 3 or runtime.Literal_Read(entry, rows[index - 3]) != 0 or
                runtime.Instructions_Normalize(rows[index - 2:index - 1]) != ['cmp r3,#0'] or
                branch[2].split('.')[0] != 'beq' or not target or
                not any(row[0] == int(target[1], 16) and
                        runtime.Instructions_Normalize([row]) == ['pop {r4,pc}'] for row in rows)):
            raise ValueError('Unproved Cortex-M0+ CRT weak NULL guard')
        for previous, current in zip(rows[index - 3:index], rows[index - 2:index + 1]):
            if {origin for origin, values in proof['successors'].items()
                    if current[0] in values} != {previous[0]}:
                raise ValueError('CRT weak callback guard can be bypassed')
        graph['indirect'].remove(name)
        result.append({'caller': name, 'linked_pointer': 0, 'guard': 'CMP zero / BEQ return dominates BLX'})
    name = '__libc_init_array'
    entry = graph['function_entries'][name]
    rows = entry['rows']
    normalized = runtime.Instructions_Normalize(rows)
    symbols = runtime.Symbols_Get(graph['nm'])
    for index, symbol in ((2, '__preinit_array_end'), (3, '__preinit_array_start'),
                          (10, '__init_array_end'), (11, '__init_array_start')):
        if runtime.Literal_Read(entry, rows[index]) != symbols[symbol]['address']:
            raise ValueError('CRT initializer does not use actual linked endpoints')
        normalized[index] = normalized[index].split(',', 1)[0] + ',' + symbol
    for index, value in enumerate(normalized):
        if '<__libc_init_array+' in value:
            normalized[index] = value.split(' ', 1)[0] + ' ' + value.split('<__libc_init_array+', 1)[1].removesuffix('>')
        elif '<_init>' in value:
            normalized[index] = 'bl _init'
    expected = ['push {r4,r5,r6,lr}', 'movs r6,#0', 'ldr r4,__preinit_array_end',
        'ldr r5,__preinit_array_start', 'subs r4,r4,r5', 'asrs r4,r4,#2', 'cmp r6,r4',
        'bne 0x24', 'movs r6,#0', 'bl _init', 'ldr r4,__init_array_end',
        'ldr r5,__init_array_start', 'subs r4,r4,r5', 'asrs r4,r4,#2', 'cmp r6,r4',
        'bne 0x2e', 'pop {r4,r5,r6,pc}', 'lsls r3,r6,#2', 'ldr r3,[r5,r3]',
        'blx r3', 'adds r6,#1', 'b 0xc', 'lsls r3,r6,#2', 'ldr r3,[r5,r3]',
        'blx r3', 'adds r6,#1', 'b 0x1e']
    if normalized != expected:
        raise ValueError('Unreviewed Cortex-M0+ CRT initializer loop shape')
    starts = {}
    for function, definition in graph['function_entries'].items():
        starts.setdefault(definition['start'] | 1, []).append(function)
    for label in ('__preinit_array', '__init_array'):
        start, end = symbols[label + '_start']['address'], symbols[label + '_end']['address']
        if end < start or (end - start) % 4 or end - start > graph['elf'].stat().st_size:
            raise ValueError('Invalid linked CRT initializer array bounds')
        raw = table_read(root, prefix, graph['elf'], start, end - start) if end > start else b''
        targets = []
        for offset in range(0, len(raw), 4):
            address = int.from_bytes(raw[offset:offset + 4], 'little')
            functions = starts.get(address)
            if not functions:
                raise ValueError('CRT initializer is not an actual Thumb function entry')
            graph['edges'][name].update(functions)
            targets.extend(functions)
        result.append({'caller': name, 'array': label, 'bytes': len(raw), 'targets': sorted(targets)})
    if len(graph['assembly_proofs'][name]['indirect']) != 2:
        raise ValueError('Unreviewed CRT initializer callback count')
    graph['indirect'].remove(name)
    return result


def WholeProgram_Build(root, graph, contract, prefix, table_read, budget_get, minimum_margin):
    symbols = runtime.Symbols_Get(graph['nm'])
    header = root / 'Drivers/CMSIS/Device/ST/STM32C0xx/Include/stm32c071xx.h'
    text = header.read_text(encoding='utf8')
    core = (root / 'Drivers/CMSIS/Include/core_cm0plus.h').read_text(encoding='utf8')
    if (not re.search(r'#define\s+__NVIC_PRIO_BITS\s+2[Uu]?\b', text) or
            '#include "core_cm0plus.h"' not in text or
            not re.search(r'#define\s+__CORTEX_M\s+\(0[Uu]?\)', core) or
            contract.get('priority_bits') != 2 or contract.get('priority_levels') != 4):
        raise ValueError('Unreviewed Cortex-M0+ exception architecture')
    vector = symbols.get('g_pfnVectors')
    if not vector or vector['kind'] not in ('r', 'R') or vector['size'] < 64 or vector['size'] % 4:
        raise ValueError('Missing complete Cortex-M0+ vector table')
    raw = table_read(root, prefix, graph['elf'], vector['address'], vector['size'])
    if len(raw) != vector['size'] or hashlib.sha256(raw).hexdigest() != contract.get('vector_sha256'):
        raise ValueError('Changed reviewed Cortex-M0+ vector table')
    values = [int.from_bytes(raw[i:i + 4], 'little') for i in range(0, len(raw), 4)]
    if values[:2] != [symbols['_estack']['address'], graph['function_entries']['Reset_Handler']['start'] | 1]:
        raise ValueError('Cortex-M0+ initial MSP/reset vector mismatch')
    by_address = {}
    for name, entry in graph['function_entries'].items():
        by_address.setdefault(entry['start'] | 1, []).append(name)
    budgets = []
    for number, address in enumerate(values[2:], 2):
        if address == 0:
            continue
        targets = by_address.get(address)
        if not targets:
            raise ValueError('Exception points outside actual linked function entries')
        count, chain = max((budget_get(name) for name in targets), key=lambda value: value[0])
        budgets.append({'exception_number': number, 'targets': sorted(targets),
                        'call_chain_bytes': count, 'chain': chain})
    if {2, 3} - {row['exception_number'] for row in budgets}:
        raise ValueError('Missing NMI/HardFault proof')
    reset, chain = budget_get('Reset_Handler')
    configurable = max(row['call_chain_bytes'] for row in budgets if row['exception_number'] >= 4)
    fixed = sum(row['call_chain_bytes'] for row in budgets if row['exception_number'] in (2, 3))
    frame = 36  # Eight core registers, plus worst-case 4-byte alignment padding; no FPU on M0+.
    estimate = reset + 4 * (configurable + frame) + fixed + 2 * frame
    allocated = symbols['_Min_Stack_Size']['address']
    return {'configured_bytes': allocated, 'main_reset_bytes': reset, 'main_reset_chain': chain,
            'priority_bits': 2, 'priority_levels': 4, 'exception_frame_bytes': frame,
            'maximum_configurable_handler_bytes': configurable, 'fixed_handler_bytes': fixed,
            'worst_known_bytes': estimate, 'margin_bytes': allocated - estimate,
            'passes': allocated - estimate >= minimum_margin, 'vectors': budgets,
            'method': 'Reset/main plus all four configurable priority levels, NMI and HardFault; 36-byte basic frames.'}
