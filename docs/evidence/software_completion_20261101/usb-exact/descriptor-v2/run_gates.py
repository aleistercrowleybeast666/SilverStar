"""Execute each newly compiled private project's four unchanged emitted gates."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
environment = os.environ.copy()
environment['PATH'] = os.pathsep.join(('D:/msys64/ucrt64/bin', 'D:/Arm GNU Toolchain/14.3 rel1/bin',
                                     str(Path(sys.executable).parent), environment['PATH']))
make = shutil.which('mingw32-make', path=environment['PATH'])
gcc = shutil.which('gcc', path=environment['PATH'])
records = []
processed = set()
started = time.monotonic()
output = HERE / 'gates'
output.mkdir(exist_ok=False)
while len(processed) < 3:
    assert time.monotonic() - started < 2400, 'Build/gate observation timeout; no result inferred'
    try:
        builds = json.loads((HERE / 'build-results.json').read_text(encoding='utf8'))
    except (FileNotFoundError, json.JSONDecodeError):
        builds = []
    for build in builds:
        part = build['part']
        if part in processed:
            continue
        if not build['new_arm_executed']:
            processed.add(part)
            continue
        assert build['result'] == 'CompiledCandidate', str(build)
        project = Path(build['output'])
        compiler = json.loads((project / 'receipt.json').read_text(encoding='utf8'))
        assert compiler['status'] == 'NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
        assert compiler['warning_diagnostics'] == []
        directory = output / part; directory.mkdir()
        for gate in ('architecture-check', 'host-tests', 'power10-check', 'artifact-check'):
            command = [make, '-j2', gate, 'PYTHON=' + sys.executable, 'HOST_CC=' + gcc]
            log = directory / (gate + '.log')
            begin = time.monotonic()
            with log.open('wb') as stream:
                result = subprocess.run(command, cwd=project, env=environment, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=600)
            records.append({'part': part, 'project': str(project), 'gate': gate, 'command': command,
                            'exit_code': result.returncode, 'seconds': time.monotonic() - begin,
                            'log': log.relative_to(HERE).as_posix(),
                            'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
            (HERE / 'gate-commands.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')
            print(part, gate, result.returncode, flush=True)
        processed.add(part)
    if (HERE / 'validate.exit').is_file():
        assert (HERE / 'validate.exit').read_text().strip() == '0', 'Native build driver failed'
        assert len(builds) == 3
    if len(processed) < 3:
        time.sleep(10)
raise SystemExit(int(any(row['exit_code'] for row in records)))
