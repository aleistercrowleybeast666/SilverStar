import os, pathlib, sys, json
from copy import deepcopy
root=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'apps/FCCG/src'),str(root/'apps/FCCG/tests')]
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication, QScrollArea
from PySide6.QtCore import QEvent
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
from test_gui_qa_repair import _GroundF103Model_Get
app=QApplication([])
settings=root/'apps/FCCG/.work/gui_011/capture/settings.ini'
settings.parent.mkdir(parents=True,exist_ok=True)
window=MainWindow(SettingsStore(settings),service=FccgService(root/'apps/FCCG'))
out=root/'docs/GSHC/gui_layout_20261001_v1/scg_native'
out.mkdir(exist_ok=True)
window.show()
window.resize(1280,720)
records=[]
initial=deepcopy(window._model)
for language in ('zh_CN','en_US'):
    window._model=deepcopy(initial)
    window._Project_Refresh()
    window.Language_Apply(language)
    window.navigation_list.setCurrentRow(5)
    app.processEvents()
    assert window.grab().save(str(out/(language+'_ground_initial.png')))
    window._model=_GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    for index,name in ((2,'navigation'),(4,'flight_hardware'),(5,'ground_hardware'),(6,'checks')):
        window.navigation_list.setCurrentRow(index)
        app.processEvents()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        assert window.grab().save(str(out/(language+'_'+name+'.png')))
        if index == 2:
            group=window.flight_configuration_page.strategy_group
            ancestor=group.parentWidget()
            while ancestor is not None and not isinstance(ancestor,QScrollArea):
                ancestor=ancestor.parentWidget()
            if ancestor is not None:
                ancestor.ensureWidgetVisible(group,0,0)
                app.processEvents()
                assert window.grab().save(str(out/(language+'_initial_alignment.png')))
        if index in (4,5):
            current=window.board_hardware_page if index == 4 else window.ground_target_page
            ancestor=next(iter(current.findChildren(QScrollArea)),None)
            if ancestor is not None:
                ancestor.verticalScrollBar().setValue(ancestor.verticalScrollBar().maximum())
                app.processEvents()
                assert window.grab().save(str(out/(language+'_'+name+'_bottom.png')))
    records.append(dict(language=language,title=window.title_label.text(),size=[window.width(),window.height()],dpr=window.devicePixelRatioF()))
(out/'capture.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
window.close()
app.processEvents()
print(json.dumps(records,ensure_ascii=True))
