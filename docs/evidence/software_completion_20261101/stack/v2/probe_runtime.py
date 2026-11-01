"""Read actual candidate stack graphs; diagnostic only, never enroll inputs."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[5]
TOOLS = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools'
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v2/analysis'
OUT = Path(__file__).resolve().parent / 'runtime-v1'
PREFIX = 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-'

def Module_Load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def Probe_Run(case):
    name, config = case
    checker, runtime = Module_Load('check_task_stacks'), Module_Load('stack_runtime')
    root = WORK / name / 'Flight_Controller'
    report = {'not_acceptance': True, 'name': name, 'configuration': config}
    try:
        graph = None
        try:
            checker.StackReport_Build(root, config, PREFIX)
        except Exception as error:
            report['strict_rejection'] = str(error)
            trace = error.__traceback__
            while trace:
                if trace.tb_frame.f_code.co_name == 'StackReport_Build':
                    graph = trace.tb_frame.f_locals.get('graph')
                trace = trace.tb_next
        if graph is None:
            raise ValueError('No strictly rejected analysis graph')
        report['proofs'] = {
            'hal_diagnostic': runtime.HalCallbacks_Resolve(root, graph, PREFIX, checker.Command_Read,
                                                          checker.CallbackSlot_Get, diagnostic=True),
            'port': runtime.PortStackPointers_Resolve(root, graph),
            'crt': runtime.CrtCallbacks_Resolve(root, graph, PREFIX, checker.TableBytes_Get),
        }
        report['unresolved_indirect'] = sorted(graph['indirect'])
        report['unresolved_sp'] = sorted(graph['unbounded'])
        memo = {}
        def Budget_Get(name, visiting=()):
            if name in visiting or name in graph['indirect'] or name in graph['unbounded']:
                raise ValueError('Unproved path: ' + repr(visiting + (name,)))
            if name not in memo:
                children = [Budget_Get(child, visiting + (name,)) for child in sorted(graph['edges'].get(name, ()))]
                count, chain = max(children, default=(0, []), key=lambda item: item[0])
                memo[name] = (graph['frames'][name] + count, [name] + chain)
            return memo[name]
        entries = {key: value[0] for key, value in checker.TASKS.items()}
        entries['Reset'] = 'Reset_Handler'
        entries.update({key: key for key in graph['instructions'] if key.endswith(('_IRQHandler', '_Handler'))})
        report['budgets'] = {}
        for label, entry in entries.items():
            try:
                report['budgets'][label] = Budget_Get(entry)
            except ValueError as error:
                report['budgets'][label] = {'error': str(error)}
        report['task_direct_edges'] = {value[0]: sorted(graph['edges'][value[0]]) for value in checker.TASKS.values()}
    except Exception:
        report['error'] = traceback.format_exc()
    (OUT / (name + '-' + config + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(name, config, report.get('error', report.get('budgets')), flush=True)

if __name__ == '__main__':
    OUT.mkdir(exist_ok=False)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(Probe_Run, [(name, config) for name in ('f407', 'installation', 'h743')
                                    for config in ('Release', 'Debug')]))
