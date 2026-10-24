from dataclasses import replace
from pathlib import Path
import runpy

import pytest
from PySide6.QtCore import Qt

from silverstar_flp.decoder_profiles.mission_profile import MissionProfile_FromDataset
from silverstar_flp.core.i18n import Translator
from silverstar_flp.ui.pages.overview import OverviewPage
from tests.synthetic_parameter_navigation import NavigationPair_Open

ROOT = Path(__file__).resolve().parents[3]
API = runpy.run_path(str(ROOT / 'tools/silverstar_mission_profile.py'))


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
