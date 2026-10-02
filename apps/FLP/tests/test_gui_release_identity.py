from pathlib import Path

from PySide6.QtWidgets import QApplication

from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow


def test_cancel_busy_and_failed_import_preserve_published_root(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    original = tmp_path / "original"
    window._silverstar_project_root = original
    errors = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: False)
    window.LogPair_Open(tmp_path / "new.BIN", tmp_path / "new.ssdecoder")
    assert window._silverstar_project_root == original
    window.SilverStarProjectRoot_Open(tmp_path / "invalid")
    assert window._silverstar_project_root == original
    monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: True)
    window.SilverStarProjectRoot_Open(tmp_path / "invalid")
    assert errors[-1] == "silverstar_project_root_invalid"
    window._active_worker = object()
    window.LogPair_Open(tmp_path / "new.BIN", tmp_path / "new.ssdecoder")
    window.SilverStarProjectRoot_Open(tmp_path / "invalid")
    window._Project_New()
    assert errors[-3:] == ["another_background_task_is_running"] * 3
    assert window._silverstar_project_root == original
    window._active_worker = None
    window.close()
    app.processEvents()


def test_root_and_analysis_session_identity_survives_resize(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(builtin_registry())
    root = tmp_path / "已保存的工程_α"
    window._silverstar_project_root = root
    window._ProjectHeader_Refresh()
    assert root.name in window.project_name_label.toolTip()
    assert "分析会话未保存" in window.project_name_label.toolTip()
    window._project.project_path = tmp_path / "分析会话.ssflp"
    window._Project_SetDirty(True)
    window.resize(780, 600)
    app.processEvents()
    assert "分析会话 *" in window.project_name_label.toolTip()
    assert str(window._project.project_path.resolve()) in window.project_name_label.toolTip()
    window._Project_SetDirty(False)
    window.close()
    app.processEvents()
