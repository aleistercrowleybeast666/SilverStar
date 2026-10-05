"""Compile the snapshot fault injection against a freshly generated project."""
import argparse
import re
import subprocess
from pathlib import Path

def run(project, test, output, start=False, compact=False):
    project, test, output = map(lambda p: Path(p).resolve(), (project, test, output))
    output.mkdir(parents=True, exist_ok=True)
    host = (project / 'Tests/Host/run_tests.ps1').read_text()
    includes = re.findall(r'"-I\$repoRoot\\([^"\r\n]+)"', host)
    sources = ['APP/Src/logger_bus.c', 'Common/Src/common_spsc_queue.c',
               'Common/Src/silverstar_assert.c', 'System/Src/system_log_policy.c',
               'System/Src/system_profile.c', 'System/Src/system_navigation_profile.c',
               'System/Src/system_estimator_profile.c', 'Generated/Src/project_metadata.c',
               'Generated/Src/project_log_config.c', 'Generated/Src/project_log_decoder_profile.c',
               'Protocol/SSLOG/Src/sslog_records.c', 'Protocol/SSLOG/Src/sslog_protocol.c']
    binary = output / 'logger_snapshot.exe'
    cmd = ['gcc', '-std=c11', '-O2', '-flto', '-Wall', '-Wextra', '-Werror',
           '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
           '-Wl,--wrap=CommonSpscQueue_Push', '-include',
           str(project / 'Generated/Inc/project_flight_config.h')]
    cmd += ['-I' + str(project / p.replace('\\', '/')) for p in includes]
    if start:
        cmd += ['-DLOGGER_SNAPSHOT_START_TEST=1']
    if compact:
        # Explicit synthetic capacity fixture; generated production config is untouched.
        config = (project / 'System/User/system_user_config.h').read_text()
        config = re.sub(r'(#define\s+SYSTEM_LOG_RECORD_QUEUE_DEPTH\s+)\d+U', r'\g<1>8U', config)
        config = re.sub(r'(#define\s+SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH\s+)\d+U', r'\g<1>4U', config)
        (output / 'system_user_config.h').write_text(config)
        cmd[1:1] = ['-I' + str(output)]
    cmd += [str(test)] + [str(project / p) for p in sources] + ['-lm', '-o', str(binary)]
    print(subprocess.list2cmdline(cmd), flush=True)
    subprocess.run(cmd, check=True)
    return subprocess.run([str(binary)]).returncode

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project'); parser.add_argument('test'); parser.add_argument('output')
    parser.add_argument('--start', action='store_true'); parser.add_argument('--compact', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.project, args.test, args.output, args.start, args.compact))
