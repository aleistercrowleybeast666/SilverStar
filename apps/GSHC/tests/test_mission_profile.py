from copy import deepcopy
import json
from pathlib import Path
import runpy

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from services.i18n import I18n, Language
from ui.main_window import MainWindow
from mission_profile import MissionProfile_Read
from test_start_ack_state import make_controller

ROOT = Path(__file__).resolve().parents[3]


def test_offline_profile_import_cancel_refusal_and_language_keep_live_state(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    i18n = I18n(QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    window = MainWindow(i18n)
    window.render_timer.stop()
    window.gl_view.hide()
    controller = make_controller()
    window.bind_runtime_model(controller.state, controller.events)
    original_state = controller.state
    authority = (original_state.capability_acked, original_state.mission_started, original_state.start_transaction_pending())
    path = ROOT / 'contracts/mission_profile_v1.golden.json'
    monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName', lambda *a, **k: (str(path), ''))
    try:
        window._MissionProfile_Open()
        profile = deepcopy(window._declared_mission_profile)
        assert profile == MissionProfile_Read(path)
        assert profile['sha256'] in window.lbl_mission_profile.text()
        assert window.lbl_mission_profile.textFormat() == Qt.TextFormat.PlainText
        assert window._state is original_state
        for language in Language:
            i18n.set_language(language)
            window.retranslate_ui()
            assert profile['sha256'] in window.lbl_mission_profile.text()
        monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName', lambda *a, **k: ('', ''))
        window._MissionProfile_Open()
        assert window._declared_mission_profile == profile
        api = runpy.run_path(str(ROOT / 'tools/silverstar_mission_profile.py'))
        invalid = deepcopy(profile); invalid['frame']['world'] = 'NED'
        invalid['sha256'] = api['MissionProfile_Digest'](invalid)
        bad_path = tmp_path / 'bad.ssmission'
        bad_path.write_text(json.dumps(invalid), encoding='utf-8')
        monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName', lambda *a, **k: (str(bad_path), ''))
        window._MissionProfile_Open()
        assert window._declared_mission_profile == profile
        assert window._state is original_state
        assert authority == (original_state.capability_acked, original_state.mission_started, original_state.start_transaction_pending())
        assert window._mission_profile_error == 'mission_profile_frame_or_source'
    finally:
        window.close(); application.processEvents()
