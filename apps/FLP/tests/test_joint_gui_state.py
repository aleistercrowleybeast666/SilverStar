import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.project import Project_Load, ProjectDocument
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.theme import Theme_Apply
from tests.synthetic_parameter_navigation import NavigationPair_Open


@pytest.mark.parametrize('language', ['zh_CN','en_US'])
@pytest.mark.parametrize('theme', ['light','dark'])
def test_range_shell_1000_700_language_theme_and_pointer(qtbot, tmp_path, language, theme):
    app = QApplication.instance()
    # The Windows offscreen backend does not discover fonts automatically.
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    assert font_id >= 0
    app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    Theme_Apply(app, theme)
    window = MainWindow(builtin_registry())
    qtbot.addWidget(window)
    opened = NavigationPair_Open(tmp_path/'pair', flight_samples=101)
    window._LogOpenResult_Set(opened, ProjectDocument())
    window.Language_Apply(language)
    window.resize(1000,700)
    window.show()
    qtbot.wait(30)
    assert window.width() == 1000 and window.height() == 700
    bar = window.time_range
    assert not bar.isVisible()
    window._Page_Select(2)
    assert bar.isVisible()
    assert bar.width() >= bar.minimumSizeHint().width()
    for control in (bar.preset, bar.duration, bar.start, bar.end, bar.slider):
        assert control.isEnabled() and control.isVisible()
        assert control.geometry().right() < bar.width()
    bar.Mission_Set(300)
    bar.duration.setValue(60)
    assert bar.controller.model.duration == 60
    qtbot.mouseClick(bar.slider, Qt.MouseButton.LeftButton, pos=bar.slider.rect().center())
    assert 0 <= bar.start.value() <= bar.end.value() <= 300
    assert window.grab().save(str(tmp_path/f'FLP_{language}_{theme}.png'))
    window._Project_SetDirty(False)
    window.close()


def test_project_reopens_selected_what_if_identity_and_exact_time_range(qtbot, tmp_path):
    registry = builtin_registry()
    opened = NavigationPair_Open(tmp_path/'pair', flight_samples=101)
    first = MainWindow(registry)
    qtbot.addWidget(first)
    first._LogOpenResult_Set(opened, ProjectDocument())
    plugin = registry.Algorithm_Get('silverstar.algorithm.kf6')
    result = plugin.run(opened.dataset, ReplayRequest(mode=ReplayMode.WHAT_IF,
                                                    parameters={'baro_std_m':6}))
    entry = first._replay_store.Result_Add(result, algorithm_name='KF6', restored_run_index=3)
    first._AnalysisSource_Set(entry.source_id)
    first.time_range.controller.Range_Set(.123,.876)
    first.time_range.State_Restore(first.time_range.controller.model.State_Get())
    project = tmp_path/'saved.ssflp'
    first._Project_Write(project)
    assert project.is_file()
    saved = Project_Load(project)
    assert saved.ui_state['analysis_source'] == entry.source_id
    assert saved.ui_state['time_range']['start'] == .123
    first.close()
    second = MainWindow(registry)
    qtbot.addWidget(second)
    errors=[]
    second._Error_Show = errors.append
    second._LogOpenResult_Set(opened, saved)
    second._AnalysisSource_Restore()
    qtbot.waitUntil(lambda: second._active_worker is None, timeout=30000)
    assert not errors
    assert second._replay_store.ActiveSource_Get().source_id == entry.source_id
    assert second.time_range.controller.model.start == .123
    assert second.time_range.controller.model.end == .876
    assert second.time_range.controller.model.preset == 'Custom'
    assert second._source_restore_index is None
    second._Project_SetDirty(False)
    second.close()
