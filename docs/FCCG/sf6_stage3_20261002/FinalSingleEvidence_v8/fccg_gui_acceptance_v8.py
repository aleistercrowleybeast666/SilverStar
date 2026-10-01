from pathlib import Path
import os,sys,json,tempfile
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'apps/FCCG/src'));os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QScrollArea
from PySide6.QtGui import QFont,QFontDatabase
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
work=root/'.work/SF6_20261001_v1';dest=work/'FCCG_GUI_Final_v8_Acceptance';dest.mkdir(exist_ok=False)
app=QApplication([])
fonts={}
for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf','segoeuib.ttf'):
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
    if path.is_file(): fonts[name]=QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Microsoft YaHei',9));service=FccgService(root/'apps/FCCG')
settings_parent=service.workspace_root/'.work';settings_parent.mkdir(exist_ok=True);settings_root=Path(tempfile.mkdtemp(prefix='GuiFinalV8Fonts-',dir=settings_parent))
reports=[]
for theme in ('light','dark'):
    window=MainWindow(SettingsStore(settings_root/(theme+'.ini')),service=service,language='zh_CN',theme=theme)
    window._model=service.Project_Open(work/'SF6_v8');window._Project_Refresh();window.resize(1360,920);window.show();app.processEvents()
    report={'theme':theme,'title':window.title_label.text(),'version':window.version_label.text(),'gain_count':len([key for key in window.algorithm_parameters_page.editors if key[0]=='silverstar.algorithm.estimator.sf6' and key[1].startswith('gain_')]),'ground_status':window.ground_target_page.status.text(),'flight_mcu':window.board_hardware_page.platform_values['part'].text(),'ground_mcu':window.ground_target_page.platform_values['part'].text(),'font_ids':fonts}
    for label,index,widget in (('ground_enabled',3,window.ground_target_page.enabled),('air_crc',3,window.air_link_page.crc),('sf6_gains',2,window.algorithm_parameters_page.editors[('silverstar.algorithm.estimator.sf6','gain_pu')])):
        window.navigation_list.setCurrentRow(index);app.processEvents();page=window.pages.currentWidget()
        for scroll in page.findChildren(QScrollArea):scroll.ensureWidgetVisible(widget)
        app.processEvents();window.grab().save(str(dest/(theme+'_'+label+'.png')))
    window.ground_target_page.enabled.setChecked(False);window.navigation_list.setCurrentRow(3);app.processEvents()
    for scroll in window.air_link_page.findChildren(QScrollArea):scroll.ensureWidgetVisible(window.ground_target_page.enabled)
    app.processEvents();window.grab().save(str(dest/(theme+'_ground_disabled.png')))
    report['ground_generate_enabled_after_disable']=window.ground_target_page.generate_button.isEnabled() if hasattr(window.ground_target_page,'generate_button') else None
    report['disabled_status']=window.ground_target_page.status.text();reports.append(report)
    window._project_state=type(window._project_state).DRAFT;window.close();window.deleteLater();app.processEvents()
(dest/'results.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(reports,ensure_ascii=True))
