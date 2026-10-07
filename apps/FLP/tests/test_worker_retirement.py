"""Actual-return and GUI disposal contracts using one tiny held runnable."""
from threading import Event, get_ident

import pytest
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker, WorkerRetireResult


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    import silverstar_flp.ui.main_window as module
    monkeypatch.setattr(module, 'QSettings', lambda *args:
                        QSettings(str(tmp_path/'private.ini'), QSettings.Format.IniFormat))
    result = MainWindow(builtin_registry()); qtbot.addWidget(result)
    yield result
    result._Project_SetDirty(False)
    result.close()


class Receipt(QObject):
    def __init__(self):
        super().__init__()
        self.received = Event()
        self.gui = False

    @Slot()
    def Finish_Receive(self):
        self.gui = QThread.currentThread() == QApplication.instance().thread()
        self.received.set()


def test_finished_does_not_retire_or_allow_close_until_actual_return(qtbot, window):
    entered, start, release, exited = Event(), Event(), Event(), Event()
    results, errors, destroyed = [], [], []
    gui_id = get_ident()
    def work(context):
        entered.set(); assert start.wait(5)
        return 'tiny-result'
    class HeldReturnWorker(FunctionWorker):
        def run(self):
            try:
                super().run()
                assert release.wait(5)
            finally:
                exited.set()
    worker = HeldReturnWorker(work)
    window._Task_Start(worker, results.append, errors.append)
    receipt = Receipt()
    worker.signals.finished.connect(receipt.Finish_Receive, Qt.ConnectionType.QueuedConnection)
    worker.signals.destroyed.connect(lambda *_: destroyed.append(get_ident()),
                                    Qt.ConnectionType.DirectConnection)
    try:
        qtbot.waitUntil(entered.is_set, timeout=5000)
        start.set()
        qtbot.waitUntil(receipt.received.is_set, timeout=5000)
        assert receipt.gui and results == ['tiny-result'] and not errors
        assert window._active_worker is worker
        assert worker.signals.parent() is window
        assert window._thread_pool.activeThreadCount() == 1 and not exited.is_set()
        assert worker._function is not None and worker.context.progress_callback is not None
        assert worker.Worker_Retire(window._thread_pool) == WorkerRetireResult.RUNNING
        event = QCloseEvent(); window.closeEvent(event)
        assert not event.isAccepted() and window._active_worker is worker
    finally:
        start.set(); release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
    assert exited.is_set() and window._thread_pool.waitForDone(0)
    assert worker._retired and worker._function is None and worker.context.progress_callback is None
    qtbot.waitUntil(lambda: bool(destroyed), timeout=5000)
    assert destroyed == [gui_id]
    assert worker.Worker_Retire(window._thread_pool) == WorkerRetireResult.ALREADY_RETIRED


def test_old_sender_cannot_finish_cancel_or_publish_into_active_task(qtbot, window):
    entered, release = Event(), Event()
    results, errors = [], []
    def work(context):
        entered.set(); assert release.wait(5)
        return 'current'
    worker = FunctionWorker(work)
    window._Task_Start(worker, results.append, errors.append)
    old = FunctionWorker(lambda context: 'old')
    old.signals.setParent(window)
    queued = Qt.ConnectionType.QueuedConnection
    connections = [old.signals.progress.connect(window._Task_Progress, queued),
        old.signals.result.connect(window._Task_ResultDispatch, queued),
        old.signals.error.connect(window._Task_Error, queued),
        old.signals.cancelled.connect(window._Task_Cancelled, queued),
        old.signals.finished.connect(window._Task_Finish, queued)]
    receipt = Receipt()
    old.signals.finished.connect(receipt.Finish_Receive, queued)
    try:
        qtbot.waitUntil(entered.is_set, timeout=5000)
        old.signals.progress.emit(1., 'old')
        old.signals.result.emit('wrong')
        old.signals.error.emit('wrong', 'wrong')
        old.signals.cancelled.emit()
        old.signals.finished.emit()
        qtbot.waitUntil(receipt.received.is_set, timeout=5000)
        assert window._active_worker is worker and not window._worker_finished_seen
        assert not window._worker_cancelled_published and window.progress_bar.value() == 0
        assert not errors and not results
    finally:
        for connection in connections: QObject.disconnect(connection)
        old.signals.deleteLater()
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
    assert results == ['current'] and not errors


def test_nested_result_event_loop_keeps_callbacks_until_publication_returns(qtbot, window):
    callbacks = []
    def publish(result):
        # Modal result/error handling may deliver finished while publishing.
        qtbot.waitUntil(lambda: window._worker_finished_seen, timeout=5000)
        assert window._thread_pool.waitForDone(0)
        qtbot.wait(30)
        assert window._active_worker is worker
        assert window._worker_result_callback is publish
        assert worker._function is not None
        callbacks.append(result)
    worker = FunctionWorker(lambda context: 'published')
    window._Task_Start(worker, publish, pytest.fail)
    qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
    assert callbacks == ['published']
    assert worker._retired and window._worker_result_callback is None
