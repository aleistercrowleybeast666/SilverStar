import os, sys, json
from pathlib import Path
from dataclasses import replace

repo = Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
output = Path(__file__).parent / sys.argv[1]
output.mkdir(exist_ok=True)
sys.path[:0] = [str(repo/'apps/FCCG/src'), str(repo/'apps/FLP/src')]
os.environ['QT_QPA_PLATFORM'] = 'windows'
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QScrollArea
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtTest import QTest
app = QApplication([])
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
window = MainWindow(SettingsStore(repo/'apps/FCCG/.work/field_capture'/sys.argv[1]/'scg.ini'),service=FccgService(repo/'apps/FCCG'))
window.show()
window.pages.setCurrentIndex(5)
QTest.qWait(250)
window.grab().save(str(output/'scg_ground_initial.png'))
initial = {'ground_mode':window._model.ground_target.hardware.mode,'ground_board':window.ground_target_page.board_combo.currentText(),'flight_mode':window._model.hardware.mode,'memory_layout':window._model.build.memory_layout}
window._GroundTarget_Change('enabled',True)
window._GroundTarget_Change('pc_interface','uart')
window.pages.setCurrentIndex(3)
window.air_link_page.findChild(QScrollArea).ensureWidgetVisible(window.ground_target_page.pc_resource)
QTest.qWait(200)
window.grab().save(str(output/'scg_uart_without_inventory.png'))
window._GroundBoard_Change('silverstar.board.ground_station_0_5')
window._GroundTarget_Change('enabled',True)
window._GroundTarget_Change('radio_plugin','silverstar.device.telemetry.sx1281')
window._GroundTarget_Change('pc_interface','uart')
window.pages.setCurrentIndex(3)
QTest.qWait(250)
window.grab().save(str(output/'scg_telemetry_selected.png'))
window.air_link_page.findChild(QScrollArea).ensureWidgetVisible(window.ground_target_page.pc_resource)
QTest.qWait(200)
window.grab().save(str(output/'scg_actual_usart1.png'))
window.pages.setCurrentIndex(5)
QTest.qWait(200)
window.grab().save(str(output/'scg_ground_board.png'))
window.pages.setCurrentIndex(6)
QTest.qWait(200)
window.grab().save(str(output/'scg_build_auto.png'))
pc=window.ground_target_page.pc_resource
selected={'module':window._model.ground_target.module_variant,'pc_resource':window._model.ground_target.pc_resource,'pc_options':[(pc.itemText(i),pc.itemData(i)) for i in range(pc.count())],'resources':[{ 'id':r.resource_id,'kind':r.kind,'physical':r.metadata.get('physical_resource')} for r in window._model.ground_target.hardware.resources],'status':window.ground_target_page.status.text()}
window.close()
from silverstar_flp.plugins.registry import builtin_registry
import silverstar_flp.ui.main_window as flp
flp.QSettings=lambda *_: QSettings(str(output/'flp.ini'),QSettings.Format.IniFormat)
f=flp.MainWindow(builtin_registry())
f._silverstar_project_root=output/('中文外场工程长名称测试_'*10)
f._project.project_path=output/('分析会话中文长名称_'*8+'.ssflp')
f._Project_SetDirty(True)
f.show()
geometry=[]
for width,height in [(1480,920),(1000,700)]:
 f.resize(width,height)
 QTest.qWait(250)
 f._ProjectHeader_Refresh()
 app.processEvents()
 f.grab().save(str(output/f'flp_{width}.png'))
 fields={}
 for name in ['title_label','version_label','credit_label','project_caption_label','project_name_label','language_label','language_combo','theme_label','theme_combo']:
  widget=getattr(f,name);p=widget.mapTo(f,QPoint(0,0));fields[name]={'rect':[p.x(),p.y(),widget.width(),widget.height()],'text':widget.text() if hasattr(widget,'text') else widget.currentText(),'hint':[widget.sizeHint().width(),widget.sizeHint().height()]}
 geometry.append({'size':[f.width(),f.height()],'fields':fields})
f._project.project_path=None
f._silverstar_project_root=None
f._Project_SetDirty(False)
QTest.qWait(100)
f.grab().save(str(output/'flp_unsaved_1000.png'))
f.Language_Apply('en_US')
f.Theme_Apply('dark')
QTest.qWait(100)
f.grab().save(str(output/'flp_en_dark_1000.png'))
f.close()
(output/'capture.json').write_text(json.dumps({'initial':initial,'selected':selected,'flp':geometry},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'initial':initial,'selected':selected,'flp':geometry},ensure_ascii=True))
