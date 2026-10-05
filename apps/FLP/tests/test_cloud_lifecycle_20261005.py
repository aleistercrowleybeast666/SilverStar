"""Fix-expected acceptance tests for eedc923, never old bug-observation asserts."""
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from silverstar_flp.decoder_profiles.discovery import TaskDirectoryDiscovery
from silverstar_flp.export.service import FlightExporter, ExportOptions
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.workers import FunctionWorker


@pytest.fixture
def window(qtbot, monkeypatch):
    w = MainWindow(builtin_registry())
    qtbot.addWidget(w)
    # Keep unexpected errors observable without a blocking modal dialog.
    w.audit_errors = []
    monkeypatch.setattr(w, "_Error_Show", w.audit_errors.append)
    yield w
    w._project_dirty = False
    w.import_dialog.reject()
    w.export_dialog.reject()
    w._dataset = None
    w.close()


def finish(qtbot, w):
    qtbot.waitUntil(lambda: w._active_worker is None, timeout=5000)


@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
def test_terminal_controls_and_error_status(qtbot, window, outcome):
    results, errors = [], []
    def work(ctx):
        ctx.Progress_Report(.25, "replay.running")
        if outcome == "error":
            raise ValueError("audit_failure")
        if outcome == "cancel":
            ctx.Cancel_Request()
            ctx.Cancel_RaiseIfRequested()
        return "OK"
    window._Task_Start(FunctionWorker(work), results.append, errors.append)
    finish(qtbot, window)
    assert results == (["OK"] if outcome == "success" else [])
    assert errors == (["audit_failure"] if outcome == "error" else [])
    assert window.progress_bar.isHidden() and window.cancel_button.isHidden()
    assert window.import_action.isEnabled() and window.new_project_action.isEnabled()
    if outcome == "error":
        assert window.status_label.text() == window._translator.Text_Get("status.failed")
    if outcome == "cancel":
        assert window.status_label.text() == window._translator.Text_Get("status.task_cancelled")


def test_repeat_start_preserves_active_worker(qtbot, window):
    entered, release = threading.Event(), threading.Event()
    def work(ctx):
        entered.set()
        assert release.wait(5)
        return "OK"
    errors, results = [], []
    first = FunctionWorker(work)
    window._Task_Start(first, results.append, errors.append)
    qtbot.waitUntil(entered.is_set)
    try:
        window._Task_Start(FunctionWorker(lambda ctx: "BAD"), results.append, errors.append)
        assert window._active_worker is first
        assert errors == ["another_background_task_is_running"]
    finally:
        release.set()
        finish(qtbot, window)
    assert results == ["OK"]


@pytest.mark.parametrize("action", ["task_cancel", "dialog_reject", "replace_request"])
def test_discovery_discards_cancelled_or_obsolete_result(qtbot, monkeypatch, window, tmp_path, action):
    entered, release = threading.Event(), threading.Event()
    def scan(path):
        entered.set()
        assert release.wait(5)
        return TaskDirectoryDiscovery(path, (), (), 0, 0, False)
    monkeypatch.setattr(window._log_open_coordinator.scanner, "Scan", scan)
    published = []
    original = window.import_dialog.PairDiscovery_Set
    def publish(discovery):
        published.append(discovery.selected_path)
        original(discovery)
    monkeypatch.setattr(window.import_dialog, "PairDiscovery_Set", publish)
    path_a, path_b = tmp_path / "A", tmp_path / "B"
    window.import_dialog.Folder_Set(path_a)
    window.import_dialog.open()
    window.import_dialog._FolderSearch_Request()
    qtbot.waitUntil(entered.is_set)
    try:
        if action == "task_cancel":
            window._Task_Cancel()
            window.import_dialog.reject()
        elif action == "dialog_reject":
            window.import_dialog.reject()
        else:
            window.import_dialog.Folder_Set(path_b)
            window.import_dialog._FolderSearch_Request()
    finally:
        release.set()
        finish(qtbot, window)
    print(f"{action}: published={published}, visible={window.import_dialog.isVisible()}, folder={window.import_dialog.folder_path_edit.text()}, errors={window.audit_errors}")
    assert published == [], "An obsolete/cancelled A result must not reach the current dialog"
    if action != "replace_request":
        assert window.import_dialog.isHidden()


def test_cancel_after_result_emit_before_gui_publication(qtbot, monkeypatch, window, tmp_path):
    entered, release, emitted = threading.Event(), threading.Event(), threading.Event()
    def scan(path):
        entered.set()
        assert release.wait(5)
        return TaskDirectoryDiscovery(path, (), (), 0, 0, False)
    monkeypatch.setattr(window._log_open_coordinator.scanner, "Scan", scan)
    published = []
    original = window.import_dialog.PairDiscovery_Set
    def publish(discovery):
        published.append(discovery.selected_path)
        original(discovery)
    monkeypatch.setattr(window.import_dialog, "PairDiscovery_Set", publish)
    window.import_dialog.Folder_Set(tmp_path)
    window.import_dialog.open()
    window.import_dialog._FolderSearch_Request()
    qtbot.waitUntil(entered.is_set)
    worker = window._active_worker
    worker.signals.result.connect(lambda result: emitted.set(), Qt.ConnectionType.DirectConnection)
    try:
        release.set()
        # Blocking Event wait deliberately withholds the GUI event loop; the real
        # worker emits result into Qt's queue, before the real UI slot can run.
        assert emitted.wait(5), "Worker must have emitted a real queued result"
        assert not published
        assert window._active_worker is worker
        window._Task_Cancel()
        window.import_dialog.reject()
    finally:
        release.set()
        finish(qtbot, window)
    print(f"post-emit cancellation: event={worker.context.cancellation_event.is_set()}, published={published}, visible={window.import_dialog.isVisible()}, status={window.status_label.text()}")
    assert published == [], "Cancellation before GUI publication must reject queued result"
    assert window.import_dialog.isHidden()
    assert window.status_label.text() == window._translator.Text_Get("status.task_cancelled")


@pytest.mark.parametrize("page", ["replay", "export"])
@pytest.mark.parametrize("outcome", ["cancel", "error"])
def test_real_start_updates_local_global_terminal(qtbot, monkeypatch, window, tmp_path, page, outcome):
    entered, release = threading.Event(), threading.Event()
    def work(ctx):
        ctx.Progress_Report(.25, f"{page}.running")
        entered.set()
        assert release.wait(5)
        ctx.Cancel_RaiseIfRequested()
        raise ValueError("audit_terminal_error")
    surface = window.replay_page if page == "replay" else window.export_dialog
    surface.result_label.setText(window._translator.Text_Get(f"{page}.running"))
    window._dataset = object()
    if page == "replay":
        plugin = window._registry.Algorithm_Get("silverstar.algorithm.pure_ins")
        monkeypatch.setattr(plugin, "run", lambda dataset, request, context: work(context))
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
    else:
        monkeypatch.setattr(FlightExporter, "export", lambda self, *args, context, **kw: work(context))
        window._Export_Start(tmp_path / "output", ExportOptions())
    qtbot.waitUntil(entered.is_set)
    try:
        if outcome == "cancel":
            window._Task_Cancel()
    finally:
        release.set()
        finish(qtbot, window)
    expected = window._translator.Text_Get("status.task_cancelled" if outcome == "cancel" else "status.failed")
    assert window.status_label.text() == expected
    assert surface.result_label.text() == (expected if outcome == "cancel" else "audit_terminal_error")
    assert window._worker_cancel_callback is None


def test_declining_close_keeps_worker_running(qtbot, monkeypatch, window):
    entered, release = threading.Event(), threading.Event()
    results = []
    def work(ctx):
        entered.set()
        assert release.wait(5)
        ctx.Cancel_RaiseIfRequested()
        return "continued"
    worker = FunctionWorker(work)
    window._Task_Start(worker, results.append, window.audit_errors.append)
    qtbot.waitUntil(entered.is_set)
    window._project_dirty = True
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    event = QCloseEvent()
    try:
        window.closeEvent(event)
        assert not event.isAccepted()
        assert not worker.context.cancellation_event.is_set()
    finally:
        release.set()
        finish(qtbot, window)
    assert results == ["continued"]
