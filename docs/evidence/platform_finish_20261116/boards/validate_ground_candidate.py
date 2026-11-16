"""Run actual emitted Ground gates and retain every exit/log/source identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def Main_Run():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    target = args.project.resolve(strict=True)
    if args.output.exists():
        raise ValueError('Do not overwrite prior gate evidence')
    args.output.mkdir(parents=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    env['PATH'] = 'D:/Arm GNU Toolchain/14.3 rel1/bin;D:/msys64/ucrt64/bin;' + str(Path(sys.executable).parent) + ';' + env['PATH']
    snapshot = {path.relative_to(target).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in target.rglob('*') if path.is_file() and
                path.relative_to(target).parts[0] not in ('build', '.eide', '.vscode')}
    receipt = {'target': str(target), 'hardware_tested': False, 'source_inputs': snapshot, 'commands': []}
    for config in ('Release', 'Debug'):
        for gate in ('all', 'artifact-check', 'architecture-check', 'power10-check',
                     'static-analysis', 'host-tests', 'stack-report'):
            command = ['D:/msys64/ucrt64/bin/mingw32-make.exe', '-C', str(target), '-j2', 'CONFIG=' + config, gate]
            log = args.output / (config + '-' + gate + '.log')
            start = time.monotonic()
            with log.open('w', encoding='utf8') as stream:
                stream.write('COMMAND ' + json.dumps(command) + '\n')
                stream.flush()
                result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
            receipt['commands'].append({'argv': command, 'config': config, 'gate': gate,
                'exit_code': result.returncode, 'seconds': time.monotonic() - start,
                'log': str(log), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
            (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
            print(config, gate, result.returncode, flush=True)
    receipt['inputs_unchanged'] = all((target / name).is_file() and
        hashlib.sha256((target / name).read_bytes()).hexdigest() == digest for name, digest in snapshot.items())
    receipt['artifacts'] = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (target / 'build').rglob('*') if p.is_file() and p.suffix in ('.elf', '.bin', '.map', '.json')}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    return 0 if receipt['inputs_unchanged'] and all(row['exit_code'] == 0 for row in receipt['commands']) else 1


if __name__ == '__main__':
    raise SystemExit(Main_Run())
