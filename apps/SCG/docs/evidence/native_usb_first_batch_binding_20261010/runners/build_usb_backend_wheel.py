from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, zipfile

task=Path(__file__).resolve().parent
root=Path(r'D:\python_software\SilverStar\.work\ccdi')
output=Path(r'C:\Users\chdxm\AppData\Local\Temp\usb-ground-wheel-20261010')
assert not output.exists()
output.mkdir()
env=os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PIP_NO_INDEX='1')
command=['D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe','-B','-m','pip','wheel',
    '--no-deps','--no-build-isolation','--no-index','--wheel-dir',str(output),str(root/'apps/SCG')]
record={'command':command,'started_utc':datetime.now(timezone.utc).isoformat(),
    'pyproject_sha256':hashlib.sha256((root/'apps/SCG/pyproject.toml').read_bytes()).hexdigest()}
with (task/'usb-wheel.log').open('w',encoding='utf-8') as stream:
    result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
record.update(exit=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
if result.returncode==0:
    wheels=list(output.glob('*.whl'))
    assert len(wheels)==1
    wheel=wheels[0]
    record.update(wheel=str(wheel),wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
    with zipfile.ZipFile(wheel) as archive:
        names=[n for n in archive.namelist() if '/hardware/usb_profiles/' in n and n.endswith('.json')]
        assert len(names)==4
        record['profile_sha256']={n:hashlib.sha256(archive.read(n)).hexdigest() for n in names}
        for name in names:
            source=root/'apps/SCG/src'/name
            assert archive.read(name)==source.read_bytes()
else:
    record['failure']=(task/'usb-wheel.log').read_text(encoding='utf-8')[-5000:]
(task/'usb-wheel.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))
