import gc
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/FLP'))
from threading import Thread
import shiboken6
import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from tests.test_project_artifact_boundaries import _SmallRun

@pytest.mark.parametrize('flush', ['close_only', 'deferred', 'flush'])
def test_closed_window_worker_collection(qapp, tmp_path, flush):
    gc.collect()
    gc.disable()
    window = MainWindow(builtin_registry())
    opened, document, store = _SmallRun(tmp_path)
    window._LogOpenResult_Set(opened, document)
    window._replay_store.Result_Add(store.Entries_Get()[0].result)
    window._Pages_Refresh()
    window._Project_SetDirty(False)
    window.close()
    if flush != 'close_only':
        window.deleteLater()
    if flush == 'flush':
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    print('VALID BEFORE GC', shiboken6.isValid(window), 'flush', flush, flush=True)
    del window
    worker = Thread(target=gc.collect)
    worker.start(); worker.join(10)
    assert not worker.is_alive()
    gc.enable()
