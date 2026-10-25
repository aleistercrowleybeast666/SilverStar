from copy import deepcopy
import json
from pathlib import Path
import runpy
import pytest

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from services.i18n import I18n, Language
from ui.main_window import MainWindow
from mission_profile import MissionProfile_Read
from test_start_ack_state import make_controller

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('schema_version', [2, 3])
def test_custom_phase_snapshot_and_trace_are_offline_and_never_authorize_live_state(tmp_path, monkeypatch, schema_version):
    api=runpy.run_path(str(ROOT/'tools/silverstar_mission_profile.py'))
    profile=api['MissionProfile_Read'](ROOT/'contracts/mission_profile_v1.golden.json')
    profile.update(schema_id='silverstar.mission-profile/2',schema_version=2,
        process=api['MissionProcess_Default'](),devices=[])
    if schema_version == 3:
        adapter = next(row for row in json.loads((ROOT/'contracts/mission_functions_v1.json').read_text(encoding='utf-8'))['adapters'] if row['category']=='recording')
        function = {key: adapter[key] for key in ('instance_id','plugin_id','category','output')}
        function.update(execution='continuous', start={'kind':adapter['start'],'stage_id':''},
            stop={'kind':adapter['stop'],'stage_id':''}, depends_on=[], input_bindings={})
        profile.update(schema_id='silverstar.mission-profile/3', schema_version=3,
            functions={'schema_version':1,'functions':[function]})
    profile['sha256']=api['MissionProfile_Digest'](profile)
    api['MissionProfile_Write'](tmp_path/'process.ssmission',profile)
    runner=api['MissionProcessRunner'](profile['process']);events=[]
    for i,event in enumerate(('ready','start_accepted','launch_detected','burnout_detected','apogee_confirmed',
                              None,'deployment_confirmed','landed_confirmed','recovery_complete')):
        _,records=runner.Sample_Step(dict(time_us=i*1000000,valid=True,events=[event] if event else [],
            altitude_agl_m=None,vertical_velocity_mps=None));events.extend(records)
    trace={'schema_id':'silverstar.mission-trace/1','profile_sha256':profile['sha256'],
        'session_id':'synthetic','source':'desktop_reference','events':events}
    api['MissionTrace_Write'](tmp_path/'process.ssmissiontrace',trace,profile)
    application=QApplication.instance() or QApplication([])
    i18n=I18n(QSettings(str(tmp_path/'trace.ini'),QSettings.Format.IniFormat))
    window=MainWindow(i18n);window.render_timer.stop();window.gl_view.hide()
    controller=make_controller();window.bind_runtime_model(controller.state,controller.events)
    authority=(controller.state.capability_acked,controller.state.mission_started,controller.state.start_transaction_pending())
    try:
        monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName',lambda *a,**k:(str(tmp_path/'process.ssmission'),''))
        window._MissionProfile_Open()
        assert window._declared_mission_profile == profile
        assert window.btn_mission_trace.isEnabled()
        monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName',lambda *a,**k:(str(tmp_path/'process.ssmissiontrace'),''))
        window._MissionTrace_Open()
        assert window._declared_mission_trace==trace
        for language in Language:
            i18n.set_language(language);window.retranslate_ui()
            assert '0s' in window.lbl_mission_profile.text()
            assert profile['sha256'] in window.lbl_mission_profile.text()
        bad=deepcopy(trace);bad['profile_sha256']='0'*64
        (tmp_path/'bad.ssmissiontrace').write_text(json.dumps(bad),encoding='utf-8')
        monkeypatch.setattr('ui.main_window.QFileDialog.getOpenFileName',lambda *a,**k:(str(tmp_path/'bad.ssmissiontrace'),''))
        window._MissionTrace_Open()
        assert window._declared_mission_trace==trace and 'mismatch' in window._mission_profile_error
        assert window._state is controller.state
        assert authority==(controller.state.capability_acked,controller.state.mission_started,controller.state.start_transaction_pending())
    finally:
        window.close();application.processEvents()


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
