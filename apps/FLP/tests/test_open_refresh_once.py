def test_project_reopen_renders_pages_once(qtbot, tmp_path, monkeypatch):
    from silverstar_flp.ui.main_window import MainWindow
    from tests.test_project_artifacts import test_gui_reopen_restores_every_run_and_two_sources_without_replay
    counts = {}
    original = MainWindow._Pages_Refresh

    def refresh(window):
        counts[id(window)] = counts.get(id(window), 0) + 1
        return original(window)

    monkeypatch.setattr(MainWindow, '_Pages_Refresh', refresh)
    test_gui_reopen_restores_every_run_and_two_sources_without_replay(qtbot, tmp_path, monkeypatch)
    # The last window is the production reopen; the first also has deliberate
    # interactive source changes. It must restore both saved sources and arrays.
    assert list(counts.values())[-1] == 1
