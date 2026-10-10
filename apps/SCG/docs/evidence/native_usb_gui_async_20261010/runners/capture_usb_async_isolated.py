from pathlib import Path
import os,sys,subprocess,json,hashlib
from PIL import Image,ImageChops
task=Path(__file__).parent
original=(task/'capture_usb_async_visual.py').read_text(encoding='utf8')
out=task/'usb-async-visual-isolated';out.mkdir(exist_ok=True)
for label in ['baseline','current']:
    s=original.replace("out=task/'usb-async-visual';","out=task/'usb-async-visual-isolated';")
    s=s.replace("[('baseline',old_main.MainWindow),('current',MainWindow)]", "[('"+label+"',"+('old_main.MainWindow' if label=='baseline' else 'MainWindow')+")]")
    s=s.replace('  for _ in range(3):app.processEvents();time.sleep(0.02)','  for _ in range(100):app.processEvents();time.sleep(0.01)')
    s=s[:s.index('comparisons=[]')]+"\nfor window in windows:window.close()\napp.processEvents()\n(out/(label+'-render.json')).write_text(json.dumps(records,indent=2),encoding='utf8')\n"
    p=task/('isolated-render-'+label+'.py');p.write_text(s,encoding='utf8')
    run=subprocess.run([r'D:\python_software\SilverStar\apps\FLP\.venv\Scripts\python.exe','-B',str(p)],capture_output=True,text=True)
    (out/(label+'.log')).write_text(run.stdout+run.stderr,encoding='utf8')
    assert run.returncode==0,(label,run.stderr)
comparisons=[]
for page in ['ground','build']:
    a=Image.open(out/('baseline-'+page+'.png')).convert('RGB');b=Image.open(out/('current-'+page+'.png')).convert('RGB')
    diff=ImageChops.difference(a,b);diff.save(out/(page+'-diff.png'));bbox=diff.getbbox()
    comparisons.append({'page':page,'identical_pixels':bbox is None,'pixel_difference_bbox':bbox})
record={'baseline':'bf22bdcd56e76687e8be40d5f221cb3c29668ec1','scope':'Separate identical offscreen processes, ordinary unbound reference model, 1280x820, no product visual changes','comparisons':comparisons}
(out/'receipt.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(record))
