"""Startup visibility and theme regressions, including the real modal entry."""
from copy import deepcopy
from pathlib import Path
import traceback
import json
import os

from PySide6.QtCore import QObject, QEvent, QTimer, Qt, QCoreApplication
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QDialog

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
from silverstar_fccg.ui.theme import ThemeTokens_Get

APP = Path(__file__).resolve().parents[1]


class TopLevelShowProbe(QObject):
    def __init__(self):
        super().__init__()
        self.unexpected = []
        self.observed = []
        self.expect_stage_dialog = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            parents = []
            parent = obj.parent()
            while parent is not None:
                parents.append({'class': type(parent).__name__, 'name': parent.objectName()})
                parent = parent.parent()
            self.observed.append({'class': type(obj).__name__, 'name': obj.objectName(),
                                  'parent_chain': parents, 'title': obj.windowTitle()})
            expected = isinstance(obj, MainWindow) or (
                self.expect_stage_dialog and isinstance(obj, MissionStageTransactionDialog))
            if not expected:
                self.unexpected.append((type(obj).__name__, obj.objectName(),
                    type(obj.parent()).__name__, ''.join(traceback.format_stack())))
        return False


def test_startup_refresh_browse_and_cancel_never_show_parentless_controls(tmp_path, qapp):
    probe = TopLevelShowProbe()
    qapp.installEventFilter(probe)
    window = None
    try:
        service = FccgService(APP)
        window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
        window._toolchain_checked = True
        window._model = service.ReferenceProject_Create('Startup probe')
        window._Project_Refresh()
        before = deepcopy(window._model.Dictionary_Get())
        window.show()
        for theme in ('dark', 'light'):
            window.Theme_Apply(theme)
            for language in ('en_US', 'zh_CN'):
                window.Language_Apply(language)
                for page in range(3):
                    window.navigation_list.setCurrentRow(page)
                    qapp.processEvents()
                    evidence = os.environ.get('SILVERSTAR_GUI_EVIDENCE_DIR')
                    if evidence and language == 'zh_CN' and theme == 'light':
                        destination = Path(evidence)
                        destination.mkdir(parents=True, exist_ok=True)
                        window.grab().save(str(destination / f'{qapp.platformName()}-zh_CN-light-page{page + 1}.png'))
                window.navigation_list.setCurrentRow(1)
                evidence = os.environ.get('SILVERSTAR_GUI_EVIDENCE_DIR')
                if evidence:
                    destination = Path(evidence)
                    destination.mkdir(parents=True, exist_ok=True)
                    window.grab().save(str(destination / f'{qapp.platformName()}-{language}-{theme}.png'))
                for _repeat in range(2):
                    def close_dialog():
                        dialog = QApplication.activeModalWidget()
                        if evidence and language == 'zh_CN' and theme == 'light' and _repeat == 0:
                            dialog.grab().save(str(Path(evidence) / f'{qapp.platformName()}-zh_CN-light-stage-dialog.png'))
                        dialog.reject()
                    probe.expect_stage_dialog = True
                    QTimer.singleShot(0, close_dialog)
                    first = next(iter(window.workflow_page.stage_panel.cards.values()))
                    QTest.mouseClick(first.findChild(QPushButton, 'phaseSelect'), Qt.MouseButton.LeftButton)
                    probe.expect_stage_dialog = False
                    qapp.processEvents()
        assert window._model.Dictionary_Get() == before
        assert not probe.unexpected, probe.unexpected
    finally:
        evidence = os.environ.get('SILVERSTAR_GUI_EVIDENCE_DIR')
        if evidence:
            Path(evidence, 'top-level-events.json').write_text(json.dumps({
                'platform': qapp.platformName(), 'observed': probe.observed,
                'unexpected': probe.unexpected}, ensure_ascii=False, indent=2), encoding='utf-8')
        qapp.removeEventFilter(probe)
        if window is not None:
            window._project_dirty = False
            window.close()


def test_theme_api_selection_palette_and_persistence_stay_in_sync(tmp_path, qapp):
    settings = SettingsStore(tmp_path / 'theme.ini')
    window = MainWindow(settings, service=FccgService(APP))
    window._toolchain_checked = True
    try:
        for theme in ('dark', 'light', 'dark', 'light'):
            window.Theme_Apply(theme)
            assert window.theme_combo.currentData() == theme
            assert window._theme == theme
            assert qapp.palette().color(QPalette.ColorRole.Window).name() == ThemeTokens_Get(theme).surface.lower()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qapp.processEvents()
            window.Language_Apply('en_US' if theme == 'light' else 'zh_CN')
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            qapp.processEvents()
            assert window.theme_combo.currentData() == theme
        window.theme_combo.setCurrentIndex(window.theme_combo.findData('dark'))
        assert window._theme == 'dark'
        assert qapp.palette().color(QPalette.ColorRole.Window).name() == ThemeTokens_Get('dark').surface.lower()
    finally:
        window._project_dirty = False
        window.close()
