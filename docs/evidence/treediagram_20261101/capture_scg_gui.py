"""Offscreen Qt visual review at an explicit scale; no desktop/hardware claim."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import re

REPO = Path(__file__).resolve().parents[3]
SCG = REPO / 'apps/SCG'
sys.path.insert(0, str(SCG / 'src'))
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox, QPushButton
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.ui.main_window import MainWindow

scale = os.environ['QT_SCALE_FACTOR']
tag = str(round(float(scale) * 100))
revision = sys.argv[1] if len(sys.argv) == 2 else ''
assert not revision or re.fullmatch(r'v[1-9][0-9]*', revision)
suffix = tag + ('-' + revision if revision else '')
output = Path(__file__).parent / ('gui-offscreen-' + suffix)
output.mkdir(exist_ok=False)
work = REPO / '.work/0.1.3-treediagram-20261101/silverstar' / ('gui-' + suffix)
work.mkdir(exist_ok=False)
app = QApplication([])
for name in ('msyh.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / name))
app.setFont(QFont('Microsoft YaHei', 9))
service = FccgService(SCG)
service.policy = WorkspacePolicy(work)
window = MainWindow(SettingsStore(work/'settings.ini'), service=service)
window._toolchain_checked = True
window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel
window._model = service.ReferenceProject_Create('TreeDiagram GUI review')
window._Project_Refresh()
window.Language_Apply('zh_CN' if tag == '125' else 'en_US')
window.Theme_Apply('light' if tag == '125' else 'dark')
window.resize(1320, 900)
window.show()
before = deepcopy(window._model.Dictionary_Get())
surfaces = []


def Flush():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    QTest.qWait(50)
    app.processEvents()


def Save(widget, name):
    Flush()
    image = widget.grab()
    assert image.save(str(output/(name+'.png')))
    surfaces.append(dict(name=name, logical_width=widget.width(), logical_height=widget.height(),
        pixels=[image.width(), image.height()], device_pixel_ratio=image.devicePixelRatio()))
    if isinstance(widget, QDialog):
        surfaces[-1]['layout_geometry'] = [dict(
            kind=type(widget.layout().itemAt(index).widget()).__name__,
            rect=list(widget.layout().itemAt(index).geometry().getRect()),
            minimum=list(widget.layout().itemAt(index).minimumSize().toTuple()))
            for index in range(widget.layout().count())]
        surfaces[-1]['button_boxes'] = [dict(visible=box.isVisible(),
            rect=list(box.geometry().getRect()), buttons=[dict(text=button.text(), visible=button.isVisible()) for button in box.buttons()])
            for box in widget.findChildren(QDialogButtonBox)]
        hit = widget.childAt(QPoint(widget.width()-80, widget.height()-35))
        surfaces[-1]['bottom_hit'] = type(hit).__name__ + ':' + hit.objectName() if hit else None


def Modal(button, name, edit=None):
    failures = []
    def During():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            if edit:
                edit(dialog)
            Save(dialog, name)
            dialog.reject()
        except BaseException as error:
            failures.append(str(error))
            if dialog:
                dialog.reject()
    QTimer.singleShot(0, During)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    Flush()
    assert not failures, failures
    assert window._model.Dictionary_Get() == before


for index, name in enumerate(('01-hardware', '02-workflow', '03-build')):
    window.navigation_list.setCurrentRow(index)
    Save(window, name)
window.navigation_list.setCurrentRow(0)


def RadioDraft(dialog):
    for combo, _power in dialog.endpoints.values():
        index = combo.findData(('silverstar.device.telemetry.sx1278', 'e32_400m20s'))
        assert index >= 0
        combo.setCurrentIndex(index)
    dialog.preset.setCurrentIndex(dialog.preset.findData('sx127x'))
    text = window._translator.Text_Get('radio.transaction.preset')
    next(button for button in dialog.findChildren(QPushButton) if button.text() == text).click()


Modal(window.hardware_workspace.link_button, '04-radio-private-draft', RadioDraft)
window.navigation_list.setCurrentRow(1)
Modal(window.workflow_page.stage_panel.cards['ascent'].findChild(QPushButton, 'phaseSelect'),
      '05-stage-condition-and-references')
window.workflow_page.coverage.Function_Select('ins')
Modal(window.workflow_page.function_buttons['parameters'], '06-single-ins-owner')
assert not any(editor._sections for editor in window.workflow_page.function_editors)
(output/'provenance.json').write_text(json.dumps(dict(platform=app.platformName(), scale_factor=scale,
    scope='Actual Qt widget renders and normal button/modal paths. Offscreen, not native desktop or hardware validation.',
    model_unchanged_after_all_cancel=True, shared_library_duplicate_function_forms=0,
    surfaces=surfaces), indent=2), encoding='utf-8')
window._project_dirty = False
window.close()
Flush()
print(output)
