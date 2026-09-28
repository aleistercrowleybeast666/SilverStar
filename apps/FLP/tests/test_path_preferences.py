import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.path_preferences import ExportDirectory_Default, PathPreferences
from silverstar_flp.core.project import ProjectDocument
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.new_project import NewProjectDialog
from silverstar_flp.ui.pages.export_settings import ExportDialog, ImportDialog


def test_json_roundtrip_corruption_and_nonexistent_root(tmp_path):
    store = PathPreferences(tmp_path / "settings/path_preferences.json")
    assert store.DefaultProjectRoot_Get() is None
    root = tmp_path / "中文 空格"
    root.mkdir()
    store.DefaultProjectRoot_Set(root)
    assert store.DefaultProjectRoot_Get() == root
    assert "中文" in store.path.read_text(encoding="utf-8")
    for document in (
        "{",
        "null",
        "[]",
        json.dumps({"schema_version": 1, "default_project_root": str(root / "missing")}),
    ):
        store.path.write_text(document, encoding="utf-8")
        assert store.DefaultProjectRoot_Get() is None
    assert not (root / "missing").exists()


def test_auto_directory_custom_edit_and_browse(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    dialog = NewProjectDialog(Translator("zh_CN"), tmp_path)
    dialog.name_edit.setText("试验 一")
    assert dialog.Path_Get() == tmp_path / "试验 一" / "试验 一.ssflp"
    dialog.name_edit.setText("二.ssflp")
    assert dialog.Path_Get() == tmp_path / "二" / "二.ssflp"
    custom = tmp_path / "custom"
    custom.mkdir()
    dialog.directory_edit.setText(str(custom))
    dialog.directory_edit.textEdited.emit(str(custom))
    dialog.name_edit.setText("三")
    assert dialog.Path_Get() == custom / "三.ssflp"
    calls = []

    def select(*args):
        calls.append(args[2])
        return str(tmp_path)

    monkeypatch.setattr("silverstar_flp.ui.new_project.QFileDialog.getExistingDirectory", select)
    dialog._Directory_Select()
    dialog.name_edit.setText("四")
    assert Path(calls[0]) == custom
    assert dialog.Path_Get() == tmp_path / "四.ssflp"
    app.processEvents()
    dialog.close()


def test_import_follows_current_project_and_manual_mode_survives_translation(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = PathPreferences(tmp_path / "preferences.json")
    store.DefaultProjectRoot_Set(tmp_path)
    window = MainWindow(builtin_registry(), path_preferences=store)
    assert window.import_dialog.source_type_combo.currentData() == "folder_search"
    assert window._ImportDirectory_Get() == tmp_path
    for name in ("工程 一", "工程 二"):
        directory = tmp_path / name
        directory.mkdir()
        window._project = ProjectDocument(project_path=directory / (name + ".ssflp"))
        window._ImportDialog_Show()
        assert Path(window.import_dialog.folder_path_edit.text()) == directory
        window.import_dialog.reject()
    dialog = ImportDialog(Translator("en_US"))
    dialog.source_type_combo.setCurrentIndex(dialog.source_type_combo.findData("manual"))
    dialog.Language_Apply(Translator("zh_CN"))
    assert dialog.source_type_combo.currentData() == "manual"
    window._Project_SetDirty(False)
    window.close()
    app.processEvents()


def test_result_names_collision_and_manual_destination(tmp_path):
    app = QApplication.instance() or QApplication([])
    for name, expected in (
        ("SS0005.BIN", "Result_SS0005"),
        ("中文 日志 (1).sSlOg", "Result_中文 日志 (1)"),
        ("bad?name.BIN", "Result_bad_name"),
    ):
        result = ExportDirectory_Default(tmp_path / name)
        assert result.name == expected
        result.mkdir()
        sentinel = result / "existing.txt"
        sentinel.write_text("preserve")
        assert ExportDirectory_Default(tmp_path / name).name == expected + "_2"
        assert sentinel.read_text() == "preserve"
    dialog = ExportDialog(Translator("en_US"))
    dialog.OutputDirectory_Set(tmp_path / "automatic")
    dialog.folder_edit.setText(str(tmp_path / "manual"))
    dialog.folder_edit.textEdited.emit(dialog.folder_edit.text())
    dialog.OutputDirectory_Set(tmp_path / "next")
    assert Path(dialog.folder_edit.text()) == tmp_path / "manual"
    dialog.close()
    app.processEvents()

def test_project_dialogs_use_root_but_save_import_export_keep_project_path(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog

    from silverstar_flp.core.project import Project_ToDict

    app = QApplication.instance() or QApplication([])
    store = PathPreferences(tmp_path / "preferences.json")
    root = tmp_path / "默认目录 Space"
    root.mkdir()
    store.DefaultProjectRoot_Set(root)
    other = tmp_path / "Other"
    other.mkdir()
    original = other / "Flight_试验.ssflp"
    original.write_text("existing project sentinel")
    window = MainWindow(builtin_registry(), path_preferences=store)
    window._project = ProjectDocument(project_path=original, notes="unchanged")
    before = Project_ToDict(window._project)
    preferences_before = store.path.read_bytes()
    opened = []
    suggested = []
    saved = []

    def open_file(*args, **kwargs):
        opened.append(Path(args[2]))
        return str(original), ""

    def save_file(*args, **kwargs):
        suggested.append(Path(args[2]))
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", open_file)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_file)
    selected_projects = []
    monkeypatch.setattr(window, "_Project_Open", selected_projects.append)
    monkeypatch.setattr(window, "_Project_Write", saved.append)
    try:
        window._ProjectDialog_Open()
        assert opened == [root]
        assert selected_projects == [original]
        window._Project_SaveAs()
        assert suggested.pop() == root / original.name
        window._Project_Save()
        assert saved == [original]
        assert not suggested
        assert window._ImportDirectory_Get() == other
        assert ExportDirectory_Default(other / "SS0005.BIN", original) == other / "Result_SS0005"
        assert Project_ToDict(window._project) == before

        def new_project(dialog):
            assert Path(dialog.directory_edit.text()) == root
            dialog.name_edit.setText("新工程")
            assert dialog.Path_Get() == root / "新工程" / "新工程.ssflp"
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(NewProjectDialog, "exec", new_project)
        window._Project_New()
        assert not (root / "新工程").exists()
        window._project = ProjectDocument()
        window._Project_Save()
        assert suggested.pop() == root / "flight.ssflp"
        assert store.path.read_bytes() == preferences_before
        assert original.read_text() == "existing project sentinel"

        # First Save must retain the existing overwrite guard used by Save As.
        confirmations = []
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(original), "")
        )
        monkeypatch.setattr(
            window, "_Overwrite_Confirm", lambda path: (confirmations.append(path), False)[1]
        )
        window._Project_Save()
        window._Project_SaveAs()
        assert confirmations == [original, original]
        assert saved == [original]  # Only the ordinary Save of the already-open project.
        assert original.read_text() == "existing project sentinel"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", save_file)

        store.path.write_text("{", encoding="utf-8")
        expected = store.DefaultProjectRoot_EffectiveGet()
        window._ProjectDialog_Open()
        assert opened[-1] == expected
        window._Project_SaveAs()
        assert suggested.pop() == expected / "flight.ssflp"
        assert store.path.read_text() == "{"
    finally:
        window._Project_SetDirty(False)
        window.close()
        app.processEvents()

@pytest.mark.parametrize(
    "preference", ["absent", "empty", "malformed", "deleted", "file", "drive", "relative"]
)
def test_effective_root_falls_back_without_creating_paths(tmp_path, monkeypatch, preference):
    home = tmp_path / "Home"
    documents = home / "Documents"
    documents.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    store = PathPreferences(tmp_path / "settings/path_preferences.json")
    root = tmp_path / "SavedRoot"
    root.mkdir()
    if preference != "absent":
        store.DefaultProjectRoot_Set(root)
        if preference == "deleted":
            root.rmdir()
        elif preference == "file":
            root.rmdir()
            root.write_text("not a directory")
        else:
            missing_drive = next(
                (f"{letter}:/" for letter in "ZYXWVUT" if not Path(f"{letter}:/").is_dir()),
                str(tmp_path / "unmounted"),
            )
            value = {
                "empty": "", "drive": str(Path(missing_drive) / "Projects"), "relative": "Projects",
            }.get(preference)
            text = "{" if preference == "malformed" else json.dumps(
                {"schema_version": 1, "default_project_root": value}
            )
            store.path.write_text(text, encoding="utf-8")
    before = store.path.read_bytes() if store.path.exists() else None
    assert store.DefaultProjectRoot_EffectiveGet() == documents
    documents.rmdir()
    assert store.DefaultProjectRoot_EffectiveGet() == home
    home.rmdir()
    monkeypatch.chdir(tmp_path)
    assert store.DefaultProjectRoot_EffectiveGet() == tmp_path
    assert not home.exists()
    assert not (tmp_path / "Projects").exists()
    assert (store.path.read_bytes() if store.path.exists() else None) == before
