from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from pathlib import Path
import pytest
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from protocol.air import parse_air_frame
from protocol.gsp_min import build_gsp_frame
from protocol.receive_pipeline import ReceivePipeline
from services.i18n import I18n, Language
from services.navigation_state import NavigationState
from services.preferences import Theme
from services.state_model import EventHistory
from test_start_ack_state import make_controller
from ui.main_window import MainWindow


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("theme", list(Theme))
def test_m0_live_gui_languages_themes_and_commands(tmp_path, language, theme):
    application = QApplication.instance() or QApplication([])
    # Preserve the original GUI test's explicit font setup across Qt backends.
    for name in ("msyh.ttc", "segoeui.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    application.setFont(QFont("Microsoft YaHei", 9))
    i18n = I18n(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    i18n.set_language(language)
    window = MainWindow(i18n)
    window.resize(1000, 700)
    window.gl_view.hide()
    window.render_timer.stop()
    controller = make_controller()
    controller.window = window
    # Real M0 parser and Controller transitions; only the serial endpoint is mocked.
    controller._handle_capability(parse_air_frame(bytes.fromhex("12010001070f10d007"))[1])
    cap_seq = controller.pending_capability_ack.command_seq
    controller._handle_ack_message(parse_air_frame(bytes((0x40, 2, cap_seq, 5, 0, 0, 0, 0, 0)))[1])
    assert controller.state.capability_acked
    assert len(controller.worker.sent) == 1  # Capability ACK only, no NAV subscription.
    controller._handle_preflight_status(parse_air_frame(bytes.fromhex("1303030400ff003400"))[1])
    window.bind_runtime_model(controller.state, controller.events)
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme.value))
    window.btn_start.clicked.connect(controller.send_start)
    window.show()
    application.processEvents()
    assert not hasattr(window, "navigation_preparation_panel")
    assert not hasattr(window, "navigation_health_panel")
    assert controller.state.navigation.requested_session is None
    assert not window.btn_start.isEnabled()  # M0 alignment/lock gates still apply.
    controller._handle_preflight_status(parse_air_frame(bytes.fromhex("1304030400ff037700"))[1])
    window.render_state()
    assert controller.state.start_ready()
    assert window.btn_start.isEnabled()
    before = len(controller.worker.sent)
    QTest.mouseClick(window.btn_start, Qt.LeftButton)
    application.processEvents()
    assert len(controller.worker.sent) == before + 1
    pending = controller._find_pending_air_cmd(1)
    assert pending is not None
    controller._handle_ack_message(parse_air_frame(bytes((0x40, 5, pending.seq, 1, 0, 0, 0, 0, 0)))[1])
    # ACK handling alone does not invent sensor data.
    assert controller.state.sensor.velocity_mps is None
    wire = bytes.fromhex(
        "100001000000000800000000000000000000ff7f000000000000"
        "7903c9bdfe1dcb3d6fe0be3d6484efbe23bcf73e2bfe933d")
    event = ReceivePipeline().feed(build_gsp_frame(2, bytes((186, 20, 50)) + wire))[0]
    controller._handle_flight_state(event.air_message, event)
    window.render_state()
    assert controller.state.sensor.velocity_mps is not None
    assert controller.state.sensor.position_m is not None
    out = Path(__file__).resolve().parents[1] / ".work/m0-release-gui"
    out.mkdir(parents=True, exist_ok=True)
    for name, page in (("preflight", window.preflight_page), ("flight", window.flight_page)):
        window.pages.setCurrentWidget(page)
        application.processEvents()
        assert window.size() == QSize(1000, 700)
        assert window.grab().save(str(out / f"{application.platformName()}_{name}_{language.value}_{theme.value}.png"))
    window.close()
    window.deleteLater()
    application.processEvents()
