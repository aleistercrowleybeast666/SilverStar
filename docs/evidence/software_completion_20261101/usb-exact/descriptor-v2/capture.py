"""Archive the three real private builds and exact pre/post Host fault inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent


def Hash_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def Archive_Write(project, names, output):
    assert not output.exists(), str(output)
    hashes = {}
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            raw = (project / name).read_bytes()
            archive.writestr(name, raw)
            hashes[name] = Hash_Get(raw)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert {name: Hash_Get(archive.read(name)) for name in archive.namelist()} == hashes
    return {'file': output.name, 'sha256': Hash_Get(output.read_bytes()), 'members': hashes}


if __name__ == '__main__':
    builds = json.loads((HERE / 'build-results.json').read_text(encoding='utf8'))
    gates = json.loads((HERE / 'gate-commands.json').read_text(encoding='utf8'))
    comparisons = json.loads((HERE / 'compiled-closure-comparison-v2.json').read_text(encoding='utf8'))
    assert len(builds) == 3 and all(row['result'] == 'CompiledCandidate' for row in builds)
    assert len(gates) == 12 and all(row['exit_code'] == 0 for row in gates)
    rows = []
    for build in builds:
        part = build['part']; project = Path(build['output'])
        receipt = json.loads((project / 'receipt.json').read_text(encoding='utf8'))
        assert receipt['status'] == 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
        assert not receipt['warning_diagnostics'] and all(row['exit'] == 0 for row in receipt['commands'])
        analyzer_commands = [row['command'] for row in receipt['commands']
                             if '-fanalyzer' in row['command'] and '-S' in row['command']]
        analyzed = [command[command.index('-S') + 1] for command in analyzer_commands]
        assert set(analyzed) == set(receipt['graph']['sources'])
        for command in analyzer_commands:
            assembly = command[command.index('-o') + 1]
            assert (project / assembly).is_file() and (project / assembly).with_suffix('.o').is_file()
        assert (project / 'build/native.elf').is_file() and (project / 'build/analysis/native.elf').is_file()
        names = ['receipt.json', 'backend-receipt.json', 'source-snapshot.json', 'commands.log',
                 'candidate_config.ssproject', 'Makefile', 'Generated/ground_source_graph.json',
                 'Tools/check_power_of_ten.ps1']
        names += [path.relative_to(project).as_posix() for path in (project / 'build').rglob('*') if path.is_file()
                  and (path.suffix in ('.elf', '.map') or path.name in ('memory-report.json', 'native-artifact-report.json'))]
        names += ['Generated/Inc/pc_usb_control.h', 'Generated/Src/pc_usb_control.c',
                  'HardwareGenerated/ReviewedNativeControl/Core/Src/usbd_core.c',
                  'HardwareGenerated/ReviewedNativeControl/Class/CDC/Src/usbd_cdc.c']
        names = [name for name in names if (project / name).is_file()]
        archive = Archive_Write(project, names, HERE / (part + '-artifacts.zip'))
        backend = json.loads((project / 'backend-receipt.json').read_text(encoding='utf8'))
        rows.append({'part': part, 'project': str(project), 'status': receipt['status'],
                     'backend_status': backend['status'], 'limits': backend['limits'],
                     'compiler_commands': len(receipt['commands']), 'all_compiler_command_exits_zero': True,
                     'warning_diagnostics': receipt['warning_diagnostics'], 'analyzed_c_sources': analyzed,
                     'analyzer_method': 'Real ARM GCC -fanalyzer -S, then GAS assembly and ELF linking; not syntax-only.',
                     'archive': archive,
                     'emitted_gate_exits': {gate['gate']: gate['exit_code'] for gate in gates if gate['part'] == part},
                     'compiled_closure_comparison': next(row for row in comparisons if row['part'] == part)})
    faults = []
    for epoch, directory in (('pre-fixture-fix', 'fd2'), ('post-fixture-fix', 'fd3')):
        for ordinal, part in enumerate(('F103', 'F407')):
            project = ROOT / '.work/sc-261101-usb' / directory / ('test_exact_generated_control_f' + str(ordinal))
            names = [path.name for path in project.iterdir() if path.is_file()
                     and path.suffix in ('.c', '.h', '.json', '.log', '.ssproject')]
            archive = Archive_Write(project, names, HERE / (epoch + '-' + part + '-host.zip'))
            receipt = json.loads((project / 'fault-receipt.json').read_text(encoding='utf8'))
            normal = json.loads((project / 'lifecycle-receipt.json').read_text(encoding='utf8'))
            failures = [row for row in receipt['runs'] if row['exit'] != 0]
            if epoch == 'post-fixture-fix':
                assert not failures
            faults.append({'epoch': epoch, 'part': part, 'fault_count': len(receipt['runs']),
                           'fault_failures': failures, 'normal_count': len(normal['runs']),
                           'normal_exits': [row['exit'] for row in normal['runs']], 'archive': archive})
    snapshot = json.loads((HERE / 'generation-source-snapshot.json').read_text(encoding='utf8'))
    changes = []
    for name, expected in snapshot['after'].items():
        path = ROOT / name
        if not path.is_file() or Hash_Get(path.read_bytes()) != expected:
            changes.append(name)
    report = {'schema': 'silverstar.private-usb-descriptor-validation/1',
              'generation_head': snapshot['head'], 'generation_source_changes': snapshot['changed'],
              'subsequent_source_changes': changes,
              'current_source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'scope': 'Exact private native F103/F407/C071 candidates. Formal USB release and hardware qualification remain blocked.',
              'builds': rows, 'faults': faults,
              'comparison_note': 'Initial Export comparison lacks compiler-added ABI probe; all three were actually rebuilt. Initial compiled comparison wrongly counted build-output deps/Host stub headers; v2 compares only target inputs and asserts no include path points into build.'}
    (HERE / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'builds': [(row['part'], row['compiler_commands'], len(row['analyzed_c_sources']), row['emitted_gate_exits']) for row in rows],
                      'faults': [(row['epoch'], row['part'], row['normal_count'], row['fault_count'], len(row['fault_failures'])) for row in faults],
                      'subsequent_source_changes': changes}, indent=2))
