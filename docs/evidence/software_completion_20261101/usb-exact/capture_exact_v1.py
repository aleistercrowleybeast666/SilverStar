"""Preserve actual EP0 regression bytes and compile first-party/derived owners with analyzer."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/sc-261101-usb'


def preserve(source, destination):
    data = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert destination.read_bytes() == data, str(destination)
    else:
        destination.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def run():
    assert not (HERE / 'receipt-v1.json').exists(), 'Preserve the existing evidence epoch'
    records = []
    for epoch in ('pre-v4', 'post-v2'):
        for ordinal, part in enumerate(('F103', 'F407')):
            project = WORK / epoch / f'test_exact_generated_control_f{ordinal}'
            target = HERE / epoch / part
            names = ('fault-receipt.json', 'lifecycle-receipt.json', 'fault-compile.log', 'compile.log',
                     'fault.c', 'pc_usb_control.c', 'pc_usb_control.h', 'usbd_core.c', 'usbd_ioreq.c')
            files = {name: preserve(project / name, target / name) for name in names}
            receipt = json.loads((project / 'fault-receipt.json').read_text(encoding='utf8'))
            assert len(receipt['runs']) == 10
            assert all(row['exit'] != 0 for row in receipt['runs']) if epoch == 'pre-v4' else all(row['exit'] == 0 for row in receipt['runs'])
            record = {'epoch': epoch, 'part': part, 'preserved_sha256': files}
            if epoch == 'post-v2':
                record['analyzer'] = []
                # The shared legacy normal harness redundantly defines BOS=0
                # even when the actual F407 header owns 0U. Remove only that
                # duplicate command argument; the actual header remains intact.
                conf = (project / 'usbd_conf.h').read_text(encoding='utf8')
                for source in ('pc_usb_control.c', 'usbd_core.c', 'usbd_ioreq.c'):
                    command = [receipt['compile_command'][0], '-std=c11', '-O2', '-Wall', '-Wextra',
                               '-Werror', '-pedantic', '-fanalyzer', '-DUSBD_MAX_SUPPORTED_CLASS=1',
                               '-I' + str(project), '-c', str(project / source), '-o', str(project / (source + '.o'))]
                    if '#define USBD_CLASS_BOS_ENABLED' not in conf:
                        command.insert(1, '-DUSBD_CLASS_BOS_ENABLED=0')
                    if part == 'F103':
                        command.insert(1, '-DHOST_F103=1')
                    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
                    (target / (source + '.analyzer.log')).write_text(result.stdout + result.stderr, encoding='utf8')
                    record['analyzer'].append({'command': command, 'exit': result.returncode,
                        'object_sha256': hashlib.sha256((project / (source + '.o')).read_bytes()).hexdigest() if result.returncode == 0 else None})
            records.append(record)
    owner = ROOT / 'apps/SCG/src/silverstar_fccg/generator/ground_usb_control.py'
    preserve(owner, HERE / 'final-ground_usb_control.py')
    preserve(ROOT / 'apps/SCG/tests/test_native_control_faults.py', HERE / 'final-test_native_control_faults.py')
    report = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_identity': 'auditable dirty owner bytes, not a clean commit assertion',
        'generator_sha256': hashlib.sha256(owner.read_bytes()).hexdigest(),
        'scratch': '.work/sc-261101-usb (short task alias; normal Windows path-length guard retained)',
        'task': '.work/0.1.3-software-completion-20261101/usb-exact', 'records': records}
    (HERE / 'receipt-v1.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps([(r['epoch'], r['part'], [a['exit'] for a in r.get('analyzer', [])]) for r in records]))
    return int(any(a['exit'] for r in records for a in r.get('analyzer', [])))


if __name__ == '__main__':
    raise SystemExit(run())
