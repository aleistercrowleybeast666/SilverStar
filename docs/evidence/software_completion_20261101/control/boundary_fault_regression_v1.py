"""Unchanged Host expectations against isolated pre/post controller and INS owners."""
from pathlib import Path
import hashlib, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / '.work/0.1.3-software-completion-20261101/control/boundary-fault-v1'
EVIDENCE = HERE / 'boundary-fault-v1'
PROJECT = ROOT / '.work/0.1.3-software-completion-20261101/control/pytest-v5/control-research-pid0/Flight_Controller'
PAYLOAD = ROOT / 'apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload'
GCC = 'D:/msys64/ucrt64/bin/gcc.exe'
phase = sys.argv[1]
assert phase in ('pre', 'post')
WORK.mkdir(exist_ok=True); EVIDENCE.mkdir(exist_ok=True)
if (EVIDENCE / f'{phase}-receipt.json').exists():
    raise RuntimeError('Evidence phase already exists')
env = os.environ.copy(); env['PATH'] = str(Path(GCC).parent) + os.pathsep + env['PATH']
sha = lambda data: hashlib.sha256(data).hexdigest()
receipt = {'phase': phase, 'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
    'scope': 'same frozen v5 support, same tests; only isolated control/INS owner replaced', 'sources': {}, 'outcomes': {}}

def execute(command, name):
    result = subprocess.run(command, capture_output=True, env=env, timeout=300)
    (EVIDENCE/f'{phase}-{name}.log').write_bytes(result.stdout + result.stderr)
    (EVIDENCE/f'{phase}-{name}.command.json').write_text(json.dumps(command, indent=2), encoding='utf8')
    (EVIDENCE/f'{phase}-{name}.exit.txt').write_text(str(result.returncode)+'\n', encoding='ascii')
    return result.returncode

for name in ('control_research', 'ins_task'):
    data = (PAYLOAD / f'APP/Src/{name}.c').read_bytes()
    (WORK/f'{phase}-{name}.c').write_bytes(data)
    receipt['sources'][name] = sha(data)
if phase == 'pre':
    for name in ('test_control_research.c', 'test_control_provenance.c', 'control_provenance_ins_inputs.c', 'control_provenance_bus.c'):
        data = (PAYLOAD/'Tests/Host'/name).read_text()
        data = data.replace('../../Common/Src/silverstar_assert.c', (PROJECT/'Common/Src/silverstar_assert.c').as_posix())
        data = data.replace('"test_optional_gnss_start.c"', '"'+(PROJECT/'Tests/Host/test_optional_gnss_start.c').as_posix()+'"')
        data = data.replace('../../APP/Src/estimator_bus.c', (PROJECT/'APP/Src/estimator_bus.c').as_posix())
        (WORK/name).write_text(data, encoding='utf8')
for name, owner in (('test_control_research.c', 'control_research'), ('control_provenance_ins_inputs.c', 'ins_task')):
    data = (WORK/name).read_text().replace(f'../../APP/Src/{owner}.c', (WORK/f'{phase}-{owner}.c').as_posix())
    (WORK/f'{phase}-{name}').write_text(data, encoding='utf8')
control = json.loads((PROJECT/'control-compile.command.json').read_text())
control = [str(WORK/f'{phase}-test_control_research.c') if value.endswith('Tests/Host/test_control_research.c') else value for value in control]
control[control.index('-o')+1] = str(WORK/f'{phase}-control.exe')
assert execute(control, 'control-compile') == 0
for scenario in ('stop_interleave', 'schedule_interleave'):
    receipt['outcomes'][scenario] = execute([control[-1], scenario], scenario)
text = (HERE/'producer-v1.log').read_text(encoding='utf-8-sig')
args = text.split('Host compiler arguments:\n',1)[1].split('GCC stdout/stderr:',1)[0]
args = [line.strip().replace('pytest-v4','pytest-v5') for line in args.splitlines() if line.strip() and line.strip() != '-fanalyzer']
mapping = {'control_provenance_ins_inputs.c': str(WORK/f'{phase}-control_provenance_ins_inputs.c'),
    'test_control_provenance.c': str(WORK/'test_control_provenance.c'),
    'estimator_bus.c': str(WORK/'control_provenance_bus.c')}
args = [mapping.get(Path(value).name, value) for value in args]
args[args.index('-o')+1] = str(WORK/f'{phase}-alignment.exe')
args += ['-flto-partition=one']
assert execute([GCC]+args, 'alignment-compile') == 0
receipt['outcomes']['alignment_source'] = execute([str(WORK/f'{phase}-alignment.exe'),'alignment_source'], 'alignment_source')
for path in WORK.glob('*.c'):
    receipt['sources'][path.name] = sha(path.read_bytes())
(EVIDENCE/f'{phase}-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps(receipt['outcomes']))
assert all((code != 0) if phase == 'pre' else (code == 0) for code in receipt['outcomes'].values())
