"""Actual bundle preview modal, explicitly using the named reference fixture."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'apps/SCG/src'))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_SCALE_FACTOR']='1.25'
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QDialogButtonBox
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.core.settings import SettingsStore

output=Path(__file__).parent/sys.argv[1]
output.mkdir(exist_ok=False)
app=QApplication([])
for name in ('msyh.ttc','segoeui.ttf'):
    QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/name))
app.setFont(QFont('Microsoft YaHei',9))
window=MainWindow(SettingsStore(ROOT/'.work/0.1.3-software-completion-20261101/gui'/sys.argv[1]/'settings.ini'))
window._toolchain_checked=True
window._model=window._service.ReferenceProject_Create('GUI control preview')
window._Project_Refresh()
window.show()
before=deepcopy(window._model.Dictionary_Get())
fixture=ROOT/'apps/SCG/tests/fixtures/tuning_bundle_v1/kf6-pid.sstuning.json'
QFileDialog.getOpenFileName=lambda *_args:(str(fixture),'TreeDiagram bundle (*.sstuning.json)')
record={'ordinary_constructor_then_explicit_reference_fixture':True,
    'fixture':fixture.relative_to(ROOT).as_posix(),'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
    'offscreen':True,'errors':[]}


def During():
    box=QApplication.activeModalWidget()
    try:
        assert isinstance(box,QMessageBox)
        option=box.checkBox()
        assert option is not None and option.isEnabled() and not option.isChecked()
        assert box.button(QMessageBox.StandardButton.Apply).text()=='应用'
        app.processEvents()
        box.grab().save(str(output/'unchecked.png'))
        option.setChecked(True)
        app.processEvents()
        box.grab().save(str(output/'selected.png'))
        record['logical_size']=[box.width(),box.height()]
        record['buttons']=[button.text() for button in box.buttons()]
        box.button(QMessageBox.StandardButton.Cancel).click()
    except BaseException as error:
        record['errors'].append(str(error))
        if box:box.reject()


QTimer.singleShot(0,During)
window._ParameterProfile_Import('silverstar.algorithm.estimator.kf6')
record['cancel_model_unchanged']=window._model.Dictionary_Get()==before
record['main_window_sha256']=hashlib.sha256((ROOT/'apps/SCG/src/silverstar_fccg/ui/main_window.py').read_bytes()).hexdigest()
(output/'capture.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
assert not record['errors'] and record['cancel_model_unchanged'],record
window.close()
print(json.dumps(record,ensure_ascii=False))
