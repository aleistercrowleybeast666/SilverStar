import os,sys,json
from pathlib import Path
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out=Path(__file__).parent/'parent_comparison';out.mkdir(exist_ok=True)
sys.path.insert(0,str(repo/'apps/FLP/src'));os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings,QPoint
from PySide6.QtTest import QTest
from silverstar_flp.plugins.registry import builtin_registry
import silverstar_flp.ui.main_window as ui
app=QApplication([])
ui.QSettings=lambda *_:QSettings(str(out/'flp.ini'),QSettings.Format.IniFormat)
w=ui.MainWindow(builtin_registry());w.show()
records=[]
for width,height in [(1536,816),(1000,700)]:
 w.resize(width,height);QTest.qWait(200)
 pix=w.grab();name=f'flp_unsaved_{pix.width()}x{pix.height()}.png';pix.save(str(out/name))
 fields={}
 for n in ['title_label','version_label','credit_label','project_caption_label','project_name_label','language_combo','theme_combo','navigation_list']:
  widget=getattr(w,n);point=widget.mapTo(w,QPoint(0,0));fields[n]=[point.x(),point.y(),widget.width(),widget.height()]
 records.append({'file':name,'logical_size':[w.width(),w.height()],'pixel_size':[pix.width(),pix.height()],'dpr':pix.devicePixelRatioF(),'fields':fields})
 w._silverstar_project_root=out/('中文外场工程长名称测试_'*10);w._Project_SetDirty(True)
 QTest.qWait(150);pix=w.grab();pix.save(str(out/f'flp_long_dirty_{pix.width()}x{pix.height()}.png'))
 w._silverstar_project_root=None;w._Project_SetDirty(False)
(out/'geometry.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print(json.dumps(records));w.close()
