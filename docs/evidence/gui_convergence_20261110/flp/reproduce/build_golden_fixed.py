"""Fresh fixed owning C codec and legacy numerical producers; no byte patches."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys

TASK=Path(__file__).resolve().parent
ROOT=TASK.parents[2]
sys.path.insert(0,str(ROOT/'apps/SCG/tests'))
from joint_navigation_support import NavigationGolden_Generate

project=TASK/'inputs/codec-golden'
script=(project/'Tests/Host/run_tests.ps1').read_text()
includes=re.findall(r'"-I\$repoRoot\\([^"\n]+)"',script)
sources=[project/path for path in ('Tests/Host/generate_golden_sample.c',
    'Generated/Src/project_log_decoder_profile.c', 'Protocol/SSLOG/Src/sslog_protocol.c',
    'Protocol/SSLOG/Src/sslog_records.c', 'Common/Src/silverstar_assert.c')]
output=TASK/'producers/codec-golden2'
output.mkdir(exist_ok=False)
target=output/'golden_sample.exe'
command=['D:/msys64/ucrt64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror',
         '-include',str(project/'Generated/Inc/project_flight_config.h'),
         *['-I'+str(project/path.replace('\\','/')) for path in includes],
         *map(str,sources),'-lm','-o',str(target)]
environment=dict(os.environ, TEMP=str(output),TMP=str(output))
log=project/'Logs/Golden/SS_TEST_0_golden.sslog'
assert not log.exists()
environment['SILVERSTAR_GOLDEN_OUTPUT']=str(log)
run=subprocess.run(command,env=environment,capture_output=True,text=True)
receipt=dict(scope=__doc__,command=command,compile_exit=run.returncode,
             stdout=run.stdout,stderr=run.stderr,
             sources={str(path):sha256(path.read_bytes()).hexdigest() for path in sources})
if run.returncode==0:
    result=subprocess.run([str(target)],env=environment,capture_output=True,text=True)
    receipt.update(run_exit=result.returncode,run_stdout=result.stdout,run_stderr=result.stderr,
                   log_sha256=sha256(log.read_bytes()).hexdigest())
(output/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print('codec',receipt['compile_exit'],receipt.get('run_exit'),flush=True)
assert receipt.get('run_exit')==0,receipt
joint=TASK/'producers/joint2'
assert not joint.exists()
log=NavigationGolden_Generate(TASK/'inputs/joint',joint,scenario='integrity')
(joint/'receipt.json').write_text(json.dumps(dict(scope=__doc__,log=str(log),
    log_sha256=sha256(log.read_bytes()).hexdigest(),
    producer_sha256=sha256((ROOT/'apps/SCG/tests/fixtures/joint_navigation_golden.c').read_bytes()).hexdigest()),indent=2),encoding='utf8')
print('joint2 compiled and ran',flush=True)
