import json
from pathlib import Path

import pytest

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.path_preferences import PathPreferences
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.ui.dialogs.new_project import NewProjectWizard


def test_json_preferences_and_invalid_fallback(tmp_path):
    store = PathPreferences(WorkspacePolicy(tmp_path), tmp_path / ".fccg/path_preferences.json")
    assert store.DefaultProjectRoot_Get() is None
    root = tmp_path / "中文工程 Space"
    root.mkdir()
    store.DefaultProjectRoot_Set(root)
    assert store.DefaultProjectRoot_Get() == root
    assert json.loads(store.path.read_text(encoding="utf-8"))["schema_version"] == 1
    for text in ("{", "[]", '{"schema_version":1,"default_project_root":null}',
                 '{"schema_version":1,"default_project_root":"missing"}'):
        store.path.write_text(text, encoding="utf-8")
        assert store.DefaultProjectRoot_Get() is None


def test_wizard_auto_name_manual_and_browse(qapp, tmp_path, monkeypatch):
    wizard = NewProjectWizard(Translator("zh_CN"), default_root=tmp_path)
    form = wizard.identity_page
    form.name_edit.setText("试验 一")
    assert Path(form.output_edit.text()) == tmp_path / "试验 一"
    form.name_edit.setText("试验 二")
    assert Path(form.output_edit.text()) == tmp_path / "试验 二"
    custom = tmp_path / "自选"
    custom.mkdir()
    form.output_edit.setText(str(custom))
    form.output_edit.textEdited.emit(str(custom))
    form.name_edit.setText("新名称")
    assert Path(form.output_edit.text()) == custom
    calls = []
    def select(*args):
        calls.append(args[2])
        return str(tmp_path)
    monkeypatch.setattr("silverstar_fccg.ui.dialogs.new_project.QFileDialog.getExistingDirectory", select)
    form._Output_Browse()
    form.name_edit.setText("再次修改")
    assert Path(calls[0]) == custom
    assert Path(wizard.WizardData_Get()["output_directory"]) == tmp_path
    wizard.close()

def test_project_dialog_roots_names_and_unrelated_dialogs(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog

    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.ui.main_window import MainWindow

    window = MainWindow(SettingsStore(tmp_path / "settings.ini"))
    root = tmp_path / "中文工程 Space"
    root.mkdir()
    store = window._path_preferences
    store.DefaultProjectRoot_Set(root)
    preferences_before = store.path.read_bytes()
    window._model = window._service.ProjectDraft_Create("SS_TEST_试验")
    model_before = window._model.Dictionary_Get()
    calls = []

    def open_file(*args, **kwargs):
        calls.append(args)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", open_file)
    try:
        window._Project_OpenDialog()
        assert Path(calls.pop()[2]) == root

        def save_directory(dialog):
            assert Path(dialog.directory().absolutePath()) == root
            assert dialog.fileMode() == QFileDialog.FileMode.Directory
            assert dialog.selectedFiles() == [str(root / window._model.identity.name).replace("\\", "/")]
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QFileDialog, "exec", save_directory)
        window._Project_SaveAs()
        # Existing same-name destination must not change the initial browsing directory.
        (root / window._model.identity.name).mkdir()
        window._Project_SaveAs()

        def new_project(wizard):
            wizard.identity_page.name_edit.setText(window._model.identity.name)
            assert Path(wizard.WizardData_Get()["output_directory"]) == root / window._model.identity.name
            wizard.identity_page._Output_Browse()
            return QDialog.DialogCode.Rejected

        def browse(*args):
            assert Path(args[2]) == root
            return ""

        monkeypatch.setattr(QFileDialog, "getExistingDirectory", browse)
        monkeypatch.setattr(NewProjectWizard, "exec", new_project)
        window._NewProject_Show()
        window._PluginInstall_Dialog()
        assert Path(calls.pop()[2]) == window._service.workspace_root
        assert not window._ToolchainBrowse("compiler")
        assert len(calls.pop()) == 2  # No project-root override for executable browsing.
        assert store.path.read_bytes() == preferences_before
        assert window._model.Dictionary_Get() == model_before
        assert window._project_root is None
        assert not (root / "SilverStar.ssproject").exists()

        # Invalid preference must also flow through the actual Open/Save As entry points.
        store.path.write_text("{", encoding="utf-8")
        expected = store.DefaultProjectRoot_EffectiveGet()
        window._Project_OpenDialog()
        assert Path(calls.pop()[2]) == expected

        def fallback_save(dialog):
            assert Path(dialog.directory().absolutePath()) == expected
            assert Path(dialog.selectedFiles()[0]).name == window._model.identity.name
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(QFileDialog, "exec", fallback_save)
        window._Project_SaveAs()
    finally:
        window.close()
        qapp.processEvents()

@pytest.mark.parametrize("preference", ["absent", "empty", "malformed", "deleted", "file", "drive", "relative"])
def test_effective_root_falls_back_without_creating_paths(tmp_path, monkeypatch, preference):
    home = tmp_path / "Home"
    documents = home / "Documents"
    documents.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    store = PathPreferences(WorkspacePolicy(tmp_path), tmp_path / ".fccg/path_preferences.json")
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
            value = {"empty": "", "drive": str(Path(missing_drive) / "Projects"), "relative": "Projects"}.get(preference)
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
