from pathlib import Path
from datetime import datetime,timezone
import sys,os,json,tempfile,time,hashlib,subprocess
repo=Path(__file__).parent/'r';task=Path(__file__).parent;root=Path(tempfile.mkdtemp(prefix='daily-scg-startup-'))
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.path.insert(0,str(repo/'apps/SCG/src'))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QMessageBox
from silverstar_fccg.app import application
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.ui.main_window import MainWindow
errors=[];ticks=[];windows=[];deadline=time.monotonic()+20
service=FccgService(root);catalog=PluginCatalog(repo/'apps/SCG/plugins/builtin',repo/'apps/SCG/plugins/installed');catalog.Scan()
service.catalog=catalog;service.assembler.catalog=catalog
# Isolate only writable settings/log/workspace state; exact daily sources and
# declarative plugins plus production application.main/MainWindow remain real.
application.WorkspaceRoot_Get=lambda:root
application.FccgService=lambda workspace:service
original=application.MainWindow
def create(*args,**kwargs):
    window=original(*args,**kwargs);windows.append(window)
    timer=QTimer(window);timer.setInterval(20);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
    window._MessageBox_Exec=lambda *a,**k:QMessageBox.StandardButton.Discard
    window._Error_Show=lambda *a:errors.append([str(x) for x in a])
    def finish():
        if window._active_worker is None and not window._retired_workers and not window._usb_refresh_timer.isActive():window.close()
        elif time.monotonic()<deadline:QTimer.singleShot(100,window,finish)
        else:errors.append('startup background task did not finish within20s');window._Task_Cancel();window.close()
    QTimer.singleShot(1200,window,finish)
    return window
application.MainWindow=create
def unexpected_dialog(box):
    errors.append('unexpected startup exception dialog: '+box.detailedText());QTimer.singleShot(0,QApplication.instance().quit)
    return QMessageBox.StandardButton.Ok
QMessageBox.exec=unexpected_dialog
started=datetime.now(timezone.utc).isoformat();result=application.main(['--lang','zh_CN','--theme','light'])
assert result==0 and len(windows)==1 and len(ticks)>20 and not errors,(result,len(windows),len(ticks),errors)
assert Path(sys.modules['silverstar_fccg.ui.main_window'].__file__).resolve().is_relative_to(repo/'apps/SCG/src')
d={'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'exit':result,'ticks':len(ticks),'errors':errors,
 'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'workspace':str(root),
 'scope':'Actual isolated SCG application.main and MainWindow show/event loop/normal shutdown with exact isolated declarative catalog; writable settings/log/workspace in Temp. No hardware or user preference changes.',
 'source_files':{p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in ['apps/SCG/src/silverstar_fccg/app/application.py','apps/SCG/src/silverstar_fccg/ui/main_window.py']}}
(task/'sr-startup.json').write_text(json.dumps(d,indent=2),encoding='utf8')
print(json.dumps(d,indent=2))
