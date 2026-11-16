"""Fault-inject an owned generated test project, restoring exact bytes each time.

Run only when no build/GUI operation uses that project. No physical device is
accessed. The baseline must pass the actual emitted strict checker first.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def Hash_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Main_Run():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--case', choices=('ssgs1-Release', 'f103-e19-Release'), default='ssgs1-Release')
    args = parser.parse_args()
    root = args.project.resolve(strict=True)
    if args.output.exists():
        raise ValueError('Keep prior fault-injection evidence unchanged')
    args.output.mkdir(parents=True)
    command = [sys.executable, str(root / 'Tools/check_ground_stacks.py'),
               '--config', 'Release', '--prefix', args.prefix]
    rows = []

    def Check_Run(name, expect):
        result = subprocess.run(command, cwd=root, capture_output=True)
        log = args.output / (name + '.log')
        log.write_bytes(result.stdout + result.stderr)
        rows.append({'name': name, 'command': command, 'exit_code': result.returncode,
                     'expected': expect, 'log': str(log), 'sha256': Hash_Get(log)})
        (args.output / 'receipt.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
        if (expect == 'pass') != (result.returncode == 0):
            raise AssertionError('Unexpected strict gate outcome: ' + name)

    Check_Run('baseline', 'pass')
    graph = json.loads((root / 'Generated/ground_source_graph.json').read_bytes())
    source = next(name for name in graph['sources'] if name.startswith('Ground/Core/'))
    source_path = Path(source)
    mutations = [
        ('source', source, lambda raw: raw + b'\n/* fault-injection changed source */\n'),
        ('source-omitted', 'Generated/ground_source_graph.json',
         lambda raw: json.dumps({**json.loads(raw), 'sources': [s for s in graph['sources'] if s != source]}).encode()),
        ('missing-su', 'build/' + source_path.with_suffix('.su').as_posix(), lambda _raw: None),
        ('object', 'build/' + source_path.with_suffix('.o').as_posix(), lambda raw: raw + b'changed'),
        ('extra-object', 'build/unselected.o', lambda _raw: b'not selected by source graph'),
        ('case', 'Tools/software_stack_cases/' + args.case + '.json', lambda raw: raw + b' '),
    ]
    for name, relative, transform in mutations:
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError('Fault target must remain in the owned test project')
        existed = path.exists()
        original = path.read_bytes() if existed else b''
        stat = path.stat() if existed else None
        changed = transform(original)
        try:
            if changed is None:
                path.unlink()
            else:
                path.write_bytes(changed)
            Check_Run(name, 'reject')
        finally:
            if existed:
                path.write_bytes(original)
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                if path.read_bytes() != original:
                    raise AssertionError('Exact test input restoration failed')
            elif path.exists():
                path.unlink()
    Check_Run('restored', 'pass')
    print(json.dumps({'checks': len(rows), 'hardware_tested': False, 'restored': True}))


if __name__ == '__main__':
    Main_Run()
