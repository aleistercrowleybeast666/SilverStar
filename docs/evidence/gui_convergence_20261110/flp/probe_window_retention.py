"""Observe real window destruction and Qt style ownership; no business mocks."""
import gc
import json
import os
from pathlib import Path
import sys
import time
import traceback
import weakref

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/FLP/src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow

app = QApplication([])
errors = []
original = sys.excepthook


def observed(kind, error, tb):
    errors.append(''.join(traceback.format_exception(kind, error, tb)))
    original(kind, error, tb)


sys.excepthook = observed
rows = []
retained = []
for policy in ('existing_close', 'native_delete_on_close'):
    for index in range(3):
        start = time.monotonic()
        window = MainWindow(builtin_registry())
        constructed = time.monotonic() - start
        if policy == 'native_delete_on_close':
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        reference = weakref.ref(window)
        window.close()
        del window
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
        app.processEvents()
        alive = reference() is not None
        row = dict(policy=policy, iteration=index, constructed_seconds=constructed,
                   wrapper_alive=alive, widgets=len(app.allWidgets()),
                   top_levels=len(app.topLevelWidgets()), callback_errors=len(errors))
        rows.append(row)
        print(json.dumps(row), flush=True)
        if alive:
            retained.append(reference)
    # End this policy's observed objects before comparing the next policy.
    for reference in retained:
        instance = reference()
        if instance is not None:
            instance.deleteLater()
    retained.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    app.processEvents()
Path(__file__).with_suffix('.json').write_text(
    json.dumps(dict(rows=rows, callback_errors=errors), indent=2), encoding='utf8')
raise SystemExit(bool(errors))
