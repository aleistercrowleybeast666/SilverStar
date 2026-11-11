"""Real accepted/ignored close boundaries, including native Qt ownership."""
import threading

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QMessageBox
from shiboken6 import getCppPointer, isValid

from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker
from tests.gui_lifecycle import MainWindow_Register


def _WidgetIds_Get(application):
    return {getCppPointer(widget)[0] for widget in application.allWidgets()}


def test_repeated_accepted_close_releases_entire_native_tree(qapp, qtbot):
    before = _WidgetIds_Get(qapp)
    for index in range(3):
        window = MainWindow(builtin_registry())
        MainWindow_Register(qtbot, window)
        window.Theme_Apply('dark' if index % 2 else 'light')
        assert _WidgetIds_Get(qapp) - before
        assert window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(window)
        assert not _WidgetIds_Get(qapp) - before


def test_unsaved_cancel_keeps_window_and_discard_destroys(qapp, qtbot):
    window = MainWindow(builtin_registry())
    MainWindow_Register(qtbot, window)
    window._project.notes = 'private unsaved draft'
    window._Project_SetDirty(True)
    answers = []

    def choose(answer):
        dialog = window.findChild(QMessageBox)
        assert dialog is not None
        dialog.button(answer).click()
        answers.append(answer)

    QTimer.singleShot(0, lambda: choose(QMessageBox.StandardButton.Cancel))
    assert not window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert isValid(window) and window._project_dirty
    assert window._project.notes == 'private unsaved draft'
    QTimer.singleShot(0, lambda: choose(QMessageBox.StandardButton.Discard))
    assert window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(window)
    assert answers == [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard]


def test_busy_close_keeps_window_until_real_worker_retires(qapp, qtbot):
    window = MainWindow(builtin_registry())
    MainWindow_Register(qtbot, window)
    entered, release = threading.Event(), threading.Event()
    published = []
    errors = []

    def work(context):
        entered.set()
        assert release.wait(5)
        context.Cancel_RaiseIfRequested()
        return 'must not publish a cancelled result'

    worker = FunctionWorker(work)
    window._Task_Start(worker, published.append, errors.append)
    qtbot.waitUntil(entered.is_set)
    try:
        assert not window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert isValid(window) and window._active_worker is worker
        assert not published
    finally:
        release.set()
    qtbot.waitUntil(lambda: not isValid(window), timeout=5000)
    assert not published and not errors
