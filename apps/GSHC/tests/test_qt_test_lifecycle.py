"""Actual plot/widget cycles must be gone before a worker can trigger GC."""
import gc
from pathlib import Path
import threading
import weakref

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QThread, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from conftest import QtTest_DisposeDeferred
from services.i18n import I18n
from ui.main_window import MainWindow


def test_deferred_plot_cycles_leave_no_worker_thread_qt_callbacks(tmp_path):
    application = QApplication.instance() or QApplication([])
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
        application.setFont(QFont('Microsoft YaHei', 10))
    original_gc = gc.isenabled()
    assert original_gc, "The regression requires active automatic GC"
    gui_thread = threading.get_ident()
    destroyed = []
    windows = []
    references = []
    for index in range(4):
        window = MainWindow(I18n(QSettings(str(tmp_path / f'{index}.ini'), QSettings.IniFormat)))
        window.gl_view.hide()
        window._test_cycle = window
        window.destroyed.connect(lambda *_: destroyed.append(threading.get_ident()))
        window.show()
        application.processEvents()
        window.close()
        window.deleteLater()
        windows.append(window)
        references.append(weakref.ref(window))
    del window
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert all(not isValid(window) for window in windows)
    windows.clear()
    QtTest_DisposeDeferred()
    assert all(ref() is None for ref in references)
    assert destroyed == [gui_thread] * 4
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append((threading.get_ident(), message)))

    class Collector(QThread):
        def run(self):
            for _ in range(8):
                gc.collect()

    worker = Collector()
    try:
        worker.start()
        assert worker.wait(3000), "The bounded synthetic collector must exit"
    finally:
        qInstallMessageHandler(previous)
    assert not [message for thread, message in messages if thread != gui_thread]
    assert gc.isenabled() is original_gc
