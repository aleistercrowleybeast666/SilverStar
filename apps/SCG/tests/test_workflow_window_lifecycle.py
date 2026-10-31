"""Native/offscreen lifecycle coverage using real actions and the worker pool."""
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.dialogs.new_project import NewProjectWizard
from silverstar_fccg.ui.main_window import MainWindow
from test_three_workspace_workflow import _Capsule_Click, _Events_Flush, _Snapshot
from test_workflow_startup_windows import TopLevelShowProbe

APP = Path(__file__).resolve().parents[1]


class LifecycleShowProbe(TopLevelShowProbe):
    expect_new_dialog = False

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Show and self.expect_new_dialog
                and isinstance(obj, NewProjectWizard) and obj.isWindow()):
            self.observed.append({'class': type(obj).__name__, 'name': obj.objectName(),
                                  'parent': type(obj.parent()).__name__,
                                  'explicit_action': 'new_project'})
            return False
        return super().eventFilter(obj, event)


def test_new_open_resize_escape_close_and_worker_completion_show_only_owned_windows(tmp_path, qapp):
    probe = LifecycleShowProbe()
    qapp.installEventFilter(probe)
    service = FccgService(APP)
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._toolchain_checked = True
    project = tmp_path / 'NewMission'
    errors = []
    window._Error_Show = errors.append
    try:
        window.Theme_Apply('light')
        window.show()
        outcomes = []

        def Create():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, NewProjectWizard)
                dialog.identity_page.name_edit.setText('NewMission')
                dialog.identity_page.output_edit.setText(str(project))
                button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
                assert button.isEnabled()
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                outcomes.append(True)
            except BaseException as error:
                outcomes.append(error)
                if dialog is not None:
                    dialog.reject()

        probe.expect_new_dialog = True
        QTimer.singleShot(0, Create)
        window.new_action.trigger()
        probe.expect_new_dialog = False
        assert outcomes == [True], outcomes
        descriptor = project / 'SilverStar.ssproject'
        assert descriptor.is_file() and not errors
        source_hash = hashlib.sha256(descriptor.read_bytes()).hexdigest()
        before = _Snapshot(window._model)
        for width in (900, 1280):
            window.resize(width, 720)
            for page in range(3):
                window.navigation_list.setCurrentRow(page)
                _Events_Flush(qapp)
        window._Project_Open(project)
        assert _Snapshot(window._model) == before and not errors
        window.navigation_list.setCurrentRow(1)
        probe.expect_stage_dialog = True
        _Capsule_Click(window, 'ascent', lambda dialog: QTest.keyClick(dialog, Qt.Key.Key_Escape))
        _Capsule_Click(window, 'ascent', lambda dialog: dialog.close())
        probe.expect_stage_dialog = False
        completed = []

        def Complete(model):
            completed.append(_Snapshot(model))
            window._Project_Refresh()

        assert window.Task_Run(lambda _context: service.Project_Open(project), Complete)
        for _attempt in range(1500):
            _Events_Flush(qapp)
            if window._active_worker is None:
                break
            QTest.qWait(10)
        assert window._active_worker is None
        assert completed == [before] and not errors
        assert _Snapshot(window._model) == before
        assert hashlib.sha256(descriptor.read_bytes()).hexdigest() == source_hash
        assert not probe.unexpected, probe.unexpected
    finally:
        evidence = os.environ.get('SILVERSTAR_GUI_EVIDENCE_DIR')
        if evidence:
            destination = Path(evidence)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'lifecycle-top-level-events.json').write_text(json.dumps({
                'platform': qapp.platformName(), 'scale_factor': os.environ.get('QT_SCALE_FACTOR', 'default'),
                'observed': probe.observed, 'unexpected': probe.unexpected,
                'scope': 'Real new/open actions, resize, Esc/close modal and project-read worker; no device operations.'
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        qapp.removeEventFilter(probe)
        window._thread_pool.waitForDone(15000)
        window._project_dirty = False
        window.close()
