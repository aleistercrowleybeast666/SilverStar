"""Small offscreen GUI audit through production buttons, never an MCU test."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

SCG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCG / 'src'))


def Capture_Main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--language', choices=('zh_CN', 'en_US'), default='zh_CN')
    parser.add_argument('--theme', choices=('light', 'dark'), default='light')
    parser.add_argument('--scale', choices=('1.25', '1.5'), default='1.25')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_SCALE_FACTOR'] = args.scale
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox, QPushButton
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.project.mission_process import MissionProcess_FirmwareDefault
    from silverstar_fccg.ui.main_window import MainWindow

    app = QApplication([])
    for name in ('msyh.ttc', 'segoeui.ttf'):
        font = Path('C:/Windows/Fonts') / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Microsoft YaHei', 9))
    window = MainWindow(SettingsStore(args.output / 'settings.ini'),
                        language=args.language, theme=args.theme)
    window._toolchain_checked = True
    window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
    window.resize(980, 700)
    window.show()
    records = []

    def Save(widget, name):
        app.processEvents()
        image = widget.grab()
        path = args.output / (name + '.png')
        assert image.save(str(path))
        buttons = [button for box in widget.findChildren(QDialogButtonBox)
                   for button in box.buttons() if button.isVisible()]
        assert all(widget.rect().contains(button.mapTo(widget, button.rect().bottomRight()))
                   for button in buttons)
        records.append({'name': name, 'logical_size': [widget.width(), widget.height()],
                        'pixel_size': [image.width(), image.height()],
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'visible_footer_buttons': [button.text() for button in buttons]})

    initial = deepcopy(window._model.Dictionary_Get())
    for index, name in enumerate(('hardware', 'workflow', 'generation')):
        window.navigation_list.setCurrentRow(index)
        Save(window, name)
    assert initial == window._model.Dictionary_Get()
    assert not window.board_hardware_page.generate_button.isEnabled()
    assert not window.ground_target_page.generate_button.isEnabled()
    window._model = window._service.ReferenceProject_Create('GUI audit, software only')
    window._model.mission_process = MissionProcess_FirmwareDefault(
        acceleration_detection=True, recovery=True, recovery_target='parachute_pyro0')
    window._Project_Refresh()
    window.navigation_list.setCurrentRow(1)
    reference = deepcopy(window._model.Dictionary_Get())
    outcomes = []

    def Dialog_Capture(name):
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog is not None
            if name == 'stage':
                assert dialog._stage_only and dialog._function_id is None
                actions = dialog.stage_editor.actions_widget
                assert actions.isVisible() and actions.parentWidget().layout().indexOf(actions) >= 0
            dialog.resize(720, 620)
            Save(dialog, name)
            outcomes.append(None)
        except BaseException as error:
            outcomes.append(error)
        finally:
            if dialog is not None:
                QTest.keyClick(dialog, Qt.Key.Key_Escape)

    QTimer.singleShot(0, lambda: Dialog_Capture('stage'))
    button = window.workflow_page.stage_panel.cards['deploy'].findChild(QPushButton, 'phaseSelect')
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    window.workflow_page.coverage.Function_Select('ins')
    QTimer.singleShot(0, lambda: Dialog_Capture('shared-ins'))
    QTest.mouseClick(window.workflow_page.function_buttons['parameters'], Qt.MouseButton.LeftButton)
    assert len(outcomes) == 2
    for error in outcomes:
        if error is not None:
            raise error
    assert reference == window._model.Dictionary_Get()
    (args.output / 'capture.json').write_text(json.dumps({
        'mode': 'Qt offscreen; production capsule/function buttons; not native desktop evidence',
        'language': args.language, 'theme': args.theme, 'scale': args.scale,
        'model_unchanged': True, 'surfaces': records}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    window._project_dirty = False
    window.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(Capture_Main())
