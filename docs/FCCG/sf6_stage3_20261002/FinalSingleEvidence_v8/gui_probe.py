import os,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'apps/GSHC'),str(root/'apps/GSHC/tests')]
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QWidget,QLabel
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtCore import QSettings
from services.i18n import I18n,Language
from services.preferences import Theme
from test_ui_workflow import ready_state
from ui.main_window import MainWindow
app=QApplication([])
for name in ('msyh.ttc','segoeui.ttf'):
    path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
    if path.is_file():QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Microsoft YaHei',9))
dest=Path(__file__).parent/('GUI_'+sys.argv[1]);dest.mkdir(exist_ok=False)
report=[]
for language in Language:
    for theme in Theme:
        i18n=I18n(QSettings(str(dest/(language.value+'_'+theme.value+'.ini')),QSettings.IniFormat));i18n.set_language(language)
        window=MainWindow(i18n);window.resize(1000,700);window.gl_view.hide()
        state=ready_state();state.navigation.algorithm_id=3
        window.bind_runtime_model(state,None)
        window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme.value));window.show();app.processEvents()
        window.render_timer.stop();window.pages.setCurrentWidget(window.preflight_page);app.processEvents()
        page=window.preflight_page.widget()
        def info(widget):
            entry=dict(type=type(widget).__name__,geometry=[widget.x(),widget.y(),widget.width(),widget.height()],
                       minhint=[widget.minimumSizeHint().width(),widget.minimumSizeHint().height()])
            if hasattr(widget,'title'):entry['title']=widget.title()
            if hasattr(widget,'text'):entry['text']=widget.text()
            entry['children']=[info(child) for child in widget.children() if isinstance(child,QWidget)]
            return entry
        report.append(dict(language=language.value,theme=theme.value,viewport=window.preflight_page.viewport().width(),content=info(page)))
        window.grab().save(str(dest/(language.value+'_'+theme.value+'.png')))
        window.close();window.deleteLater();app.processEvents()
(dest/'geometry.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
