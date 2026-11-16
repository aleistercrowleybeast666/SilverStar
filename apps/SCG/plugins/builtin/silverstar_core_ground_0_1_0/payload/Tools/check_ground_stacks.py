"""Strict Ground stack gate: complete inputs, actual objects and all vectors.

The shared graph loader only parses machine code. This owner validates Ground's
Make/source graph and compiler dependencies before consulting a sealed review.
"""
import argparse
import json
from pathlib import Path

import check_ground
import check_task_stacks as stack
import ground_artifact_contract as artifacts
import ground_stack_runtime as runtime
import ground_stack_runtime_m3 as runtime_m3
import stack_review as review

REVIEW_SHA256 = '8fad07a2e2387645c3d941ef867623b42270bcc420a8f7927bcc6353e7d78543'


def RuntimeAdapter_Get(declared):
    for name, cpu, startup, define, adapter in (
            ('cortex_m0plus', 'cortex-m0plus', 'startup_stm32c071xx.s', 'STM32C071xx', runtime),
            ('cortex_m3', 'cortex-m3', 'startup_stm32f103xb.s', 'STM32F103xB', runtime_m3)):
        if (declared['mcu_flags'] == ['-mcpu=' + cpu, '-mthumb', '-mfloat-abi=soft'] and
                declared['asm_sources'] == [startup] and define in declared['defines']):
            return name, adapter
    raise ValueError('No reviewed Ground stack architecture for this target')


def GroundGraph_Load(root, configuration, prefix):
    root = root.resolve(strict=True)
    if configuration not in ('Release', 'Debug'):
        raise ValueError('Unsupported Ground stack configuration')
    build_dir = 'build' if configuration == 'Release' else 'build/Debug'
    declared = check_ground.Architecture_Check(root)
    RuntimeAdapter_Get(declared)
    artifacts.DependencyClosure_Validate(root, declared, prefix + 'gcc', build_dir=build_dir)
    build = root / build_dir
    expected_objects = {Path(name).with_suffix('.o').as_posix()
                        for name in declared['sources'] + declared['asm_sources']}
    actual_objects = {path.relative_to(build).as_posix() for path in build.rglob('*.o')
                      if path.relative_to(build).parts[0] not in ('Debug', 'analysis')}
    if expected_objects != actual_objects:
        raise ValueError('Actual Ground objects differ from the complete selected source graph')
    graph = stack.StackGraph_LoadInputs(root, build, prefix, declared['sources'])
    graph['ground_declarations'] = declared
    return graph


def ArtifactPaths_Get(graph):
    names = {Path(source).with_suffix(suffix).as_posix()
             for source in graph['sources'] for suffix in ('.o', '.su', '.d', '.gas.d', '.deps.mk', '.s')}
    for source in graph['ground_declarations']['asm_sources']:
        stem = Path(source).with_suffix('')
        names.update(stem.as_posix() + suffix for suffix in ('.o', '.d', '.gas.d', '.deps.mk', '.s'))
    names.update((graph['elf'].name, graph['elf'].with_suffix('.map').name))
    return sorted(names)


def Inputs_Capture(root, graph, prefix):
    """Capture facts for comparison; this function grants no acceptance."""
    inputs = {*graph['sources'], *(path.relative_to(root).as_posix() for path in root.rglob('*')
        if path.is_file() and path.suffix.lower() in ('.h', '.inc', '.s', '.ld') and
        path.relative_to(root).parts[0] not in ('build', '.git', '.fccg'))}
    declarations = {'Makefile', 'Generated/ground_source_graph.json',
                    *(path.relative_to(root).as_posix() for path in root.rglob('*.mk')
                      if path.relative_to(root).parts[0] not in ('build', '.git', '.fccg'))}
    metadata = json.loads((root / 'Generated/ground_target_metadata.json').read_bytes())
    # These owner receipts include this review's own payload hash. They are
    # provenance, never compiler inputs; every other semantic field is sealed.
    for key in ('generation_authority_sha256', 'generation_input_sha256', 'component_locks'):
        metadata.pop(key)
    return {'sources': sorted(graph['sources']),
        'metadata_semantics': metadata,
        'build_declarations': {name: review.FileHash_Get(review.InputPath_Get(root, name), source=True)
                               for name in sorted(declarations)},
        'source_inputs': {name: review.FileHash_Get(review.InputPath_Get(root, name), source=True)
                          for name in sorted(inputs)},
        'compiled_artifacts': {name: review.FileHash_Get(review.InputPath_Get(graph['build'], name))
                               for name in ArtifactPaths_Get(graph)},
        'compiler': stack.Command_Read([prefix + 'gcc', '--version'], root).splitlines()[0],
        'toolchain_files': review.ToolchainInputs_Get(root, graph, prefix, stack.Command_Read)}


def Inputs_Verify(root, graph, configuration, prefix):
    index = Path(__file__).with_name('ground_stack_inputs.json')
    data = review._manifest.Manifest_Load(root, index, REVIEW_SHA256)
    cases = [case for case in data['cases'] if case['configuration'] == configuration]
    actual = Inputs_Capture(root, graph, prefix)
    selected = [case for case in cases if all(case.get(key) == value for key, value in actual.items())]
    if len(selected) != 1:
        raise ValueError('Changed or ambiguous complete Ground compilation/artifact closure')
    review.ReviewDocument_Verify(root, selected[0])
    return {**selected[0], '_review_reference': {
        'case': selected[0]['name'], 'revision': data['review_revision'],
        'document': Path(selected[0]['review_document']).name,
        'document_sha256': selected[0]['review_document_sha256'],
        'case_file': data['sealed_case_files'][selected[0]['name']]}}


def BudgetFunction_Get(graph):
    memo = {}
    def Budget_Get(name, visiting=()):
        if name in visiting:
            raise ValueError('Recursive Ground stack path: ' + ' -> '.join((*visiting, name)))
        if name in graph['indirect'] or name in graph['unbounded']:
            raise ValueError('Unresolved Ground stack usage: ' + name)
        if name not in memo:
            children = [Budget_Get(child, (*visiting, name)) for child in sorted(graph['edges'].get(name, ()))]
            count, chain = max(children, default=(0, []), key=lambda value: value[0])
            memo[name] = (graph['frames'][name] + count, [name, *chain])
        return memo[name]
    return Budget_Get


def StackReport_Build(root, configuration, prefix):
    graph = GroundGraph_Load(root, configuration, prefix)
    case = Inputs_Verify(root, graph, configuration, prefix)
    architecture, adapter = RuntimeAdapter_Get(graph['ground_declarations'])
    reset = adapter.ResetStack_Resolve(graph)
    crt = adapter.CrtCallbacks_Resolve(root, graph, prefix, stack.TableBytes_Get)
    hal = runtime.runtime.HalCallbacks_Resolve(root, graph, prefix, stack.Command_Read, stack.CallbackSlot_Get,
                                              review=case['runtime_contract']['hal'])
    exceptions = case['runtime_contract']['exceptions']
    declared = graph['ground_declarations']
    if architecture == 'cortex_m3':
        raw = adapter.VectorTable_Get(root, graph, prefix, stack.TableBytes_Get, stack.Command_Read)
        required = exceptions.get('required_irq_handlers')
        if (type(required) is not list or not required or len(required) != len(set(required)) or
                any(type(name) is not str for name in required)):
            raise ValueError('Missing sealed Cortex-M3 active IRQ contract')
        declared = {**declared, 'required_irq_handlers': sorted(set(declared['required_irq_handlers']) | set(required))}
    else:
        vector = runtime.runtime.Symbols_Get(graph['nm'])['g_pfnVectors']
        raw = stack.TableBytes_Get(root, prefix, graph['elf'], vector['address'], vector['size'])
    irq_symbols = stack.Command_Read([prefix + 'nm', '-n', str(graph['elf'])], root).replace('\r\n', '\n')
    artifacts.InterruptVectors_Validate(root, declared, irq_symbols, raw)
    arguments = (root, graph, exceptions, prefix, stack.TableBytes_Get, BudgetFunction_Get(graph), stack.MIN_MARGIN_BYTES)
    whole = adapter.WholeProgram_Build(*arguments, stack.Command_Read) if architecture == 'cortex_m3' else adapter.WholeProgram_Build(*arguments)
    if graph['indirect'] or graph['unbounded']:
        raise ValueError('Unresolved linked Ground functions: ' + ', '.join(sorted(graph['indirect'] | graph['unbounded'])))
    return {'schema': 'silverstar.ground-stack-budget/1', 'configuration': configuration, 'architecture': architecture,
        'case': case['name'], 'elf': graph['elf'].relative_to(root).as_posix(),
        'elf_sha256': review.FileHash_Get(graph['elf']), 'source_count': len(graph['sources']),
        'checker_sha256': review.FileHash_Get(Path(__file__)), 'compiler': case['compiler'],
        'software_review': case['_review_reference'],
        'su_files': len(graph['su_paths']), 'minimum_margin_bytes': stack.MIN_MARGIN_BYTES,
        'analysis_tools_sha256': {name: review.FileHash_Get(Path(__file__).with_name(name)) for name in
            ('check_ground_stacks.py', 'ground_stack_runtime.py', 'ground_stack_runtime_m3.py', 'check_task_stacks.py', 'stack_arm.py',
             'stack_runtime.py', 'stack_review.py', 'stack_manifest.py', 'ground_stack_inputs.json',
             'check_ground.py', 'ground_artifact_contract.py', case['_review_reference']['document'])},
        'runtime_proofs': {'reset': reset, 'crt': crt, 'hal': hal}, 'whole_program': whole,
        'checks': {'complete_source_and_objects': True, 'all_linked_calls_resolved': True,
                   'all_vectors_budgeted': True},
        'passes': whole['passes'], 'hardware_tested': False,
        'limitation': 'Sealed software stack only; timing, dynamic measurements and hardware qualification not proven.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', choices=('Release', 'Debug'), default='Release')
    parser.add_argument('--prefix', default='arm-none-eabi-')
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    result = StackReport_Build(root, arguments.config, arguments.prefix)
    output = root / Path(result['elf']).parent / 'ground-stack-budget.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print('FIRMWARE_STACK_REPORT|' + str(output))
    print(json.dumps({'passes': result['passes'], 'report': str(output),
                      'msp_margin_bytes': result['whole_program']['margin_bytes']}))
    return 0 if result['passes'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
