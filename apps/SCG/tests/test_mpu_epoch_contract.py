"""Host provider contracts; real fault publication, test-only terminal process exit."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

CORE = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload'


def test_epoch_tokens_exhaustion_identity_and_fault_contracts(tmp_path):
    sources = [Path(__file__).parent / 'fixtures/mpu_epoch_contract/test_epoch_contract.c',
               Path(__file__).parent / 'fixtures/mpu_epoch_contract/assert_capture.c']
    provider = CORE / 'System/Src/system_imu_epoch.c'
    binary = tmp_path / 'epoch_contract.exe'
    argv = [os.environ.get('HOST_GCC', 'D:/msys64/ucrt64/bin/gcc.exe'), '-std=c11', '-O2',
            '-Wall', '-Wextra', '-Werror', '-pedantic', '-DSYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED=1U']
    argv += ['-I' + str(CORE / path) for path in ['Interfaces/Inc', 'System/Src', 'Common/Inc', 'Common/Src']]
    argv += ['-I' + str(Path(__file__).parent / 'fixtures/mpu_recovery')]
    argv += ['-I' + str(CORE.parent.parent / 'silverstar_platform_api/payload/Platform/Inc')]
    argv += [str(path) for path in sources] + ['-o', str(binary)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    (tmp_path / 'compile.json').write_text(json.dumps({'argv': argv, 'exit': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr,
        'sources': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in sources + [provider, CORE / 'Common/Src/silverstar_assert.c']]}, indent=2))
    assert result.returncode == 0, result.stderr
    rows = []
    terminal_cases = {2, 3, 10, 11}
    for case in range(1, 13):
        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=10)
        expected = 86
        rows.append({'case': case, 'exit': result.returncode, 'expected_exit': expected if case in terminal_cases else 0,
                     'stdout': result.stdout, 'stderr': result.stderr})
    (tmp_path / 'cases.json').write_text(json.dumps(rows, indent=2))
    assert all(row['exit'] == row['expected_exit'] for row in rows), rows
