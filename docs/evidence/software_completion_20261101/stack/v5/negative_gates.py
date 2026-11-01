"""Strict rejection on the independently built PID copy; restore every byte."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PROJECT = ROOT / '.work/0.1.3-software-completion-20261101/stack/v5/b/pid/Flight_Controller'
BUILD = PROJECT / 'build/FCCG/SilverStar_F407/Release'
OUT = HERE / 'negatives-b'
COMMAND = [sys.executable, str(PROJECT / 'Tools/check_task_stacks.py'), '--project', str(PROJECT),
           '--config', 'Release', '--prefix', 'D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-']


def Hash_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def Run(name):
    log = OUT / (name + '.log')
    started = time.monotonic()
    with log.open('w', encoding='utf8') as stream:
        result = subprocess.run(COMMAND, cwd=PROJECT, stdout=stream, stderr=subprocess.STDOUT)
    return {'name': name, 'command': COMMAND, 'exit_code': result.returncode,
            'seconds': round(time.monotonic() - started, 3), 'log': log.name,
            'log_sha256': Hash_Get(log.read_bytes())}


def ReducedFrame_Get(raw):
    changed, count = re.subn(rb'\t[1-9][0-9]*\t', b'\t0\t', raw, count=1)
    assert count == 1 and changed != raw
    return changed


def ControlMetadata_Change(raw):
    value = json.loads(raw)
    # The contract's exact JSON bytes are sealed separately from source inputs.
    value['negative_test_mutation'] = 'unreviewed control metadata'
    return (json.dumps(value, indent=2) + '\n').encode()


if __name__ == '__main__':
    accepted = json.loads((HERE / 'gates-b/commands.json').read_text(encoding='utf8'))
    pid_accepted = [row for row in accepted if row['name'] == 'pid']
    assert len(pid_accepted) == 5 and all(row['exit_code'] == 0 for row in pid_accepted)
    OUT.mkdir(exist_ok=False)
    cases = [
        ('header-change', PROJECT / 'APP/Inc/control_research.h', lambda raw: raw + b'\n/* unreviewed header */\n'),
        ('lower-stack-frame', BUILD / 'APP/Src/flight_task.su', ReducedFrame_Get),
        ('object-byte-change', BUILD / 'APP/Src/flight_task.o', lambda raw: raw[:-1] + bytes([raw[-1] ^ 1])),
        ('missing-manifest', PROJECT / 'Tools/software_stack_inputs.json', lambda raw: None),
        ('changed-manifest', PROJECT / 'Tools/software_stack_inputs.json', lambda raw: raw + b'\n'),
        ('changed-review-document', PROJECT / 'Tools/software_stack_review.md', lambda raw: raw + b'\nUnreviewed edit.\n'),
        ('control-metadata-change', PROJECT / 'Generated/control_research.json', ControlMetadata_Change),
    ]
    rows = [Run('baseline')]
    assert rows[0]['exit_code'] == 0
    for name, path, change in cases:
        assert path.resolve().is_relative_to(PROJECT.resolve()) and not path.is_symlink()
        original = path.read_bytes()
        stat = path.stat()
        try:
            changed = change(original)
            if changed is None:
                path.unlink()
            else:
                path.write_bytes(changed)
            row = Run(name)
            row.update({'path': path.relative_to(PROJECT).as_posix(), 'original_sha256': Hash_Get(original),
                        'changed_sha256': None if changed is None else Hash_Get(changed)})
        finally:
            path.write_bytes(original)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        row['restored_sha256'] = Hash_Get(path.read_bytes())
        row['restored'] = row['restored_sha256'] == row['original_sha256']
        rows.append(row)
        (OUT / 'commands.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
        print(name, row['exit_code'], 'restored', row['restored'], flush=True)
        assert row['exit_code'] != 0 and row['restored']
    rows.append(Run('restored-positive'))
    (OUT / 'commands.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    assert rows[-1]['exit_code'] == 0
