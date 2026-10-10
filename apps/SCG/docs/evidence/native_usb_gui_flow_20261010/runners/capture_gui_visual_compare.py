"""Offscreen regression rendering of unchanged ordinary GUI appearance."""
from pathlib import Path
from copy import deepcopy
import os,sys,json,hashlib,subprocess,importlib.util,tempfile,time
os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['PYTHONDONTWRITEBYTECODE']='1'
repo=Path(r'D:\python_software\SilverStar\.work\ccdi');task=Path(__file__).parent
sys.path.insert(0,str(repo/'apps/SCG/src'))
from PySide6.QtWidgets import QApplication,QMessageBox
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from PIL import Image,ImageChops
baseline='c55bdc3a16514f62c9a92b6a7582a7bbcdf132a3'
out=task/'usb-gui-visual';out.mkdir(exist_ok=True)
def load(name,relative):
 body=subprocess.check_output(['git','-C',str(repo),'show',baseline+':'+relative])
 path=out/(name+'.py');path.write_bytes(body)
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
old_build=load('_accepted_build_page','apps/SCG/src/silverstar_fccg/ui/pages/build.py')
old_main=load('_accepted_main_window','apps/SCG/src/silverstar_fccg/ui/main_window.py')
old_main.BuildPage=old_build.BuildPage
app=QApplication.instance() or QApplication([])
catalog=PluginCatalog(repo/'apps/SCG/plugins/builtin',repo/'apps/SCG/plugins/installed');catalog.Scan()
models=[];windows=[];records=[]
for label,cls in [('baseline',old_main.MainWindow),('current',MainWindow)]:
 root=Path(tempfile.mkdtemp(prefix='uv-'))
 service=FccgService(root);service.catalog=catalog;service.assembler.catalog=catalog
 window=cls(SettingsStore(root/'s.ini'),service=service)
 window._MessageBox_Exec=lambda *a,**k:QMessageBox.StandardButton.Discard
 window._toolchain_checked=True
 window._Toolchains_Detect=lambda:None
 if not models:models.append(deepcopy(window._model))
 window._model=deepcopy(models[0]);window._Project_Refresh();window.resize(1280,820);window.show()
 for page,widget in [('ground',window.ground_target_page),('build',window.build_page)]:
  row=next(i for i,w in enumerate(window._page_widgets) if w is widget)
  window.navigation_list.setCurrentRow(row)
  for _ in range(3):app.processEvents();time.sleep(0.02)
  path=out/(label+'-'+page+'.png');assert window.grab().save(str(path))
  records.append({'label':label,'page':page,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'width':window.width(),'height':window.height()})
 windows.append(window)
 window.hide();app.processEvents()
comparisons=[]
for page in ['ground','build']:
 a=Image.open(out/('baseline-'+page+'.png')).convert('RGBA');b=Image.open(out/('current-'+page+'.png')).convert('RGBA')
 delta=ImageChops.difference(a,b);bbox=delta.convert('RGB').getbbox()
 delta.save(out/(page+'-diff.png'))
 comparisons.append({'page':page,'pixel_difference_bbox':bbox,'identical_pixels':bbox is None})
for window in windows:window.close()
app.processEvents()
(out/'receipt.json').write_text(json.dumps({'baseline':baseline,'scope':'Same ordinary unbound reference model, Ground and Build pages, offscreen1280x820; candidate status/resource text may differ by authorized logic and is not compared here','renders':records,'comparisons':comparisons},indent=2),encoding='utf8')
print(comparisons)
