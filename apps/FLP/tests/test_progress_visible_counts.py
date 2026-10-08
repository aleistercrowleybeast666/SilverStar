from threading import Event

from silverstar_flp.ui.workers import FunctionWorker
from tests.test_project_stage_progress_gui import window, private_settings


def test_quantified_progress_keeps_visible_percentage_and_work_count(window, qtbot):
    release = Event()
    def work(context):
        context.Progress_Report(.096, 'progress.artifact.records|9000|20000')
        assert release.wait(5)
    worker = FunctionWorker(work)
    worker.is_staged_io = True
    try:
        window._Task_Start(worker, lambda result: True, window.test_errors.append)
        qtbot.waitUntil(lambda: window.progress_bar.value() == 96, timeout=3000)
        assert '%' in window.progress_bar.text()
        assert '9,000' in window.status_label.text()
        assert '20,000' in window.status_label.text()
    finally:
        release.set()
        qtbot.waitUntil(lambda: window._active_worker is None, timeout=5000)
