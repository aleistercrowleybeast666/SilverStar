import gc
import inspect
import threading
import weakref

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker


def test_real_qthreadpool_result_publication_runs_on_gui_thread(qtbot, monkeypatch):
    window = MainWindow(builtin_registry())
    qtbot.addWidget(window)
    gui_thread = QApplication.instance().thread()
    gui_python_thread = threading.get_ident()
    observations = {}
    errors = []

    def work(context):
        observations["work_qt_gui"] = QThread.currentThread() == gui_thread
        observations["work_python_thread"] = threading.get_ident()
        return "thread-affinity-result"

    def publish(result):
        observations["callback_qt_gui"] = QThread.currentThread() == gui_thread
        observations["callback_python_thread"] = threading.get_ident()
        observations["result"] = result
        # Observe the real dispatch call stack, without replacing the QObject
        # connection target or assuming a particular private helper signature.
        frame = inspect.currentframe().f_back
        dispatch_frames = []
        while frame is not None:
            if frame.f_code.co_filename.replace("\\", "/").endswith(
                "/ui/main_window.py"
            ) and frame.f_code.co_name.startswith("_Task_"):
                dispatch_frames.append(frame.f_code.co_name)
            frame = frame.f_back
        del frame
        observations["dispatch_frames"] = dispatch_frames
        observations["publish_qt_gui"] = (
            bool(dispatch_frames) and QThread.currentThread() == gui_thread
        )
        observations["publish_python_thread"] = threading.get_ident()

    try:
        window._Task_Start(FunctionWorker(work), publish, errors.append)
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        print("Actual QThreadPool affinity:", observations, "gui_python_thread:", gui_python_thread)
        assert not errors
        assert observations["work_qt_gui"] is False
        assert observations["work_python_thread"] != gui_python_thread
        assert observations["publish_qt_gui"] is True
        assert observations["callback_qt_gui"] is True
        assert observations["publish_python_thread"] == gui_python_thread
        assert observations["callback_python_thread"] == gui_python_thread
        assert observations["result"] == "thread-affinity-result"
    finally:
        window._project_dirty = False
        window.close()


def test_completed_worker_releases_its_payload_after_gc(qtbot):
    class Payload:
        pass

    window = MainWindow(builtin_registry())
    qtbot.addWidget(window)
    payload = Payload()
    reference = weakref.ref(payload)
    worker = FunctionWorker(lambda context, captured=payload: "tiny-done")
    worker_reference = weakref.ref(worker)
    published = []
    errors = []
    try:
        window._Task_Start(worker, published.append, errors.append)
        del worker, payload
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        qtbot.waitUntil(lambda: window._thread_pool.activeThreadCount() == 0, timeout=5000)
        qtbot.wait(50)
        QApplication.instance().processEvents()
        gc.collect()
        print(
            "Completed worker after GC: worker alive=",
            worker_reference() is not None,
            ", captured payload alive=",
            reference() is not None,
        )
        assert not errors and published == ["tiny-done"]
        assert reference() is None
    finally:
        window._project_dirty = False
        window.close()
