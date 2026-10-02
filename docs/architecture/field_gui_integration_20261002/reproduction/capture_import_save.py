import os,sys,json
from pathlib import Path
root=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out=Path(__file__).parent/'final_capture'
sys.path.insert(0,str(root/'apps/FCCG/src'));os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
app=QApplication([])
service=FccgService(root/'apps/FCCG')
service.catalog.installed_root=root/'apps/FCCG/.work/field_capture/isolated_pcb'
service.installer.installed_root=service.catalog.installed_root
service.catalog.Scan()
w=MainWindow(SettingsStore(root/'apps/FCCG/.work/field_capture/import_save.ini'),service=service)
w._Error_Show=lambda error: (_ for _ in ()).throw(RuntimeError(str(error)))
w.show();w.navigation_list.setCurrentRow(5)
source=next((root/'apps/FCCG/.work/qall').glob('test_ground_ioc_import*/CubeMX_inputs'))
result=service.CubeMxProject_Import(source,w._model,risk_acknowledged=True)
w._GroundCubeMxImport_Complete(result)
w._GroundTarget_Change('enabled',True)
w._GroundTarget_Change('radio_plugin','silverstar.device.telemetry.sx1281')
w._GroundTarget_Change('pc_interface','uart')
p=w.ground_target_page
p.pc_resource.setCurrentIndex(p.pc_resource.findData('USART1'))
binding=w._model.ground_target.pc_resource
w._GroundTarget_Change('pc_interface','uart')
assert w._model.ground_target.pc_resource==binding=='USART1'
assert p.save_instance.isEnabled()
QTest.qWait(200);w.grab().save(str(out/'scg_ground_import_complete.png'))
saved=service.CustomBoardPlugin_SaveLocal(w._model,component_id='local.board.ground.pixel',name='Pixel Ground',target_role='ground')
w._Project_Refresh()
assert p.board.findData(saved.component_id)>=0
p.board.setCurrentIndex(p.board.findData(saved.component_id))
QTest.qWait(200);w.grab().save(str(out/'scg_ground_saved_instance.png'))
assert p.import_ioc.isEnabled() and p.import_directory.isEnabled()
record={'source':str(source),'imported_uart':binding,'save_enabled_after_import':True,
        'saved_board':saved.component_id,'selected_board':w._model.ground_target.board,
        'same_interface_kept_binding':True,'snapshot_id':result.hardware.snapshot_id}
(out/'import_save.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print(json.dumps(record));w.close()
