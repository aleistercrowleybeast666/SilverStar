"""Recompile Host-only deterministic producers against this turn's SCG output."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys

TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
SOURCES = json.loads((TASK / 'producer_sources.json').read_text())
OUTPUT = TASK / 'producers'
OUTPUT.mkdir(exist_ok=True)
COMPILER = 'D:/msys64/ucrt64/bin/gcc.exe'


def build(kind):
    project = TASK / 'inputs' / {'kf': 'existing', 'eskf': 'eskf', 'sf6': 'sf6'}[kind]
    target = OUTPUT / (kind + '.exe')
    graph = (project / 'Generated/project_sources.mk').read_text()
    definitions = re.search(r'^C_DEFS \+= \\\n(.*?)(?:\n\n|\Z)', graph, re.M | re.S).group(1)
    defines = ['-D' + line.strip().rstrip('\\').strip()
               for line in definitions.splitlines() if line.strip()]
    host_script = (project / 'Tests/Host/run_tests.ps1').read_text()
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', host_script)
    includes = list(dict.fromkeys([str(project), *(
        str(project / path.replace('\\', '/')) for path in includes)]))
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
             '-fno-fast-math', '-ffp-contract=off', '-flto=1',
             '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections']
    if kind in ('kf', 'eskf'):
        sources = [project / name for name in SOURCES[kind]]
        sources.append(ROOT / 'apps/FLP/tests/fixtures' / (
            'current_' + kind + '_backend_trace.c'))
        defines.append('-DTEST_EXPECT_ALIGNMENT_ALGORITHM=SYSTEM_ALIGNMENT_VECTOR_CONSTRAINTS')
        if kind == 'eskf':
            defines.append('-DTEST_ESKF_BACKEND_EXPORT=1')
    else:
        # Source set mirrors the normal generated sf6_backend_actual Host job.
        names = ['Tests/Host/host_platform_mock.c', 'APP/Src/logger_bus.c',
                 'Common/Src/common_spsc_queue.c', 'Common/Src/silverstar_assert.c',
                 'System/Src/system_log_policy.c', 'System/Src/system_profile.c',
                 'System/Src/system_navigation_profile.c', 'System/Src/system_estimator_profile.c',
                 'Generated/Src/project_metadata.c', 'Generated/Src/project_log_decoder_profile.c',
                 'Generated/Src/project_log_config.c', 'Algorithm/Common/Src/geodesy_local.c',
                 'Algorithm/Common/Src/attitude_frame.c',
                 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c',
                 'APP/Src/estimator_bus.c', 'System/Src/system_navigation_health.c',
                 'System/Src/system_gnss_quality.c', 'System/Src/system_barometer.c',
                 'System/Src/system_time.c', 'Protocol/SSLOG/Src/sslog_records.c',
                 'Protocol/SSLOG/Src/sslog_protocol.c', 'Tests/Host/test_sf6_backend.c',
                 'Algorithm/Estimator/SF6/Src/navigation_sf6.c',
                 'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c',
                 'System/Src/system_gnss_receipt.c', 'System/Src/system_mission_process.c',
                 'Generated/Src/project_mission_process.c']
        sources = [project / name for name in names]
        defines.append('-DTEST_SF6_BACKEND_EXPORT=1')
    command = [COMPILER, *flags, *defines, '-include',
               str(project / 'Generated/Inc/project_flight_config.h'),
               *('-I' + path for path in includes), *map(str, sources), '-lm', '-o', str(target)]
    environment = dict(os.environ, TEMP=str(OUTPUT), TMP=str(OUTPUT))
    environment['PATH'] = 'D:/msys64/ucrt64/bin;' + environment.get('PATH', '')
    compiled = subprocess.run(command, capture_output=True, text=True, env=environment)
    receipt = dict(scope=__doc__, project=str(project), command=command,
        compile_exit=compiled.returncode, stdout=compiled.stdout, stderr=compiled.stderr,
        compiler=subprocess.check_output([COMPILER, '--version'], text=True),
        source_sha256={str(path): sha256(path.read_bytes()).hexdigest() for path in sources},
        generated_header_sha256={str(path): sha256(path.read_bytes()).hexdigest()
            for path in (project/'Generated/Inc').glob('*.h')})
    (OUTPUT/(kind+'-compile.log')).write_text(compiled.stdout+compiled.stderr, encoding='utf8')
    if compiled.returncode == 0:
        output = OUTPUT / (kind + ('.jsonl' if kind == 'kf' else '.sslog'))
        assert not output.exists(), 'Never overwrite a previous output'
        result = subprocess.run([str(target), str(output)], capture_output=True, text=True,
                                env=environment, timeout=60)
        receipt.update(run_command=[str(target), str(output)], run_exit=result.returncode,
                       run_stdout=result.stdout, run_stderr=result.stderr)
        if output.exists():
            receipt['output_sha256'] = sha256(output.read_bytes()).hexdigest()
    (OUTPUT/(kind+'.json')).write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(kind, 'compile', compiled.returncode, 'run', receipt.get('run_exit'), flush=True)
    return receipt.get('run_exit', compiled.returncode)


if __name__ == '__main__':
    failed = False
    for kind in sys.argv[1:] or ('kf', 'eskf', 'sf6'):
        failed |= build(kind) != 0
    raise SystemExit(int(failed))
