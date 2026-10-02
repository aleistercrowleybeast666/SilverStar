from threading import Event
import time

import pytest

from test_scg_ui_metadata_hotfix import window


def _Wait(qapp, condition):
    deadline = time.monotonic() + 10
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert condition(), "bounded worker wait expired"


@pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
def test_unknown_job_uses_real_phase_events_until_actual_outcome(qapp, window, outcome):
    advance = [Event() for _ in range(3)]
    results, errors = [], []

    def run(context):
        assert advance[0].wait(10)
        context.Line_Report("FCCG_PROGRESS|CHECK|BEGIN|1|2|first_phase")
        context.Line_Report("FCCG_PROGRESS|CHECK|DONE|1|2|first_phase")
        assert advance[1].wait(10)
        context.Line_Report("FCCG_PROGRESS|CHECK|DONE|2|2|last_phase")
        assert advance[2].wait(10)
        context.Cancel_RaiseIfRequested()
        if outcome == "error":
            raise ValueError("expected test failure")
        return "done"

    try:
        assert window.Task_Run(run, results.append, errors.append)
        assert window.progress_bar.minimum() == window.progress_bar.maximum() == 0
        advance[0].set()
        _Wait(qapp, lambda: window.progress_bar.maximum() == 1000 and
              window.progress_bar.value() == 500)
        assert window._active_worker is not None
        assert "first phase" in window.status_label.text()
        advance[1].set()
        _Wait(qapp, lambda: window.progress_bar.value() == 999)
        assert window._active_worker is not None
        if outcome == "cancelled":
            window._Task_Cancel()
        advance[2].set()
        _Wait(qapp, lambda: window._active_worker is None)
        assert window.progress_bar.value() == (1000 if outcome == "success" else 999)
        assert window.progress_bar.property("taskState") == outcome
        assert results == (["done"] if outcome == "success" else [])
        assert bool(errors) is (outcome == "error")
    finally:
        for event in advance:
            event.set()
        _Wait(qapp, lambda: window._active_worker is None)
