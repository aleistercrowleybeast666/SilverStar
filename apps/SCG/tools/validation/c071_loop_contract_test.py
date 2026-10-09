"""Test only the exact approved C071 loop exception, using isolated small inputs."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess

def C071LoopContract_Test(usb, uart, output):
    roots = {'usb_cdc': usb.resolve(), 'uart': uart.resolve()}
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('new empty output required')
    if any(root == output or root.is_relative_to(output) or output.is_relative_to(root) for root in roots.values()):
        raise ValueError('disjoint test output required')
    results = []
    for name, mode, change in [('usb', 'usb_cdc', None), ('uart', 'uart', None),
        ('changed-main', 'usb_cdc', 'main'), ('other-loop', 'uart', 'loop'),
        ('other-part', 'uart', 'part'), ('wrong-transport', 'usb_cdc', 'transport'),
        ('wrong-cpu', 'usb_cdc', 'cpu'), ('wrong-define', 'uart', 'define'),
        ('normal-import', 'uart', 'import')]:
        source = roots[mode]; target = output/name
        for directory in ('Common', 'Devices', 'Generated', 'Ground', 'Platform'):
            for path in (source/directory).rglob('*'):
                if path.is_file() and path.suffix in ('.c', '.h', '.json'):
                    dest = target/path.relative_to(source)
                    dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, dest)
        graph_path = target/'Generated/ground_source_graph.json'
        graph = json.loads(graph_path.read_text(encoding='utf-8'))
        linker = graph['linker_script']
        (target/linker).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/linker, target/linker)
        shutil.copyfile(source/'Makefile', target/'Makefile')
        (target/'Tools').mkdir()
        checker = target/'Tools/check_power_of_ten.ps1'
        shutil.copyfile(source/'Tools/check_power_of_ten.ps1', checker)
        if change == 'main':
            path = target/'Platform/STM32C0/Src/main.c'
            path.write_bytes(path.read_bytes()+b'\n/* changed identity */\n')
        if change == 'loop':
            (target/'Platform/other.c').write_text('void Other_Run(void) { while (1) { } }\n')
        if change == 'part': graph['experimental_standalone_mcu'] = 'STM32F103C8'
        if change == 'transport': graph['pc_interface'] = 'uart'
        if change == 'cpu': graph['mcu_flags'] = ['-mcpu=cortex-m3', '-mthumb']
        if change == 'define': graph['defines'].remove('STM32C071xx')
        if change == 'import': graph['complete_cube_import'] = True
        graph_path.write_text(json.dumps(graph), encoding='utf-8')
        command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(checker), '-TargetKind', 'Ground']
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
        expected = 0 if change is None else 1
        log = output/(name+'.log'); log.write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        if result.returncode != expected or 'POWER10_CONTRACT_REVIEW|NOT_PROVEN' not in result.stdout:
            raise ValueError('unexpected loop gate result: '+name)
        if expected and 'finite while/do loop violation' not in result.stdout:
            raise ValueError('negative did not reach finite-loop gate: '+name)
        results.append({'case': name, 'command': command, 'expected_exit': expected,
            'actual_exit': result.returncode, 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        print('PASS exact loop contract', name, 'exit', result.returncode, flush=True)
    (output/'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usb', type=Path, required=True)
    parser.add_argument('--uart', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    C071LoopContract_Test(args.usb, args.uart, args.output)
