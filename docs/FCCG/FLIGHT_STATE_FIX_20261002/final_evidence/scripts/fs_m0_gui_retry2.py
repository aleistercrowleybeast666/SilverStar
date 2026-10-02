from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
out=repo/'.work/gshc_retry2_evidence';out.mkdir(exist_ok=False)
env=dict(os.environ,PATH=r'D:\python_software\SilverStar\.venv\Scripts;D:\msys64\ucrt64\bin;'+os.environ['PATH'],PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf8',PYTHONPATH=str(repo/'apps/GSHC')+';'+str(repo/'apps/GSHC/tests'))
records=[]
def run(name,paths,backend,base):
 command=[sys.executable,'-m','pytest','-q','-o','addopts=','-p','no:cacheprovider','--basetemp='+str(repo/'.work'/base),*paths]
 log=out/(name+'.log');start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with log.open('w',encoding='utf8') as stream:result=subprocess.run(command,cwd=repo,env=dict(env,QT_QPA_PLATFORM=backend),stdout=stream,stderr=subprocess.STDOUT)
 r={'name':name,'command':command,'cwd':str(repo),'qt_backend':backend,'exit':result.returncode,'started':start,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'log':str(log),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 records.append(r);(out/'results.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
 print(name,result.returncode,flush=True);print(log.read_text(encoding='utf8',errors='replace')[-1800:],flush=True)
 return result.returncode
if run('live_windows',['apps/GSHC/tests/test_navigation_gui.py'],'windows','gshc_live_gui_retry2')!=0:sys.exit(1)
if run('touch_offscreen',['apps/GSHC/tests/test_touch_scroll.py'],'offscreen','touch_offscreen_retry2')!=0:sys.exit(1)
if run('full_offscreen',['apps/GSHC/tests'],'offscreen','gshc_full_retry2')!=0:sys.exit(1)
