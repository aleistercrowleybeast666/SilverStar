from pathlib import Path
import subprocess,json,os,sys,datetime
root=Path(sys.argv[1]); label=sys.argv[2]
out=Path(__file__).resolve().parent
python='D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe'
env=os.environ.copy();env['PATH']='D:/msys64/ucrt64/bin;D:/Arm GNU Toolchain/14.3 rel1/bin;'+env.get('PATH','')
env['PYTHONDONTWRITEBYTECODE']='1'
commands=[('architecture',[python,'Tools/check_native_ground.py']),
          ('host',[python,'Tools/check_native_ground.py','host','--host-cc','gcc']),
          ('artifact',[python,'Tools/check_native_ground.py','artifact','--prefix','arm-none-eabi-']),
          ('power10',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','Tools/check_power_of_ten.ps1','-TargetKind','Ground'])]
results=[]
for name,command in commands:
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=600)
    (out/(label+'-'+name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
    (out/(label+'-'+name+'.exit')).write_text(str(result.returncode))
    results.append({'name':name,'command':command,'cwd':str(root),'started_utc':started,'exit':result.returncode})
    (out/(label+'-gates.json')).write_text(json.dumps(results,indent=2))
    print(name,result.returncode,flush=True)
