import ctypes
import gc
import json
from pathlib import Path
from threading import Thread, get_ident
from time import monotonic, sleep
from weakref import ref
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/FLP/src'))
import pyqtgraph as pg
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, Qt, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from silverstar_flp.ui.plot_helpers import _Plot_Prepare

ctypes.windll.kernel32.SetErrorMode(0x8003)
stream = Path(sys.argv[1]).open('w', encoding='utf-8', buffering=1)
gui = get_ident()
events = []
def record(kind, **data):
    event = dict(kind=kind, thread=get_ident(), gui=gui, **data)
    events.append(event); stream.write(json.dumps(event)+'\n')
qInstallMessageHandler(lambda kind, context, message: record('qt', text=message))
app = QApplication([])
plot = pg.PlotWidget(); _Plot_Prepare(plot, 'light')
item = plot.getPlotItem()
menus = [item.ctrlMenu, item.getViewBox().menu]
weak = []
for index, menu in enumerate(menus):
    record('menu', index=index, parentless=menu.parent() is None, python_owned=shiboken6.ownedByPython(menu))
    weak.append(ref(menu))
    menu.destroyed.connect(lambda *_, index=index: record('destroyed', index=index), Qt.ConnectionType.DirectConnection)
del menu
plot.deleteLater(); QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
record('after_native_window_delete', menu_valid=[shiboken6.isValid(menu) for menu in menus])
del menus, item, plot
def collect():
    record('gc_start'); count=gc.collect(); record('gc_done',count=count)
worker=Thread(target=collect); worker.start()
deadline=monotonic()+10
while worker.is_alive() and monotonic()<deadline:
    app.processEvents(); sleep(.001)
worker.join(0)
record('summary', worker_alive=worker.is_alive(), wrong=sum(e['kind']=='destroyed' and e['thread']!=gui for e in events),
    remaining=[obj is not None and shiboken6.isValid(obj) for obj in (r() for r in weak)])
print(events[-1], flush=True)
raise SystemExit(1 if events[-1]['wrong'] or events[-1]['worker_alive'] else 0)
