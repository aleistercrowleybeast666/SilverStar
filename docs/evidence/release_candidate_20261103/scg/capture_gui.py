"""Fresh ordinary SCG startup and isolated dialogs; explicitly offscreen evidence."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'apps/SCG/src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog

tag = str(round(float(os.environ['QT_SCALE_FACTOR'])*100))
revision = sys.argv[1]
assert revision.isalnum()
output = Path(__file__).parent/(revision+'-'+tag)
output.mkdir(exist_ok=False)
work = ROOT/'.work/0.1.3-release-20261103/scg'/(revision+'-'+tag)
work.mkdir(exist_ok=False)
app = QApplication([])
for name in ('msyh.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/name))
app.setFont(QFont('Microsoft YaHei', 9))
language, theme = ('zh_CN', 'light') if tag == '125' else ('en_US', 'dark')
window = MainWindow(SettingsStore(work/'settings.ini'), language=language, theme=theme)
window._toolchain_checked = True  # Only automatic tool discovery is suppressed.
window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
window.resize(1200, 800)
window.show()
before = deepcopy(window._model.Dictionary_Get())
records = []


def Flush():
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(30)
    app.processEvents()


def Save(widget, name):
    Flush()
    pixmap = widget.grab()
    assert pixmap.save(str(output/(name+'.png')))
    record = dict(name=name, logical_size=[widget.width(), widget.height()],
                  pixel_size=[pixmap.width(), pixmap.height()], scale=pixmap.devicePixelRatio())
    boxes = widget.findChildren(QDialogButtonBox) if isinstance(widget, QDialog) else ()
    record['buttons'] = [dict(text=button.text(), visible=button.isVisible(),
        inside=widget.rect().contains(button.mapTo(widget, button.rect().bottomRight())))
        for box in boxes for button in box.buttons()]
    assert any(item['visible'] and item['inside'] for item in record['buttons']) if boxes else True
    assert all(item['inside'] for item in record['buttons'] if item['visible'])
    records.append(record)


for page, name in ((0, 'ordinary-hardware'), (1, 'ordinary-workflow'), (2, 'ordinary-build')):
    window.navigation_list.setCurrentRow(page)
    Save(window, name)
    assert window._model.Dictionary_Get() == before
assert not window.board_hardware_page.generate_button.isEnabled()
assert not window.ground_target_page.generate_button.isEnabled()
window.navigation_list.setCurrentRow(0)
for target in ('flight', 'ground'):
    dialog = HardwareTransactionDialog(window._translator, window._model, window._service,
                                       target, parent=window)
    dialog.show()
    for page, name in enumerate(('hardware', 'devices', 'resources')):
        dialog.tabs.setCurrentIndex(page)
        Save(dialog, target+'-'+name)
    if target == 'ground':
        dialog.controller._GroundBoard_Change('silverstar.board.ground_station_0_5')
        dialog.tabs.setCurrentIndex(0)
        Save(dialog, 'ground-private-change')
        assert window._model.Dictionary_Get() == before
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    Flush()
    assert dialog.Configuration_Get() is None
    assert window._model.Dictionary_Get() == before
    dialog.deleteLater()
radio = RadioTransactionDialog(window._translator, window._model, window._service.catalog, window)
radio.show()
Save(radio, 'shared-radio')
radio.reject()
assert window._model.Dictionary_Get() == before
radio.deleteLater()
window.resize(900, 700)
Save(window, 'ordinary-hardware-compact')
for page in (1, 2):
    window.navigation_list.setCurrentRow(page)
    Save(window, ('ordinary-workflow-compact' if page == 1 else 'ordinary-build-compact'))
blank_unchanged = window._model.Dictionary_Get() == before
# Additional owner screenshots use a declared software reference project.
window._model = window._service.ReferenceProject_Create('Workflow properties')
window._Project_Refresh()
window.navigation_list.setCurrentRow(1)
reference = window._model.Dictionary_Get()
from silverstar_fccg.ui.workflow_properties import WorkflowPropertiesDialog
from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
from silverstar_fccg.ui.build_options_dialog import BuildOptionsDialog
for scope in ('algorithms', 'preparation', 'protocols'):
    dialog = WorkflowPropertiesDialog(window._translator, window.workflow_page._display, window._service.catalog, scope, window)
    dialog.show()
    Save(dialog, 'reference-options-'+scope)
    dialog.reject(); dialog.deleteLater(); Flush()
for identity in ('', 'ins', 'recording'):
    dialog = MissionStageTransactionDialog(window._translator,window._model,window._service.catalog,'ascent',window,
        stage_only=not identity, function_id=identity, display=window.workflow_page._display)
    dialog.show()
    Save(dialog, 'reference-'+(identity or 'stage'))
    dialog.reject(); dialog.deleteLater(); Flush()
dialog = BuildOptionsDialog(window._translator,window._model,(),window)
dialog.show(); Save(dialog,'build-options'); dialog.reject(); dialog.deleteLater(); Flush()
assert reference == window._model.Dictionary_Get()
source = [item.relative_to(ROOT) for item in (ROOT/'apps/SCG/src/silverstar_fccg').rglob('*') if item.suffix in ('.py','.json')]
result = dict(mode='Qt offscreen; not a desktop or hardware test',
    source_base=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
    source_sha256={item.as_posix():hashlib.sha256((ROOT/item).read_bytes()).hexdigest() for item in source},
    ordinary_constructor=True, model_substituted=False, automatic_tool_discovery_suppressed=True,
    language=language, theme=theme, flight_generate_enabled=False, ground_generate_enabled=False,
    cancel_model_unchanged=blank_unchanged, reference_dialogs_model_unchanged=reference == window._model.Dictionary_Get(), surfaces=records)
(output/'capture.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf8')
window.close()
print(json.dumps({'output':str(output),'surfaces':len(records),'pass':True}))
