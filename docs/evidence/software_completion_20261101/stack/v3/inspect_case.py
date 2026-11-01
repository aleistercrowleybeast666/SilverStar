"""Capture candidate proof inputs for review; never writes the owning manifest."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[5]
TOOLS = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools'
PREFIX = 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-'

def Module_Load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def Inspect_Run(project, configuration, name):
    checker, runtime, review = (Module_Load(module) for module in ('check_task_stacks', 'stack_runtime', 'stack_review'))
    graph = None
    try:
        checker.StackReport_Build(project, configuration, PREFIX)
    except Exception as error:
        rejection = str(error)
        trace = error.__traceback__
        while trace:
            if trace.tb_frame.f_code.co_name == 'StackReport_Build':
                graph = trace.tb_frame.f_locals.get('graph')
            trace = trace.tb_next
    if graph is None:
        raise ValueError('Expected an unadmitted candidate, not an accepted or missing graph')
    hal = runtime.HalCallbacks_Resolve(project, graph, PREFIX, checker.Command_Read, checker.CallbackSlot_Get, diagnostic=True)
    port = runtime.PortStackPointers_Resolve(project, graph)
    crt = runtime.CrtCallbacks_Resolve(project, graph, PREFIX, checker.TableBytes_Get)
    target = json.loads((project / 'SilverStar.ssproject').read_text())['build']['target_profile']
    declarations = {'Makefile', *(path.relative_to(project).as_posix() for path in project.rglob('*.mk')
        if path.relative_to(project).parts[0] not in ('build', '.git', '.fccg'))}
    inputs = {*graph['sources'], *(path.relative_to(project).as_posix() for path in project.rglob('*')
        if path.is_file() and path.suffix.lower() in ('.h', '.inc', '.s', '.ld')
        and path.relative_to(project).parts[0] not in ('build', '.git', '.fccg'))}
    vector = runtime.Symbols_Get(graph['nm'])['g_pfnVectors']
    vector_bytes = checker.TableBytes_Get(project, PREFIX, graph['elf'], vector['address'], vector['size'])
    h7 = 'H7' in target.upper()
    exceptions = {'vector_sha256': hashlib.sha256(vector_bytes).hexdigest(), 'priority_bits': 4,
        'cmsis_device_header': 'Drivers/CMSIS/Device/ST/STM32H7xx/Include/stm32h743xx.h' if h7 else
                               'Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f407xx.h',
        'priority_levels': 16 if h7 else 4}
    if not h7:
        exceptions.update(raw_priority_domain=[0, 5, 6, 15],
                          priority_write_review='software_stack_review.md: Main/MSP and exception nesting; complete source and linked byte seal required.')
    case = {'name': name, 'target_profile': target, 'configuration': configuration,
        'sources': sorted(graph['sources']),
        'compiler': checker.Command_Read([PREFIX + 'gcc', '--version'], project).splitlines()[0],
        'build_declarations': {path: review.FileHash_Get(project / path, source=True) for path in sorted(declarations)},
        'source_inputs': {path: review.FileHash_Get(project / path, source=True) for path in sorted(inputs)},
        'compiled_artifacts': {path: review.FileHash_Get(graph['build'] / path) for path in review.ArtifactPaths_Get(project, graph)},
        'toolchain_files': review.ToolchainInputs_Get(project, graph, PREFIX, checker.Command_Read),
        'review_document': 'Tools/software_stack_review.md',
        'review_document_sha256': review.FileHash_Get(TOOLS / 'software_stack_review.md'),
        'runtime_contract': {'hal': {
            'schema': 'silverstar.hal-stack-objects/1', 'elf_sha256': review.FileHash_Get(graph['elf']),
            'sites': [{key: row[key] for key in ('caller', 'address', 'abi_slot', 'field', 'targets', 'null_only')} for row in hal],
            'bss_handles': runtime.HalHandles_Get(project, graph),
            'manual_findings': {
                'handle_initialization_and_parent_links': 'Reviewed concrete CubeMX global handles, startup BSS interval, MX/MSP initialization and reciprocal __HAL_LINKDMA parent links; see review document.',
                'callback_installers_and_alias_writes': 'Reviewed typed HAL installers and source references, including dot assignments, macro aliases and whole-object copies; union of actual linked constant callbacks retained.',
                'object_type_at_each_linked_load': 'Reviewed DMA handler parameter and UART parameter/hdmarx child at actual indirect loads; sealed compiler output and actual DWARF/reaching definitions checked.',
                'null_only_field_initialization': 'Reviewed actual BSS initialization and absence of linked non-NULL installers for M1 and H7 DMA-only UART fields; unrelated NULL writes alone are not evidence.',
                'no_runtime_registration': 'Reviewed disabled UART registration and absent/unreferenced DMA registration APIs; no selected application runtime callback registry or handle replacement.'}},
            'exceptions': exceptions}}
    memo = {}
    def Budget_Get(node, visiting=()):
        if node in visiting or node in graph['indirect'] or node in graph['unbounded']:
            raise ValueError('Unproved reachable stack: ' + repr(visiting + (node,)))
        if node not in memo:
            children = [Budget_Get(child, visiting + (node,)) for child in sorted(graph['edges'].get(node, ()))]
            count, chain = max(children, default=(0, []), key=lambda item: item[0])
            memo[node] = (graph['frames'][node] + count, [node] + chain)
        return memo[node]
    whole = runtime.WholeProgram_Build(project, graph, exceptions, PREFIX, checker.TableBytes_Get,
                                       Budget_Get, checker.MIN_MARGIN_BYTES)
    runtime.HalObjectContract_Verify(project, graph, case['runtime_contract']['hal'], hal)
    return {'not_acceptance': True, 'requires_manual_case_admission': True, 'strict_rejection': rejection,
        'tool_hashes': {path.name: review.FileHash_Get(path) for path in TOOLS.glob('stack_*.py')},
        'case_candidate': case, 'diagnostic_msp': whole,
        'diagnostic_tasks': {label: {'budget': Budget_Get(entry), 'configured': graph['sizes'][stack],
                                   'context': checker.CONTEXT_BYTES}
                            for label, (entry, stack) in checker.TASKS.items()},
        'port': port, 'crt': crt, 'hal_details': hal,
        'remaining_indirect': sorted(graph['indirect']), 'remaining_unbounded': sorted(graph['unbounded'])}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('configuration', choices=('Release', 'Debug'))
    parser.add_argument('name')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Do not overwrite a prior review result')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = Inspect_Run(args.project.resolve(), args.configuration, args.name)
    except Exception:
        report = {'not_acceptance': True, 'error': traceback.format_exc()}
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(args.name, report.get('error', 'candidate captured for manual review'), flush=True)
    raise SystemExit(int('error' in report))
