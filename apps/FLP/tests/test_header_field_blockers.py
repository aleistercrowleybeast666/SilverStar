import pytest
from PySide6.QtCore import QPoint, QRect, QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from silverstar_flp.plugins.registry import builtin_registry
import silverstar_flp.ui.main_window as ui


@pytest.mark.parametrize('language',['zh_CN','en_US'])
@pytest.mark.parametrize('theme',['light','dark'])
def test_header_actual_geometry_and_dirty_suffix(language,theme,tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui,'QSettings',lambda *_:QSettings(str(tmp_path/'flp.ini'),QSettings.Format.IniFormat))
    w=ui.MainWindow(builtin_registry(),language=language,theme=theme)
    w._silverstar_project_root=tmp_path/('中文工程名称'*40)
    w._project.project_path=tmp_path/('中文会话'*25+'.ssflp')
    w._Project_SetDirty(True)
    w.show()
    names=['title_label','version_label','credit_label','project_caption_label','project_name_label',
           'language_label','language_combo','theme_label','theme_combo']
    for width,height in [(1480,920),(1000,700),(1280,720),(1480,920)]:
        w.resize(width,height);QTest.qWait(30);app.processEvents()
        rectangles=[QRect(getattr(w,n).mapTo(w,QPoint(0,0)),getattr(w,n).size()) for n in names]
        for i,r in enumerate(rectangles):
            assert w.rect().contains(r)
            assert all(not r.intersects(other) for other in rectangles[i+1:])
        assert w.project_name_label.text().endswith(' *')
        assert w.project_name_label.fontMetrics().horizontalAdvance(w.project_name_label.text())<=w.project_name_label.contentsRect().width()
        assert '中文工程名称' in w.project_name_label.toolTip()
        for n in ('title_label','version_label','credit_label','language_combo','theme_combo'):
            widget=getattr(w,n);assert widget.height()>=widget.sizeHint().height()
    w._project.project_path=None;w._silverstar_project_root=None
    w._Project_SetDirty(False);app.processEvents()
    assert w.project_name_label.text()
    w.close()
