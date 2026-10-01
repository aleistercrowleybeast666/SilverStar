import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
evidence = root / 'docs/FCCG/gui_closeout_20261001_v1'
commands = {
    'python': [sys.executable, '--version'],
    'arm_gcc': ['D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-gcc.exe', '--version'],
    'host_gcc': ['D:/msys64/ucrt64/bin/gcc.exe', '--version'],
    'make': ['D:/msys64/ucrt64/bin/mingw32-make.exe', '--version'],
    'powershell': ['powershell', '-NoProfile', '-Command', '$PSVersionTable | Out-String'],
    'git': ['git', '--version'],
}
versions = {}
for name, command in commands.items():
    result = subprocess.run(command, cwd=root, capture_output=True)
    versions[name] = dict(command=command, exit_code=result.returncode,
        output=(result.stdout + result.stderr).decode('utf-8', errors='replace'))
(evidence/'tool_versions.json').write_text(json.dumps(versions, indent=2)+'\n', encoding='utf-8')
(evidence/'source_snapshot.diff').write_bytes(subprocess.check_output(['git','diff','--binary','HEAD'],cwd=root))
paths = subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=root).decode().splitlines()
paths += ['SCG.py', 'apps/FCCG/src/silverstar_fccg/project/power10_report.py',
          'apps/FCCG/src/silverstar_fccg/project/release_policy.py',
          'apps/FCCG/tests/test_release_closeout.py', 'apps/FLP/tests/test_gui_release_identity.py']
hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths if (root/name).is_file()}
(evidence/'source_snapshot_sha256.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
for version in ('v2','v3'):
    generated = root / ('.work/SCG_Closeout_2175d95_'+version)
    files = {str(path.relative_to(generated)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in generated.rglob('*') if path.is_file()}
    (evidence/('generated_'+version+'_sha256.json')).write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
for name in ('gui_closeout_generate.py','gui_closeout_run.py','gui_closeout_snapshot.py'):
    shutil.copy2(root/'.work'/name, evidence/name)
print('Saved tool versions, dirty source snapshot, and v2/v3 generated hashes.')
