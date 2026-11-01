"""Isolate the original INS queue-admission owner against an unchanged real-bus test.

No production or existing generated file is overwritten. Old/new INS owners use
the same generated v6 headers, START, queue, estimator and test expectations.
This is component fault reproduction, not a build of the whole historical tree.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent / 'queue-boundary-v2'
WORK = ROOT / '.work/0.1.3-software-completion-20261101/control/queue-boundary-v2'
PROJECT = ROOT / '.work/0.1.3-software-completion-20261101/control/pytest-v6/control-research-pid0/Flight_Controller'
BASE = '8b028f280ba01dce0efc697479ef99ec143f7456'
OWNER = 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/ins_task.c'
GCC = Path('D:/msys64/ucrt64/bin/gcc.exe')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def execute(command, log):
    result = subprocess.run(command, capture_output=True, timeout=300, env=ENV)
    log.write_bytes(result.stdout + result.stderr)
    log.with_suffix('.command.json').write_text(json.dumps(command, indent=2), encoding='utf8')
    log.with_suffix('.exit.txt').write_text(str(result.returncode) + '\n', encoding='ascii')
    return result.returncode


if EVIDENCE.exists() or WORK.exists():
    raise RuntimeError('Unique immutable evidence/output directory required')
EVIDENCE.mkdir(); WORK.mkdir()
ENV = os.environ.copy()
ENV['PATH'] = str(GCC.parent) + os.pathsep + ENV['PATH']
original = subprocess.check_output(['git', 'show', BASE + ':' + OWNER], cwd=ROOT)
current = (PROJECT / 'APP/Src/ins_task.c').read_bytes()
receipt = (Path(__file__).parent / 'producer-v1.log').read_text(encoding='utf-8-sig')
args = receipt.split('Host compiler arguments:\n', 1)[1].split('GCC stdout/stderr:', 1)[0]
args = [line.strip() for line in args.splitlines() if line.strip()]
args = [arg.replace('pytest-v4', 'pytest-v6') for arg in args if arg != '-fanalyzer']
args = [str(PROJECT/'Tests/Host/control_provenance_bus.c') if arg.endswith('APP\\Src\\estimator_bus.c') else arg for arg in args]
assert str(PROJECT/'Tests/Host/control_provenance_bus.c') in args
args += ['-flto-partition=one']
# The historical owner has a separately retained analyzer diagnostic. Both
# isolated runtime runs use identical strict compilation without the analyzer;
# the current full production-chain analyzer is a separate emitted Host run.
metadata = {'baseline_commit': BASE, 'owner': OWNER,
    'scope': 'isolated INS owner; all other actual generated v6 components identical',
    'pre_sha256': digest(original), 'post_sha256': digest(current),
    'compiler': subprocess.check_output([str(GCC), '--version'], env=ENV).decode(),
    'outcomes': {}, 'inputs': {}}
for argument in args:
    path = Path(argument)
    if path.is_file() and path.suffix in ('.c', '.h'):
        metadata['inputs'][str(path)] = digest(path.read_bytes())
for phase, source in (('pre', original), ('post', current)):
    owner = WORK / (phase + '-ins_task.c'); owner.write_bytes(source)
    harness = WORK / (phase + '-inputs.c')
    template = (PROJECT / 'Tests/Host/control_provenance_ins_inputs.c').read_text()
    harness.write_text(template.replace('../../APP/Src/ins_task.c', owner.as_posix()), encoding='utf8')
    command = [str(GCC)] + [str(harness) if value.endswith('control_provenance_ins_inputs.c') else value for value in args]
    executable = WORK / (phase + '.exe')
    command[command.index('-o') + 1] = str(executable)
    code = execute(command, EVIDENCE / (phase + '-compile.log'))
    if code != 0:
        raise RuntimeError(f'{phase} compile failed: {code}')
    metadata['outcomes'][phase] = {}
    for scenario in ('queue_full_boundary', 'queue_not_ready'):
        code = execute([str(executable), scenario], EVIDENCE / f'{phase}-{scenario}.log')
        metadata['outcomes'][phase][scenario] = code
    metadata[phase + '_binary_sha256'] = digest(executable.read_bytes())
(EVIDENCE / 'receipt.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
assert all(code != 0 for code in metadata['outcomes']['pre'].values()), metadata['outcomes']
assert all(code == 0 for code in metadata['outcomes']['post'].values()), metadata['outcomes']
print(json.dumps(metadata['outcomes'], indent=2))

