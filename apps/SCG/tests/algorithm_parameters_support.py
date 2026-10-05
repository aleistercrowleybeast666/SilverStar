"""Run a deterministic trajectory through the generated project's real C code."""
import os
import re
import subprocess
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy


def Trajectory_Run(project: Path, workspace: Path, *, baseline: bool = False, fixture_name: str = "test_algorithm_parameters.c") -> bytes:
    policy = WorkspacePolicy(workspace)
    output = policy.Directory_Ensure(project / 'build/FCCG/Host/Tests')
    temp = policy.Directory_Ensure(output / 'tmp')
    script = (project / 'Tests/Host/run_tests.ps1').read_text(encoding='utf-8')
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    compiler = Path(r'D:\msys64\ucrt64\bin\gcc.exe')
    sources = ['Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c',
               'Algorithm/Estimator/KF6/Src/navigation_kf.c',
               'Algorithm/Common/Src/attitude_frame.c',
               'System/Src/system_estimator_profile.c',
               'Common/Src/silverstar_assert.c']
    fixture = workspace / 'plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host' / fixture_name
    command = [str(compiler), '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
               '-include', str(project / 'Generated/Inc/project_flight_config.h')]
    if baseline:
        command += ['-DSYSTEM_INS_GRAVITY_MPS2=SYSTEM_LOCAL_GRAVITY_MPS2',
                    '-DSYSTEM_KF_GRAVITY_MPS2=SYSTEM_LOCAL_GRAVITY_MPS2']
    command += ['-I' + str(project / p.replace('\\', '/')) for p in includes]
    command += [str(project / p) for p in sources] + [str(fixture), '-lm', '-o', str(output / 'parameters.exe')]
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp))
    env['PATH'] = str(compiler.parent) + os.pathsep + env.get('PATH', '')
    result = subprocess.run(command, env=env, capture_output=True)
    policy.Bytes_AtomicWrite(output / 'parameters-compile.log', result.stdout + result.stderr)
    if result.returncode:
        raise AssertionError(result.stderr.decode(errors='replace'))
    result = subprocess.run([str(output / 'parameters.exe')], env=env, capture_output=True)
    policy.Bytes_AtomicWrite(output / 'parameters-trajectory.txt', result.stdout)
    assert result.returncode == 0, result.stdout[-2000:]
    return result.stdout.replace(b'\r\n', b'\n')
