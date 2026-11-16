"""Exact STM32F103xB no-RTOS runtime, after complete source/object sealing."""
import hashlib
import re

import stack_runtime as runtime


def ResetStack_Resolve(graph):
    if graph['assembly_proofs']['Reset_Handler']['unknown_sp']:
        raise ValueError('Unresolved Cortex-M3 Reset stack assignment')
    for entry in graph['function_entries'].values():
        for _, _, op, args in entry.get('rows', ()):
            if op == 'msr' and args.split(',', 1)[0].strip().lower() in ('control', 'msp', 'psp'):
                raise ValueError('Unreviewed Cortex-M3 stack/control switch')
    return {'method': 'Hardware reset vector initializes MSP; no linked MSP/PSP/CONTROL switch.'}


def CrtCallbacks_Resolve(root, graph, prefix, table_read):
    result = runtime.CrtWeakCallbacks_Resolve(graph)
    name = '__libc_init_array'
    symbols = runtime.Symbols_Get(graph['nm'])
    entry = graph['function_entries'][name]
    rows = entry['rows']
    normalized = runtime.Instructions_Normalize(rows)
    for index, symbol in ((2, '__preinit_array_start'), (3, '__preinit_array_end'),
                          (10, '__init_array_start'), (11, '__init_array_end')):
        if runtime.Literal_Read(entry, rows[index]) != symbols[symbol]['address']:
            raise ValueError('Cortex-M3 CRT does not load actual linked table endpoints')
        normalized[index] = normalized[index].split(',', 1)[0] + ',' + symbol
    for index, value in enumerate(normalized):
        if '<__libc_init_array+' in value:
            normalized[index] = value.split(' ', 1)[0] + ' ' + value.split('<__libc_init_array+', 1)[1].removesuffix('>')
        elif '<_init>' in value:
            normalized[index] = 'bl _init'
    expected = ['push {r4,r5,r6,lr}', 'movs r6,#0', 'ldr r5,__preinit_array_start',
        'ldr r3,__preinit_array_end', 'subs r3,r3,r5', 'asrs r4,r3,#2', 'cmp r6,r4',
        'bne 0x24', 'movs r6,#0', 'bl _init', 'ldr r5,__init_array_start',
        'ldr r3,__init_array_end', 'subs r3,r3,r5', 'asrs r4,r3,#2', 'cmp r6,r4',
        'bne 0x2e', 'pop {r4,r5,r6,pc}', 'ldr r3,[r5],#4', 'blx r3', 'adds r6,#1',
        'b 0xc', 'ldr r3,[r5],#4', 'blx r3', 'adds r6,#1', 'b 0x1e']
    if normalized != expected or len(graph['assembly_proofs'][name]['indirect']) != 2:
        raise ValueError('Unreviewed Cortex-M3 CRT initializer loop shape')
    starts = {}
    for function, definition in graph['function_entries'].items():
        starts.setdefault(definition['start'] | 1, []).append(function)
    for label in ('__preinit_array', '__init_array'):
        start, end = symbols[label + '_start']['address'], symbols[label + '_end']['address']
        if end < start or (end - start) % 4 or end - start > graph['elf'].stat().st_size:
            raise ValueError('Invalid Cortex-M3 CRT table bounds')
        raw = table_read(root, prefix, graph['elf'], start, end - start) if end > start else b''
        if len(raw) != end - start:
            raise ValueError('Incomplete Cortex-M3 CRT table bytes')
        targets = []
        for offset in range(0, len(raw), 4):
            pointer = int.from_bytes(raw[offset:offset + 4], 'little')
            functions = starts.get(pointer)
            if not functions:
                raise ValueError('CRT initializer is not an actual Thumb function entry')
            graph['edges'][name].update(functions)
            targets.extend(functions)
        result.append({'caller': name, 'array': label, 'bytes': len(raw), 'targets': sorted(targets)})
    graph['indirect'].remove(name)
    return result


def VectorTable_Get(root, graph, prefix, table_read, command_read):
    symbols = runtime.Symbols_Get(graph['nm'])
    vector = symbols.get('g_pfnVectors')
    sections = command_read([prefix + 'objdump', '-h', str(graph['elf'])], root)
    matches = re.findall(r'(?m)^\s*\d+\s+\.isr_vector\s+([0-9a-f]+)\s+([0-9a-f]+)[^\r\n]*\r?\n'
                         r'\s*CONTENTS, ALLOC, LOAD, READONLY, DATA\s*$', sections)
    if (not vector or vector['kind'] not in ('r', 'R') or vector['size'] not in (0, 0x10C) or
            len(matches) != 1 or int(matches[0][0], 16) != 0x10C or
            int(matches[0][1], 16) != vector['address']):
        raise ValueError('Missing complete readonly STM32F103xB vector section')
    header = (root / 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xb.h').read_text(encoding='utf8')
    core = (root / 'Drivers/CMSIS/Include/core_cm3.h').read_text(encoding='utf8')
    if (not re.search(r'#define\s+__NVIC_PRIO_BITS\s+4[Uu]?\b', header) or
            '#include "core_cm3.h"' not in header or
            not re.search(r'USBWakeUp_IRQn\s*=\s*42\s*[,}]', header) or
            not re.search(r'#define\s+__CORTEX_M\s+\(3[Uu]?\)', core)):
        raise ValueError('Unreviewed STM32F103xB exception architecture')
    raw = table_read(root, prefix, graph['elf'], vector['address'], 0x10C)
    if len(raw) != 0x10C:
        raise ValueError('Incomplete STM32F103xB linked vector bytes')
    values = [int.from_bytes(raw[i:i + 4], 'little') for i in range(0, len(raw), 4)]
    if (values[:2] != [symbols['_estack']['address'], graph['function_entries']['Reset_Handler']['start'] | 1] or
            values[59:66] != [0] * 7 or values[66] != 0xF108F85F or
            symbols.get('BootRAM', {}).get('address') != 0xF108F85F):
        raise ValueError('Changed initial MSP/reset vector or non-vector F103 boot trailer')
    return raw


def WholeProgram_Build(root, graph, contract, prefix, table_read, budget_get, minimum_margin, command_read):
    if contract.get('priority_bits') != 4 or contract.get('priority_levels') != 16:
        raise ValueError('All Cortex-M3 implemented priority levels must be budgeted')
    raw = VectorTable_Get(root, graph, prefix, table_read, command_read)
    if hashlib.sha256(raw).hexdigest() != contract.get('vector_sha256'):
        raise ValueError('Changed reviewed STM32F103xB vector bytes')
    by_address = {}
    for name, entry in graph['function_entries'].items():
        by_address.setdefault(entry['start'] | 1, []).append(name)
    budgets = []
    for number in range(2, 59):
        address = int.from_bytes(raw[number * 4:number * 4 + 4], 'little')
        if address == 0:
            continue
        targets = by_address.get(address)
        if not targets:
            raise ValueError('Exception is not an actual linked Thumb function entry')
        count, chain = max((budget_get(name) for name in targets), key=lambda item: item[0])
        budgets.append({'exception_number': number, 'targets': sorted(targets),
                        'call_chain_bytes': count, 'chain': chain})
    if {2, 3} - {row['exception_number'] for row in budgets}:
        raise ValueError('Missing NMI/HardFault proof')
    reset, chain = budget_get('Reset_Handler')
    configurable = max(row['call_chain_bytes'] for row in budgets if row['exception_number'] >= 4)
    fixed = sum(row['call_chain_bytes'] for row in budgets if row['exception_number'] in (2, 3))
    frame = 36  # Eight core registers + conservative alignment word; Cortex-M3 has no FPU.
    estimate = reset + 16 * (configurable + frame) + fixed + 2 * frame
    allocated = runtime.Symbols_Get(graph['nm'])['_Min_Stack_Size']['address']
    return {'configured_bytes': allocated, 'main_reset_bytes': reset, 'main_reset_chain': chain,
            'priority_bits': 4, 'priority_levels': 16, 'exception_frame_bytes': frame,
            'maximum_configurable_handler_bytes': configurable, 'fixed_handler_bytes': fixed,
            'worst_known_bytes': estimate, 'margin_bytes': allocated - estimate,
            'passes': allocated - estimate >= minimum_margin, 'vectors': budgets,
            'method': 'Reset/main plus all 16 configurable levels, NMI/HardFault; 36-byte basic frames. '
                      '59 hardware vector slots; separately verified reserved words and BootRAM trailer.'}
