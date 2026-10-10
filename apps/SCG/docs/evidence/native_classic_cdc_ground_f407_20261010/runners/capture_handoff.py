from pathlib import Path
import subprocess, json, hashlib
root=Path('D:/python_software/SilverStar/.work/ccdi')
dest=Path(__file__).resolve().parent/'handoff_snapshot'
dest.mkdir(exist_ok=True)
status=subprocess.check_output(['git','-C',str(root),'status','--porcelain','-z'])
files=[]
for item in status.decode().split('\0'):
    if item:
        files.append(item[3:])
manifest={}
for name in files:
    p=root/name
    if p.is_file():
        data=p.read_bytes();target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        manifest[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
(dest/'dirty.diff').write_bytes(subprocess.check_output(['git','-C',str(root),'diff','--binary']))
(dest/'manifest.json').write_text(json.dumps({'head':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'files':manifest},indent=2))
print(len(manifest),'incoming changed sources preserved')
