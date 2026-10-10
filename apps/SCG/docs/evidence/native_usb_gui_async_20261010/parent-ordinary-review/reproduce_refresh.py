"""Read-only completed candidate views; isolated offscreen Qt/settings context.

No import/export/build/clean or native UI/hardware action is performed.
This is the exact program used for ordinary-offscreen-refresh.json.
"""
from pathlib import Path
import sys,json,time,os
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,r'D:\python_software\SilverStar\.work\ccdi\apps\SCG\src')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.ui.main_window import MainWindow
B=Path(__file__).parent
root=B/'ordinary-offscreen-context';root.mkdir(exist_ok=True)
s=FccgService(root)
s.catalog=PluginCatalog(Path(r'D:\python_software\SilverStar\.work\ccdi\apps\SCG\plugins\builtin'),root/'installed')
s.catalog.Scan();s.assembler.catalog=s.catalog
rows=[json.loads(x) for x in Path(r'C:\Users\chdxm\Documents\Codex\2026-10-10\task\ug08-build-index.jsonl').read_text().splitlines()]
qapp=QApplication([]);current=MainWindow(SettingsStore(root/'settings.ini'),service=s);records=[]
current._Project_Close=lambda:True
for row in rows:
    o=Path(row['output']);d=json.loads((o/'receipt.json').read_text());cache=Path(d['snapshot_root']).parent.parent
    s.hardware_importer.cache_root=cache;s.hardware_importer.policy=WorkspacePolicy(cache.parent)
    current._model=ProjectModel_Load(Path(row['project_root'])/'SilverStar.ssproject');current._project_root=Path(row['project_root'])
    ticks=[];timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:ticks.append(time.perf_counter()))
    timer.start();qapp.processEvents();ticks.clear()
    start=time.perf_counter();current._Project_Refresh();elapsed=time.perf_counter()-start;during=len(ticks)
    qapp.processEvents();timer.stop()
    records.append({'part':row['part'],'refresh_seconds':elapsed,'qt_timer_ticks_during_refresh':during,'qt_timer_ticks_after_events_processed':len(ticks),'ground_build_enabled':current.build_page.action_buttons['ground_build'].isEnabled(),'ground_open_enabled':current.build_page.action_buttons['ground_open_folder'].isEnabled(),'quality_record_count':len(s.QualityResults_Get(o))})
current._project_root=None;current.close()
(B/'ordinary-offscreen-refresh.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print(json.dumps(records,indent=2))
