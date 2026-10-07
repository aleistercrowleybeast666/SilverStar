"""Bounded offscreen QObject contract probe; run in its own process with GC on."""
import argparse
import gc
import json
from pathlib import Path
import sys
from threading import Thread, get_ident
from time import monotonic, sleep
from weakref import finalize, ref

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt, qInstallMessageHandler, qVersion
from PySide6.QtWidgets import QApplication
import numpy as np
import PySide6
import shiboken6

from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.charts import CameraLockGLViewWidget, gl
import silverstar_flp.ui.main_window as main_window

parser = argparse.ArgumentParser()
parser.add_argument('case', choices=('mainwindow', 'transfer', 'multiple'))
parser.add_argument('--trace', type=Path, required=True)
args = parser.parse_args()
stream = args.trace.open('w', encoding='utf-8', buffering=1)
GUI = get_ident()
events = []
tracked = set()


def record(kind, **data):
    value = {'kind':kind, 'thread':get_ident(), **data}
    events.append(value)
    stream.write(json.dumps(value)+'\n'); stream.flush()


def qt_message(kind, context, message):
    record('qt_message',severity=str(kind),message=message)
    print('QT '+str(kind)+': '+message,file=sys.stderr,flush=True)


def track(obj):
    if id(obj) in tracked:
        return
    tracked.add(id(obj))
    meta = {'id':id(obj),'type':type(obj).__name__,
            'python_owned':shiboken6.ownedByPython(obj),
            'parentless':obj.parent() is None,'affinity_gui':obj.thread()==app.thread()}
    record('tracked',object=meta)
    finalize(obj,record,'python_finalize',object=meta)
    def destroyed(*_):
        record('native_destroyed',object=meta)
    obj.destroyed.connect(destroyed,Qt.ConnectionType.DirectConnection)


def track_scene(view):
    track(view.keyTimer)
    pending = list(view.items)
    while pending:
        item = pending.pop()
        track(item)
        pending.extend(item.childItems())


def native_delete(widget):
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(widget)


def worker_collect():
    def collect():
        record('worker_gc_start',gc_enabled=gc.isenabled())
        count = gc.collect()
        record('worker_gc_done',collected=count)
    worker = Thread(target=collect)
    worker.start()
    deadline = monotonic()+10
    while worker.is_alive() and monotonic()<deadline:
        app.processEvents(); sleep(.001)
    worker.join(timeout=0)
    assert not worker.is_alive(),'bounded GC injection timed out'


def mainwindow_case():
    window = main_window.MainWindow(builtin_registry())
    for view in (window.flight_page.attitude_view,window.flight_page.trajectory_view):
        track_scene(view)
    del view
    reference = ref(window)
    window._Project_SetDirty(False)
    assert window.close()
    native_delete(window)
    del window
    record('window_dropped',wrapper_alive=reference() is not None)
    worker_collect()


def transfer_case():
    first,second = CameraLockGLViewWidget(),CameraLockGLViewWidget()
    grid = gl.GLGridItem()
    original_children = tuple(grid.childItems())
    first.addItem(grid)
    track_scene(first); track(first.keyTimer); track(second.keyTimer)
    assert grid.parent() is first and grid.lineplot.parent() is grid
    assert tuple(grid.childItems())==original_children and grid.lineplot.parentItem() is grid
    assert first.keyTimer.parent() is first and not shiboken6.ownedByPython(first.keyTimer)
    first.removeItem(grid)
    assert grid.view() is None and shiboken6.isValid(grid) and grid.parent() is first
    first.addItem(grid)
    assert grid.view() is first
    first.clear()
    assert first.items==[] and grid.view() is None and shiboken6.isValid(grid)
    second.addItem(grid)
    assert grid.parent() is second and grid.view() is second
    assert grid.lineplot.parent() is grid and grid.lineplot.parentItem() is grid
    native_delete(first)
    assert shiboken6.isValid(grid) and shiboken6.isValid(grid.lineplot)
    second.clear()
    second.addItem(grid)
    # Rebuild a second static scene object; removal remains nondestructive.
    rebuilt = gl.GLGridItem(); second.addItem(rebuilt); track_scene(second)
    second.removeItem(rebuilt); second.addItem(rebuilt)
    ids = {id(grid),id(grid.lineplot),id(rebuilt),id(rebuilt.lineplot)}
    native_delete(second)
    assert not any(shiboken6.isValid(obj) for obj in (grid,grid.lineplot,rebuilt,rebuilt.lineplot))
    del grid,rebuilt,first,second,original_children
    worker_collect()
    destroyed = [e['object']['id'] for e in events if e['kind']=='native_destroyed']
    assert all(destroyed.count(identity)==1 for identity in ids),'native child deleted twice or not deleted'


def multiple_case():
    first,second = CameraLockGLViewWidget(),CameraLockGLViewWidget()
    a,b = gl.GLGridItem(),gl.GLGridItem()
    first.addItem(a); second.addItem(b)
    track_scene(first); track_scene(second)
    first.keyTimer.start(60000); second.keyTimer.start(60000)
    assert first.keyTimer.isActive() and second.keyTimer.isActive()
    native_delete(first)
    assert not shiboken6.isValid(a) and not shiboken6.isValid(first.keyTimer)
    assert shiboken6.isValid(b) and second.keyTimer.isActive()
    del first,a
    worker_collect()
    assert shiboken6.isValid(b) and b.view() is second
    native_delete(second)
    assert not shiboken6.isValid(b) and not shiboken6.isValid(second.keyTimer)
    del second,b
    worker_collect()


app = QApplication([])
app.setQuitOnLastWindowClosed(False)
qInstallMessageHandler(qt_message)
main_window.QSettings = lambda *_: QSettings(str(args.trace.with_suffix('.ini')),QSettings.Format.IniFormat)
record('environment',case=args.case,gui_thread=GUI,gc_enabled=gc.isenabled(),
       python=sys.version,numpy=np.__version__,pyside6=PySide6.__version__,qt=qVersion())
assert gc.isenabled()
assert np.__version__!='2.4.0','Known global NumPy must not run this probe'
gc.collect()
{'mainwindow':mainwindow_case,'transfer':transfer_case,'multiple':multiple_case}[args.case]()
wrong = [e for e in events if e['kind']=='native_destroyed'
         and e['object']['affinity_gui'] and e['thread']!=GUI]
record('summary',tracked_count=len(tracked),wrong_thread_native_count=len(wrong),
       gc_enabled=gc.isenabled(),qt_message_count=sum(e['kind']=='qt_message' for e in events))
print(json.dumps({'wrong_thread_native_count':len(wrong),'gc_enabled':gc.isenabled()}),flush=True)
# Keep trace open for shutdown finalizers; errors stay visible on stderr.
sys.exit(2 if wrong else 0)
