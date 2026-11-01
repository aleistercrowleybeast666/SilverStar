"""Independent actual-ELF control reachability supplement to the A review."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
WORK = ROOT / '.work/0.1.3-software-completion-20261101/stack/v5/a'
TOOLS = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools'
PREFIX = 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-'

def Load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def Run(case):
    name, config = case
    checker, runtime = Load('check_task_stacks'), Load('stack_runtime')
    project = WORK / name / 'Flight_Controller'
    raw = (project / 'Generated/control_research.json').read_bytes()
    data = json.loads(raw)
    contract = {'sha256': hashlib.sha256(raw).hexdigest(), 'enabled': data['enabled'], 'kind': data['kind']}
    if data['enabled']:
        graph = checker.StackGraph_Load(project, config, PREFIX)
    else:
        target = json.loads((project / 'SilverStar.ssproject').read_text())['build']['target_profile']
        elf = next((project / 'build/FCCG' / target / config).glob('*.elf'))
        nm = checker.Command_Read([PREFIX + 'nm', '-S', '--defined-only', str(elf)], project)
        graph = {'elf': elf, 'instructions': set(runtime.Symbols_Get(nm)), 'edges': {}}
    def Closure(entry):
        visited, pending = set(), [entry]
        while pending:
            node = pending.pop()
            if node not in visited:
                visited.add(node)
                pending.extend(graph['edges'].get(node, ()))
        return visited
    proof = runtime.ControlTask_Verify(project, graph, contract, Closure)
    expected = json.loads((EVIDENCE / 'inspection-a' / (name + '-' + config + '.json')).read_text())
    elf_sha = hashlib.sha256(graph['elf'].read_bytes()).hexdigest()
    assert elf_sha == expected['case_candidate']['compiled_artifacts'][graph['elf'].name]
    return {'name': name, 'configuration': config, 'contract': contract, 'proof': proof, 'elf_sha256': elf_sha,
            'flight_control_functions': sorted(node for node in Closure('AppTask_Flight') if node.startswith(('ControlResearch', 'ControlPid', 'ControlLqr')))}

output = EVIDENCE / 'control-reachability.json'
assert not output.exists()
results = []
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(Run, (name, config)) for name in ('f407', 'installation', 'h743', 'pid', 'lqr')
               for config in ('Release', 'Debug')]
    for future in as_completed(futures):
        row = future.result()
        results.append(row)
        output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf8')
        print(row['name'], row['configuration'], row['proof'], flush=True)
assert len(results) == 10
