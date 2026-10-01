import subprocess
import json
from pathlib import Path
out = Path(__file__).parent.resolve()
focused = out / 'focused_host.py'
namespace = {'__file__': str(focused)}
source = focused.read_text(encoding='utf-8')
exec(compile(source[:source.index('report = []')], str(focused), 'exec'), namespace)
project = out / 'candidate_a_v6/Flight_Controller'
command = [arg.replace(str(namespace['project']), str(project)) for arg in namespace['base']] + [
    '-I' + str(namespace['radio'] / 'Devices/Telemetry/SX1281/Src'),
    str(out / 'radio_ack_wait.c'), str(project / 'Generated/Src/project_resources.c'),
    str(project / 'Protocol/Src/air_protocol.c'),
    str(project / 'Common/Src/silverstar_assert.c'), '-lm', '-o', str(out / 'radio_ack_wait.exe')]
with (out / 'radio_ack_wait_compile2.log').open('w') as log:
    compiled = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
report = {'command': command, 'compile_exit': compiled.returncode}
if compiled.returncode == 0:
    result = subprocess.run([str(out / 'radio_ack_wait.exe')], capture_output=True, text=True)
    (out / 'radio_ack_wait_run.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    report['run_exit'] = result.returncode
    print(result.stdout + result.stderr)
else:
    print((out / 'radio_ack_wait_compile2.log').read_text()[-2000:])
(out / 'radio_ack_wait_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
