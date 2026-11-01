"""Capture the actual controller-v7 inputs, compiler command and torque output."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
EPOCH = 'v7b'  # v7 retained: Windows default-codepage failure in two Python assertions.
WORK = ROOT / f'.work/0.1.3-software-completion-20261101/control/pytest-{EPOCH}'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    assert not (EVIDENCE / f'task-{EPOCH}-receipt.json').exists(), 'Preserve the existing evidence epoch'
    assert (EVIDENCE / f'task-{EPOCH}.exit.txt').read_text(encoding='utf8').strip() == '0'
    sources = {name: digest(ROOT / name) for name in
               (EVIDENCE / 'OWNED_FILES.txt').read_text(encoding='utf8').splitlines()}
    runs = []
    for kind in ('pid', 'lqr'):
        project = WORK / f'control-research-{kind}0/Flight_Controller'
        command = [str(project / 'control-research.exe'), 'torque_units']
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        compile_command = json.loads((project / 'control-compile.command.json').read_text(encoding='utf8'))
        compiled = {str(Path(item).relative_to(project)).replace('\\', '/'):
                    digest(Path(item)) for item in compile_command if item.endswith('.c')}
        # The Host driver includes these actual owners into its translation unit.
        for name in ('APP/Src/control_research.c', 'APP/Inc/control_research.h',
                     'Common/Src/silverstar_assert.c'):
            compiled[name] = digest(project / name)
        runs.append({'kind': kind, 'command': command, 'exit': result.returncode,
                     'stdout': result.stdout, 'stderr': result.stderr,
                     'compile_command': compile_command,
                     'compiled_sources_sha256': compiled,
                     'executable_sha256': digest(project / 'control-research.exe'),
                     'runtime_contract': json.loads((project / 'Generated/control_research.json').read_text(encoding='utf8')),
                     'compile_log_sha256': digest(project / 'control-compile.log')})
    receipt = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'identity': 'auditable dirty source snapshot; not a clean commit assertion',
               'owned_sources_sha256': sources,
               'pytest_command': f'python -m pytest apps/SCG/tests/test_control_research.py -q --basetemp=.work/0.1.3-software-completion-20261101/control/pytest-{EPOCH}',
               'pytest_exit': 0, 'pytest_log_sha256': digest(EVIDENCE / f'task-{EPOCH}.log'),
               'runs': runs, 'scope': 'Actual generated PID/LQR cores and task; logical input ports, no hardware/electrical drive/WCET claim'}
    (EVIDENCE / f'task-{EPOCH}-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({row['kind']: row['stdout'].strip() for row in runs}))
