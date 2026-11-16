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
import ground_stack_runtime_m3 as runtime
import stack_review as review


def Inspect_Run(project, configuration):
    graph = gate.GroundGraph_Load(project, configuration, PREFIX)
    case = {'name': 'f103-e19-' + configuration, 'configuration': configuration,
            'target_profile': 'STM32F103C8T6', **gate.Inputs_Capture(project, graph, PREFIX)}
    reset = runtime.ResetStack_Resolve(graph)
    crt = runtime.CrtCallbacks_Resolve(project, graph, PREFIX, stack.TableBytes_Get)
    hal = runtime.runtime.HalCallbacks_Resolve(project, graph, PREFIX, stack.Command_Read,
                                               stack.CallbackSlot_Get, diagnostic=True)
    symbols = runtime.runtime.Symbols_Get(graph['nm'])
    raw = runtime.VectorTable_Get(project, graph, PREFIX, stack.TableBytes_Get, stack.Command_Read)
    contract = {'priority_bits': 4, 'priority_levels': 16, 'vector_sha256': hashlib.sha256(raw).hexdigest(),
                'required_irq_handlers': ['SysTick_Handler', 'EXTI0_IRQHandler', 'DMA1_Channel4_IRQHandler',
                                          'DMA1_Channel5_IRQHandler', 'USART1_IRQHandler']}
    manual = {
        'handle_initialization_and_parent_links': 'Three actual BSS handles in HardwareGenerated/STM32CubeMX/Core/Src/usart.c: huart1 72B, RX/TX DMA68B, reciprocal links and fixed five IRQ dispatch reviewed in software_stack_f103_ground_review_20261117.md.',
        'callback_installers_and_alias_writes': 'Complete selected C/header objects and retained UART constant callback installers reviewed, including macro aliases and whole-object assignment absence.',
        'object_type_at_each_linked_load': 'Actual DMA parameter / UART parameter / hdmarx child and every callback load were checked against concrete DWARF slots and linked instruction reaching definitions.',
        'null_only_field_initialization': 'F1 UART has no M0+ RxISR/TxISR callback slot. Actual DMA callback slots40/44/48/52 are BSS-cleared or written by retained constant UART DMA installers; HAL_UART_AbortReceive clears callbacks; independent cross-review recorded.',
        'no_runtime_registration': 'UART callback registration disabled and no application DMA registration or handle replacement; exact selected source and linked bytes sealed.'}
    hal_contract = {'schema': 'silverstar.hal-stack-objects/1', 'elf_sha256': review.FileHash_Get(graph['elf']),
        'sites': [{key: row[key] for key in ('caller', 'address', 'abi_slot', 'field', 'targets', 'null_only')} for row in hal],
        'bss_handles': runtime.runtime.HalHandles_Get(project, graph), 'manual_findings': manual}
    runtime.runtime.HalObjectContract_Verify(project, graph, hal_contract, hal)
    irq_symbols = stack.Command_Read([PREFIX + 'nm', '-n', str(graph['elf'])], project).replace('\r\n', '\n')
    gate.artifacts.InterruptVectors_Validate(project, {**graph['ground_declarations'], 'required_irq_handlers': contract['required_irq_handlers']}, irq_symbols, raw)
    whole = runtime.WholeProgram_Build(project, graph, contract, PREFIX, stack.TableBytes_Get,
                                       gate.BudgetFunction_Get(graph), stack.MIN_MARGIN_BYTES, stack.Command_Read)
    if graph['indirect'] or graph['unbounded'] or not whole['passes']:
        raise ValueError('Remaining unknowns or insufficient budget')
    document = 'software_stack_f103_ground_review_20261117.md'
    case.update(review_document='Tools/' + document, review_document_sha256=review.FileHash_Get(GROUND / document),
                runtime_contract={'hal': hal_contract, 'exceptions': contract})
    return {'not_acceptance': True, 'requires_manual_case_admission': True, 'case_candidate': case,
        'diagnostic_msp': whole, 'reset': reset, 'crt': crt, 'hal': hal,
        'analysis_sha256': {str(path.relative_to(ROOT)): review.FileHash_Get(path)
            for path in [GROUND / 'check_ground_stacks.py', GROUND / 'ground_stack_runtime_m3.py',
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
