from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
out=repo/'.work/gshc_final_evidence';out.mkdir(exist_ok=False)
gui=repo/'apps/GSHC/tests/test_navigation_gui.py';shutil.copy2(gui,out/'before_font_setup.py')
p=repo/'docs/GSHC/AIR_PROTOCOL.md';shutil.copy2(p,out/'before_decode_table.md')
s=p.read_text(encoding='utf8');heading='## 41. 导航扩展 schema 1：延期，保留历史记录解码资料';assert heading in s
insert='''
仅用于历史记录解码的固定长度（本次发布不发送）：

| ID | type | bytes | 范围 |
|---|---|---|---|
| `0x15` | `NAV_CAPABILITY` | 9 | 历史实验解码，不启用发送 |
| `0x16` | `NAV_PREPARATION` | 9 | 历史实验解码，不启用发送 |
| `0x17` | `NAV_HEALTH` | 9 | 历史实验解码，不启用发送 |
'''
s=s.replace(heading,heading+'\n'+insert);p.write_text(s,encoding='utf8')
s=gui.read_text(encoding='utf8').replace('from PySide6.QtTest import QTest','from PySide6.QtTest import QTest\nfrom PySide6.QtGui import QFont, QFontDatabase')
s=s.replace('    application = QApplication.instance() or QApplication([])','''    application = QApplication.instance() or QApplication([])
    # Preserve the original GUI test's explicit font setup across Qt backends.
    for name in ("msyh.ttc", "segoeui.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    application.setFont(QFont("Microsoft YaHei", 9))''')
s=s.replace('f"{name}_{language.value}_{theme.value}.png"','f"{application.platformName()}_{name}_{language.value}_{theme.value}.png"')
gui.write_text(s,encoding='utf8')
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/GSHC')+';'+str(repo/'apps/GSHC/tests'))
records=[]
def run(name,paths,backend,base):
 command=[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work'/base),*paths]
 log=out/(name+'.log');start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with log.open('w',encoding='utf8') as stream:result=subprocess.run(command,cwd=repo,env=dict(env,QT_QPA_PLATFORM=backend),stdout=stream,stderr=subprocess.STDOUT)
 r={'name':name,'command':command,'cwd':str(repo),'qt_backend':backend,'exit':result.returncode,'started':start,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 records.append(r);(out/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
 print(name,result.returncode,flush=True);print(log.read_text(encoding='utf8',errors='replace')[-2000:],flush=True)
 return result.returncode
if run('docs_gui_offscreen',['apps/GSHC/tests/test_docs.py','apps/GSHC/tests/test_navigation_gui.py'],'offscreen','gshc_docs_gui_final')!=0:sys.exit(1)
if run('live_windows',['apps/GSHC/tests/test_navigation_gui.py'],'windows','gshc_live_final')!=0:sys.exit(1)
if run('GSHC_full',['apps/GSHC/tests'],'offscreen','gshc_full_final')!=0:sys.exit(1)
