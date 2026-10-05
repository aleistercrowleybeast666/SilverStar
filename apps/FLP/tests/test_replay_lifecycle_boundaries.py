"""Synthetic tiny-array and gated-worker lifecycle tests, never flight evidence."""

import gc
import threading
import weakref
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.dataset import FlightDataset, TimeSeries
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.replay import ReplayPage


def tiny_dataset(name):
    return FlightDataset(Path(name), 0, {}, ParserDiagnostics(), {}, {})


def tiny_result():
    channels = {}
    for name, count in [
        ("attitude.q_nb", 4),
        ("navigation.position_enu", 3),
        ("navigation.velocity_enu", 3),
    ]:
        channels[name] = TimeSeries(
            np.array([1, 2], dtype=np.uint64),
            np.ones((2, count)),
            "1",
            name,
            "synthetic",
            np.array([True, True]),
        )
    return AlgorithmResult(
        "silverstar.algorithm.estimator.eskf15",
        "synthetic",
        "corrected_imu",
        {},
        ReplayFidelity.APPROXIMATE,
        (),
        (),
        channels,
        {"output_count": 2},
        "Offline",
    )


def test_store_clear_releases_arrays_when_no_other_owners():
    store = ReplayResultStore()
    result = tiny_result()
    reference = weakref.ref(result.channels["navigation.position_enu"].values)
    entry = store.Result_Add(result)
    assert entry.channels["navigation.position_enu"] is result.channels["navigation.position_enu"]
    del entry, result
    assert reference() is not None
    store.Clear()
    gc.collect()
    assert reference() is None


def test_successive_completed_runs_are_retained_without_copying_arrays():
    store = ReplayResultStore()
    references = []
    for _ in range(3):
        result = tiny_result()
        references.append(weakref.ref(result.channels["navigation.position_enu"].values))
        entry = store.Result_Add(result)
        assert (
            entry.channels["navigation.position_enu"] is result.channels["navigation.position_enu"]
        )
    del result, entry
    assert len(store.Entries_Get()) == 3
    assert all(reference() is not None for reference in references)
    store.Clear()
    gc.collect()
    assert all(reference() is None for reference in references)


def test_switching_dataset_releases_previous_replay_page_result(qtbot):
    """Desired behavior; reproduces a bounded stale-result reference on 34bbd38."""
    store = ReplayResultStore()
    page = ReplayPage(Translator("zh_CN"), builtin_registry())
    qtbot.addWidget(page)
    page.Dataset_Set(tiny_dataset("first"), store)
    result = tiny_result()
    reference = weakref.ref(result.channels["navigation.position_enu"].values)
    page.Result_Set(result)
    page.result_information_label.setToolTip("previous_result_warning")
    page.comparison_table.setRowCount(1)
    del result
    store.Clear()
    page.Dataset_Set(tiny_dataset("second"), store)
    assert page.result_label.text() == "—"
    assert page.result_information_label.text() == "—"
    assert page.result_information_label.toolTip() == ""
    assert page.comparison_table.rowCount() == 0
    page.Language_Apply(Translator("en_US"))
    assert page.result_information_label.text() == "—"
    gc.collect()
    assert store.Entries_Get() == ()
    stale_entry = page._last_entry is not None
    stale_result = page._last_result is not None
    retained_array = reference() is not None
    print(
        "After dataset switch: store entries=0, stale_entry=",
        stale_entry,
        ", stale_result=",
        stale_result,
        ", old ndarray alive=",
        retained_array,
    )
    # Cleanup also demonstrates that these two cache fields are sufficient owners.
    page._last_entry = None
    page._last_result = None
    gc.collect()
    assert reference() is None
    assert not stale_entry and not stale_result and not retained_array


def test_same_dataset_refresh_preserves_completed_history_and_last_result(qtbot):
    store = ReplayResultStore()
    page = ReplayPage(Translator("en_US"), builtin_registry())
    qtbot.addWidget(page)
    dataset = tiny_dataset("same")
    page.Dataset_Set(dataset, store)
    for _ in range(3):
        page.Result_Set(tiny_result())
    entry, result = page._last_entry, page._last_result
    information = page.result_information_label.text()
    page.Dataset_Set(dataset, store)
    assert len(store.Entries_Get()) == 3
    assert page._last_entry is entry and page._last_result is result
    assert page.result_information_label.text() == information


@pytest.mark.parametrize("state", ["active", "cancelled", "superseded"])
def test_task_result_publication_requires_current_uncancelled_worker(state):
    worker = SimpleNamespace(context=SimpleNamespace(cancellation_event=threading.Event()))
    owner = SimpleNamespace(_active_worker=worker)
    if state == "cancelled":
        worker.context.cancellation_event.set()
    elif state == "superseded":
        owner._active_worker = object()
    published = []
    MainWindow._Task_ResultPublish(owner, worker, "result", published.append)
    assert published == (["result"] if state == "active" else [])


@pytest.mark.parametrize("close_accepted", [False, True])
def test_repeat_cancel_close_and_switch_do_not_launch_a_second_worker(
    qtbot, monkeypatch, close_accepted
):
    registry = builtin_registry()
    window = MainWindow(registry)
    qtbot.addWidget(window)
    window._dataset = object()
    entered, release = threading.Event(), threading.Event()
    calls, errors, published = [], [], []
    plugin = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15")

    def gated(dataset, request, context):
        calls.append(plugin.metadata.plugin_id)
        entered.set()
        assert release.wait(5)
        context.Cancel_RaiseIfRequested()
        return "tiny-mock-result"

    monkeypatch.setattr(plugin, "run", gated)
    monkeypatch.setattr(window, "_Replay_ResultSet", published.append)
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    monkeypatch.setattr(window.replay_page, "Result_Error", errors.append)
    monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: close_accepted)
    try:
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        qtbot.waitUntil(entered.is_set, timeout=5000)
        first = window._active_worker
        assert not window.replay_page.controls_group.isEnabled()
        assert not window.replay_page.parameters_group.isEnabled()
        for _ in range(3):
            window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        window.Log_Open(Path("nonexistent.sslog"))
        window._Project_Open(Path("nonexistent.ssflp"))
        window._Project_New()
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted() == close_accepted
        assert first.context.cancellation_event.is_set() == close_accepted
        assert window._active_worker is first
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        assert calls == [plugin.metadata.plugin_id]
        window._Task_Cancel()
        assert window._active_worker is first
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        assert calls == [plugin.metadata.plugin_id]
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        assert published == []
        assert errors.count("another_background_task_is_running") == 8
        assert errors[-1] == window._translator.Text_Get("status.task_cancelled")
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        assert calls == [plugin.metadata.plugin_id] * 2
        assert published == ["tiny-mock-result"]
    finally:
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        window._project_dirty = False
        window._dataset = None
        monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: True)
        window.close()


@pytest.mark.parametrize("action", ["cancel", "accepted_close"])
def test_queued_replay_result_is_not_published_after_cancellation(qtbot, monkeypatch, action):
    """Desired behavior; exercises only the result-emitted / GUI-not-yet-serviced race."""
    registry = builtin_registry()
    window = MainWindow(registry)
    qtbot.addWidget(window)
    window._dataset = object()
    entered, release, emitted = threading.Event(), threading.Event(), threading.Event()
    plugin = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15")

    def gated(dataset, request, context):
        entered.set()
        assert release.wait(5)
        return tiny_result()

    monkeypatch.setattr(plugin, "run", gated)
    # Keep the real MainWindow -> ResultStore -> ReplayPage publication path;
    # omit only unrelated plot/data pages for this tiny lifecycle fixture.
    monkeypatch.setattr(window, "_Pages_Refresh", lambda: None)
    monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: True)
    try:
        window._Replay_Start(plugin.metadata.plugin_id, ReplayRequest())
        qtbot.waitUntil(entered.is_set, timeout=5000)
        worker = window._active_worker
        worker.signals.result.connect(lambda _: emitted.set(), Qt.ConnectionType.DirectConnection)
        release.set()
        # Withhold the GUI queue while waiting for the actual worker emission.
        assert emitted.wait(5)
        assert window._replay_store.Entries_Get() == ()
        if action == "cancel":
            window._Task_Cancel()
        else:
            event = QCloseEvent()
            window.closeEvent(event)
            assert event.isAccepted()
        assert worker.context.cancellation_event.is_set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        print(
            action,
            "after cancelled queued result: entries=",
            len(window._replay_store.Entries_Get()),
            ", status=",
            window.status_label.text(),
            ", active_worker=",
            window._active_worker,
        )
        assert window._replay_store.Entries_Get() == ()
    finally:
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
        window._project_dirty = False
        window._dataset = None
        window.close()
