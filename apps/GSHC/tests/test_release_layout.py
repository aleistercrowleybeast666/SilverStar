import os
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, QSize
from PySide6.QtWidgets import QApplication
from services.i18n import I18n
from services.state_model import EventHistory
from test_ui_workflow import ready_state
from ui.main_window import MainWindow


@pytest.mark.parametrize('size', [(1280,720), (1536,816)])
@pytest.mark.parametrize('language', ['zh_CN','en_US'])
def test_original_monitor_rows_and_six_plots_are_visible(tmp_path, size, language):
    app=QApplication.instance() or QApplication([])
    i18n=I18n(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat))
    i18n.set_language(language)
    window=MainWindow(i18n)
    window.render_timer.stop()
    state=ready_state()
    state.sensor.accel_mps2=(0.125,-0.375,9.807)
    state.sensor.gyro_radps=(0.012,-0.025,0.001)
    state.sensor.quat=(1.0,0.0,0.0,0.0)
    state.sensor.quat_valid=True
    state.sensor.euler_rpy=(0.01,-0.02,1.57)
    state.sensor.velocity_mps=(12.345,-6.789,20.012)
    state.sensor.position_m=(123.456,-234.567,1200.012)
    state.sensor.revision=1
    window.bind_runtime_model(state, EventHistory())
    window.show()
    app.processEvents()
    window.resize(*size)
    app.processEvents()
    assert window.size() == QSize(*size)
    def rect(widget):
        return QRect(widget.mapTo(window,QPoint()),widget.size())
    system=rect(window.lbl_pf_system_ready.parentWidget())
    calibration=rect(window.lbl_cal_ready.parentWidget())
    alignment=rect(window.lbl_align_ready.parentWidget())
    assert system.top() == calibration.top() == alignment.top()
    assert system.right() < calibration.left() < alignment.left()
    assert rect(window.lbl_pf_accel).top() < rect(window.btn_start).top()
    for widget in (window.lbl_pf_system_ready, window.lbl_pf_selftest, window.lbl_cal_ready,
                   window.lbl_align_ready, window.lbl_pf_accel, window.lbl_pf_gyro,window.lbl_pf_gnss_usable,window.btn_start):
        assert window.rect().contains(rect(widget)), (language,size,rect(widget))
    window.pages.setCurrentWidget(window.flight_page)
    app.processEvents()
    assert window.size() == QSize(*size)
    status=rect(window.lbl_flight_lifecycle.parentWidget())
    data=rect(window.lbl_flight_accel.parentWidget())
    mission=rect(window.lbl_mission_state.parentWidget())
    assert status.top() == data.top() == mission.top()
    viewport=rect(window.flight_status_scroll.viewport())
    for widget in (window.lbl_flight_lifecycle,window.lbl_packet_loss,window.lbl_flight_vel,
                   window.lbl_flight_pos,window.lbl_mission_parachute):
        assert viewport.contains(rect(widget)), (language,size,rect(widget),viewport)
    plots=[rect(window.plot_widgets[(key,axis)]) for key in ('vel','pos') for axis in range(3)]
    assert len({r.top() for r in plots[:3]}) == 1
    assert len({r.top() for r in plots[3:]}) == 1
    assert plots[0].top() < plots[3].top()
    assert all(window.rect().contains(r) for r in plots)
    assert all(r.width() >= 200 and r.height() >= 100 for r in plots)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_m0_flight_status_does_not_reserve_navigation_chart_space(tmp_path):
    app = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path/'settings.ini'), QSettings.IniFormat))
    window = MainWindow(i18n)
    try:
        window.render_timer.stop()
        window.gl_view.hide()
        window.bind_runtime_model(ready_state(), EventHistory())
        window.pages.setCurrentWidget(window.flight_page)
        window.resize(1536, 816)
        window.show()
        app.processEvents()
        assert not hasattr(window, "navigation_health_panel")
        panel = window.flight_status_scroll
        summary_bottom = panel.mapTo(window, QPoint()).y() + panel.height()
        chart_top = window.plot_layout.parentWidget().mapTo(window, QPoint()).y()
        assert chart_top - summary_bottom <= 24
        assert all(window.plot_widgets[(key, axis)].height() >= 140
                   for key in ('vel', 'pos') for axis in range(3))
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
