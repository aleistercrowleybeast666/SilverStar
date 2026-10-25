from dataclasses import replace
from pathlib import Path
import runpy
import json

import pytest
from PySide6.QtCore import Qt

from silverstar_flp.decoder_profiles.mission_profile import MissionProfile_FromDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.ui.pages.overview import OverviewPage
from tests.synthetic_parameter_navigation import NavigationPair_Open

ROOT = Path(__file__).resolve().parents[3]
API = runpy.run_path(str(ROOT / 'tools/silverstar_mission_profile.py'))


@pytest.mark.parametrize('schema_version', [2, 3])
def test_exact_custom_phase_metadata_and_reference_trace_preserve_source(tmp_path,qapp,monkeypatch,schema_version):
    from silverstar_flp.decoder_profiles.mission_profile import MissionTrace_FromPath
    profile=API['MissionProfile_Read'](ROOT/'contracts/mission_profile_v1.golden.json')
    profile.update(schema_id='silverstar.mission-profile/2',schema_version=2,
        process=API['MissionProcess_Default'](),devices=[])
    if schema_version == 3:
        adapter = next(row for row in json.loads((ROOT/'contracts/mission_functions_v1.json').read_text(encoding='utf-8'))['adapters'] if row['category']=='recording')
        function = {key: adapter[key] for key in ('instance_id','plugin_id','category','output')}
        function.update(execution='continuous', start={'kind':adapter['start'],'stage_id':''},
            stop={'kind':adapter['stop'],'stage_id':''}, depends_on=[], input_bindings={})
        profile.update(schema_id='silverstar.mission-profile/3', schema_version=3,
            functions={'schema_version':1,'functions':[function]})
    profile['sha256']=API['MissionProfile_Digest'](profile)
    opened=NavigationPair_Open(tmp_path/'process',flight_samples=7,mission_profile=profile)
    assert MissionProfile_FromDataset(opened.dataset) == profile
    original=opened.dataset.source_path.read_bytes()
    runner=API['MissionProcessRunner'](profile['process'])
    _,events=runner.Sample_Step(dict(time_us=100,valid=True,events=['ready'],altitude_agl_m=None,vertical_velocity_mps=None))
    trace={'schema_id':'silverstar.mission-trace/1','profile_sha256':profile['sha256'],
        'session_id':'synthetic','source':'desktop_reference','events':events}
    path=tmp_path/'process.ssmissiontrace';API['MissionTrace_Write'](path,trace,profile)
    assert MissionTrace_FromPath(opened.dataset,path)==trace
    page=OverviewPage(Translator('en_US'))
    try:
        page.Dataset_Set(opened.dataset)
        assert page.mission_trace_button.isEnabled()
        monkeypatch.setattr('silverstar_flp.ui.pages.overview.QFileDialog.getOpenFileName',lambda *a,**k:(str(path),''))
        page._MissionTrace_Open()
        assert 'Desktop reference' in page.mission_trace_label.text()
        page.Language_Apply(Translator('zh_CN'))
        assert '桌面参考' in page.mission_trace_label.text()
        assert 'Recorded' in page.mission_trace_label.text()  # Explicitly says it is NOT onboard Recorded.
        assert opened.dataset.source_path.read_bytes()==original
    finally:
        page.close()


def test_exact_decoder_profile_is_declared_configuration_and_legacy_stays_absent(tmp_path, qapp):
    profile = API['MissionProfile_Read'](ROOT / 'contracts/mission_profile_v1.golden.json')
    opened = NavigationPair_Open(tmp_path / 'profile', flight_samples=7, mission_profile=profile)
    before = opened.dataset.source_path.read_bytes()
    assert MissionProfile_FromDataset(opened.dataset) == profile
    returned = MissionProfile_FromDataset(opened.dataset)
    returned['project']['name'] = 'Changed local copy'
    assert MissionProfile_FromDataset(opened.dataset) == profile
    page = OverviewPage(Translator('zh_CN'))
    try:
        page.Dataset_Set(opened.dataset)
        assert profile['sha256'] in page.mission_profile_label.text()
        assert page.mission_profile_label.textFormat() == Qt.TextFormat.PlainText
        page.Language_Apply(Translator('en_US'))
        assert 'Project declaration' in page.mission_profile_label.text()
    finally:
        page.close()
    assert opened.dataset.source_path.read_bytes() == before
    legacy = NavigationPair_Open(tmp_path / 'legacy', flight_samples=7)
    assert MissionProfile_FromDataset(legacy.dataset) is None
    with pytest.raises(ValueError, match='mission_profile_exact_open_required'):
        MissionProfile_FromDataset(replace(opened.dataset, metadata={}))


@pytest.mark.parametrize('mutation', ['version', 'unit', 'digest'])
def test_profile_refused_without_reinterpreting_recorded_states(tmp_path, mutation, qapp):
    profile = API['MissionProfile_Read'](ROOT / 'contracts/mission_profile_v1.golden.json')
    if mutation == 'version': profile['schema_version'] = 2
    elif mutation == 'unit': profile['rules'][0]['parameters'][0]['unit'] = 'knots'
    elif mutation == 'digest': profile['sha256'] = '0' * 64
    if mutation != 'digest': profile['sha256'] = API['MissionProfile_Digest'](profile)
    opened = NavigationPair_Open(tmp_path / mutation, flight_samples=7, mission_profile=profile)
    with pytest.raises(ValueError, match='mission_profile_'):
        MissionProfile_FromDataset(opened.dataset)
    page = OverviewPage(Translator('en_US'))
    try:
        page.Dataset_Set(opened.dataset)
        assert page.mission_profile_label.text().startswith('Mission configuration refused:')
    finally:
        page.close()
