from pathlib import Path
import os, sys, json, runpy
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
name=sys.argv[1]
out=repo/'docs/architecture/field_gui_integration_20261002/entry_capture'
out.mkdir(parents=True,exist_ok=True)
data=repo/'.work/entry_capture'/name
data.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='windows'
os.environ['SILVERSTAR_GSHC_DATA_ROOT']=str(data/'gshc_data')
sys.dont_write_bytecode=True
sys.path.insert(0,str(repo))
from PySide6 import QtCore,QtWidgets
OriginalSettings=QtCore.QSettings
class IsolatedSettings(OriginalSettings):
    def __init__(self,*args,**kwargs):
        if len(args)>=2 and isinstance(args[0],str) and isinstance(args[1],str):
            super().__init__(str(data/(args[0]+'_'+args[1]+'.ini')),OriginalSettings.Format.IniFormat)
        else:super().__init__(*args,**kwargs)
QtCore.QSettings=IsolatedSettings
QtCore.QStandardPaths.writableLocation=lambda *_:str(data/'appdata')
serial_attempts=[]
import serial.serialwin32
def forbid_serial_open(self):
    serial_attempts.append(str(self.port))
    raise RuntimeError('Hardware serial open forbidden during GUI-only acceptance')
serial.serialwin32.Serial.open=forbid_serial_open
original_exec=QtWidgets.QApplication.exec
captured=[]
def application_exec(self):
    def capture_and_close():
        for w in self.topLevelWidgets():
            if w.isVisible() and isinstance(w,QtWidgets.QMainWindow):
                pix=w.grab()
                filename=name+'.png'
                pix.save(str(out/filename))
                captured.append({'class':type(w).__module__+'.'+type(w).__name__,'title':w.windowTitle(),'visible':w.isVisible(),'logical_size':[w.width(),w.height()],'pixel_size':[pix.width(),pix.height()],'screenshot':filename})
                w.close()
        (out/(name+'.json')).write_text(json.dumps({'entry':name+'.py','captured':captured,'serial_open_attempts':serial_attempts,'settings_isolated':True,'input_method':'actual root runpy and Qt event loop; automatic window grab and close, no native mouse'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        self.quit()
    QtCore.QTimer.singleShot(1000,capture_and_close)
    return original_exec()
QtWidgets.QApplication.exec=application_exec
sys.argv=[str(repo/(name+'.py'))]
try:
    runpy.run_path(str(repo/(name+'.py')),run_name='__main__')
except SystemExit as e:
    assert not serial_attempts,serial_attempts
    assert captured,'Root entry did not show a main window'
    raise
