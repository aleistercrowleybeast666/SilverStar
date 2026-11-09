"""Real QApplication event loop: ordinary main window + target drafts + exit."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
from silverstar_fccg.ui.main_window import MainWindow

output = Path(sys.argv[1])
output.mkdir(exist_ok=True)
app = QApplication([])
result = {'unexpected_windows': [], 'last_window_closed': False,
          'about_to_quit': False, 'timed_out': False, 'errors': []}


class WindowProbe(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            if not isinstance(obj, (MainWindow, HardwareTransactionDialog)):
                result['unexpected_windows'].append({'kind':type(obj).__name__,
                    'name':obj.objectName(), 'title':obj.windowTitle(),
                    'parent':type(obj.parent()).__name__})
        return False


probe = WindowProbe(app)
app.installEventFilter(probe)
window = MainWindow(SettingsStore(output/'settings.ini'))
window._toolchain_checked = True
window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
window._Error_Show = lambda *args: result['errors'].append(str(args))
window.show()


def Run():
    try:
        for target in ('ground', 'flight'):
            for apply in (False, True):
                before = deepcopy(window._model.Dictionary_Get())
                def During():
                    dialog = QApplication.activeModalWidget()
                    try:
                        assert isinstance(dialog, HardwareTransactionDialog)
                        if target == 'ground':
                            dialog.controller._GroundBoard_Change('silverstar.board.ground_station_0_5')
                        else:
                            dialog.controller._BoardSelection_Change(
                                window._service.ReferenceProject_Create('PCB').board)
                        assert window._model.Dictionary_Get() == before
                        if apply: dialog.accept()
                        else: QTest.keyClick(dialog, Qt.Key.Key_Escape)
                    except BaseException:
                        result['errors'].append(traceback.format_exc())
                        if dialog: dialog.reject()
                QTimer.singleShot(0, During)
                window._HardwareTransaction_Open(target)
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
                if not apply: assert window._model.Dictionary_Get() == before
                assert [w for w in app.topLevelWidgets() if w.isVisible()] == [window]
        window.close()
    except BaseException:
        result['errors'].append(traceback.format_exc())
        app.quit()


def Timeout():
    result['timed_out'] = True
    app.quit()


app.lastWindowClosed.connect(lambda:result.update(last_window_closed=True))
app.aboutToQuit.connect(lambda:result.update(about_to_quit=True))
QTimer.singleShot(0, Run)
QTimer.singleShot(30000, Timeout)
result['qt_exit_code'] = app.exec()
(output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result))
raise SystemExit(0 if result['last_window_closed'] and result['about_to_quit'] and
                 not result['timed_out'] and not result['errors'] and not result['unexpected_windows'] else 1)
