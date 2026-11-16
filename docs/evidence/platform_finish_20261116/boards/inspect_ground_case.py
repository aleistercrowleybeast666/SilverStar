"""Capture actual Ground review candidate; never auto-enroll or grant acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[4]
GROUND = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools'
COMMON = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools'
sys.path[:0] = [str(GROUND), str(COMMON)]
import check_ground_stacks as gate
import check_task_stacks as stack
import ground_stack_runtime as runtime
import stack_review as review


def Inspect_Run(project, configuration):
    graph = gate.GroundGraph_Load(project, configuration, PREFIX)
    case = {'name': 'ssgs1-' + configuration, 'configuration': configuration,
            'target_profile': 'STM32C071FBP6', **gate.Inputs_Capture(project, graph, PREFIX)}
    reset = runtime.ResetStack_Resolve(graph)
    crt = runtime.CrtCallbacks_Resolve(project, graph, PREFIX, stack.TableBytes_Get)
    hal = runtime.runtime.HalCallbacks_Resolve(project, graph, PREFIX, stack.Command_Read,
                                               stack.CallbackSlot_Get, diagnostic=True)
    symbols = runtime.runtime.Symbols_Get(graph['nm'])
    vector = symbols['g_pfnVectors']
    raw = stack.TableBytes_Get(project, PREFIX, graph['elf'], vector['address'], vector['size'])
    contract = {'priority_bits': 2, 'priority_levels': 4, 'vector_sha256': hashlib.sha256(raw).hexdigest()}
    manual = {
        'handle_initialization_and_parent_links': 'Three actual BSS handles in Core/Src/usart.c, reciprocal RX/TX DMA Parent links and fixed IRQ dispatch reviewed in software_stack_ssgs_review_20261117.md.',
        'callback_installers_and_alias_writes': 'Complete selected C/header objects and retained UART constant callback installers reviewed, including macro aliases and whole-object assignment absence.',
        'object_type_at_each_linked_load': 'Actual DMA parameter / UART parameter / hdmarx child and every callback load were checked against concrete DWARF slots and linked instruction reaching definitions.',
        'null_only_field_initialization': 'RxISR/TxISR are in startup-cleared huart2 BSS; UART_SetConfig clears them and no retained non-NULL UART IT installer exists. SPI fields are a distinct type.',
        'no_runtime_registration': 'UART callback registration disabled and no application DMA registration or handle replacement; exact selected source and linked bytes sealed.'}
    hal_contract = {'schema': 'silverstar.hal-stack-objects/1', 'elf_sha256': review.FileHash_Get(graph['elf']),
        'sites': [{key: row[key] for key in ('caller', 'address', 'abi_slot', 'field', 'targets', 'null_only')} for row in hal],
        'bss_handles': runtime.runtime.HalHandles_Get(project, graph), 'manual_findings': manual}
    runtime.runtime.HalObjectContract_Verify(project, graph, hal_contract, hal)
    irq_symbols = stack.Command_Read([PREFIX + 'nm', '-n', str(graph['elf'])], project).replace('\r\n', '\n')
    gate.artifacts.InterruptVectors_Validate(project, graph['ground_declarations'], irq_symbols, raw)
    whole = runtime.WholeProgram_Build(project, graph, contract, PREFIX, stack.TableBytes_Get,
                                       gate.BudgetFunction_Get(graph), stack.MIN_MARGIN_BYTES)
    if graph['indirect'] or graph['unbounded'] or not whole['passes']:
        raise ValueError('Remaining unknowns or insufficient budget')
    document = 'software_stack_ssgs_review_20261117.md'
    case.update(review_document='Tools/' + document, review_document_sha256=review.FileHash_Get(GROUND / document),
                runtime_contract={'hal': hal_contract, 'exceptions': contract})
    return {'not_acceptance': True, 'requires_manual_case_admission': True, 'case_candidate': case,
        'diagnostic_msp': whole, 'reset': reset, 'crt': crt, 'hal': hal,
        'analysis_sha256': {str(path.relative_to(ROOT)): review.FileHash_Get(path)
            for path in [GROUND / 'check_ground_stacks.py', GROUND / 'ground_stack_runtime.py',
                         COMMON / 'check_task_stacks.py', COMMON / 'stack_arm.py', COMMON / 'stack_runtime.py']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('configuration', choices=('Release', 'Debug'))
    parser.add_argument('output', type=Path)
    parser.add_argument('--prefix', default='D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-')
    args = parser.parse_args()
    PREFIX = args.prefix
    if args.output.exists():
        raise ValueError('Do not overwrite an earlier inspection')
    try:
        result = Inspect_Run(args.project.resolve(), args.configuration)
    except Exception:
        result = {'not_acceptance': True, 'error': traceback.format_exc()}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(result.get('error', 'Candidate captured; manual admission still required.'))
    raise SystemExit(int('error' in result))
