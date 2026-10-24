from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from silverstar_fccg.project.mission_profile import (
    _API, MissionProfile_Build, MissionProfile_Read, MissionProfile_Write, MissionProfile_Require)
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, LogDecoderProfile_Render
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.theme import Theme_Apply


def test_project_roundtrip_parameter_change_header_and_exact_decoder(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    original = model.Dictionary_Get()
    initial = MissionProfile_Build(model, builtin_catalog)
    assert model.Dictionary_Get() == original
    assert MissionProfile_Build(ProjectModel_Parse(original), builtin_catalog) == initial
    model.mode_parameters['deployment']['Delay']['delay'] = 12.5
    updated = MissionProfile_Build(model, builtin_catalog)
    assert updated['sha256'] != initial['sha256']
    delay = next(row for row in updated['rules'] if row['option'] == 'Delay')['parameters'][0]
    assert (delay['value'], delay['unit'], delay['generated_scale']) == (12.5, 's', 1000.0)
    assert re.search(r'#define SYSTEM_FLIGHT_DEPLOY_DELAY_MS\s+12500U', _FlightConfigHeader_Render(model, builtin_catalog))
    # Profile is included in the same semantics hashed by the exact decoder.
    package = LogDecoderProfile_Render(model, builtin_catalog)
    semantics = json.loads(package.project_semantics_content)
    assert semantics['metadata_declarations']['mission_profile'] == updated


@pytest.mark.parametrize('mutation', ['version', 'unknown', 'frame', 'state_bool', 'hardware_number',
    'rule_version', 'unit', 'symbol', 'scale', 'nan', 'bool', 'range', 'log_range', 'digest'])
def test_profile_rejects_incompatible_or_nonphysical_declarations(builtin_catalog, mutation):
    profile = MissionProfile_Build(ReferenceProject_Create(catalog=builtin_catalog), builtin_catalog)
    p = profile['rules'][0]['parameters'][0]
    if mutation == 'version': profile['schema_version'] = True
    elif mutation == 'unknown': profile['script'] = 'arbitrary'
    elif mutation == 'frame': profile['frame']['world'] = 'NED'
    elif mutation == 'state_bool': profile['lifecycle']['states'][0]['state_id'] = False
    elif mutation == 'hardware_number': profile['qualification']['hardware_tested'] = 0
    elif mutation == 'rule_version': profile['rules'][0]['owner']['version'] = '99.0.0'
    elif mutation == 'unit': p['unit'] = 'knots'
    elif mutation == 'symbol': p['generated_symbol'] = 'OTHER_CHANNEL'
    elif mutation == 'scale': p['generated_scale'] = 0
    elif mutation == 'nan': p['value'] = float('nan')
    elif mutation == 'bool': p['value'] = True
    elif mutation == 'range': p['value'] = p['maximum'] + 1
    elif mutation == 'log_range': profile['continuous']['logging'][0]['period_us'] = 2**32
    elif mutation == 'digest': profile['sha256'] = '0' * 64
    if mutation not in ('nan', 'digest'):
        profile['sha256'] = _API['MissionProfile_Digest'](profile)
    with pytest.raises(ValueError, match='mission_profile_'):
        MissionProfile_Require(profile)


def test_atomic_save_backup_failure_conflict_and_duplicate_keys(tmp_path, builtin_catalog, monkeypatch):
    profile = MissionProfile_Build(ReferenceProject_Create(catalog=builtin_catalog), builtin_catalog)
    path = tmp_path / 'mission.ssmission'
    assert MissionProfile_Write(path, profile).value == 'ok'
    previous = path.read_bytes()
    with pytest.raises(ValueError, match='mission_profile_exists'):
        MissionProfile_Write(path, profile)
    changed = deepcopy(profile)
    changed['project']['name'] = 'Changed'
    changed['sha256'] = _API['MissionProfile_Digest'](changed)
    real_replace = _API['MissionProfile_Write'].__globals__['os'].replace
    def Replace_Fail(source, destination):
        if Path(destination) == path:
            raise OSError('injected replace failure')
        return real_replace(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(_API['MissionProfile_Write'].__globals__['os'], 'replace', Replace_Fail)
        with pytest.raises(ValueError, match='injected replace failure'):
            MissionProfile_Write(path, changed, replace_existing=True)
    assert path.read_bytes() == previous
    MissionProfile_Write(path, changed, replace_existing=True)
    assert path.with_suffix('.ssmission.bak').read_bytes() == previous
    assert MissionProfile_Read(path) == changed
    assert not list(tmp_path.glob('.mission-*'))
    duplicate = tmp_path / 'duplicate.ssmission'
    duplicate.write_text('{"schema_id":"a","schema_id":"b"}', encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate_key'):
        MissionProfile_Read(duplicate)


def test_lifecycle_ids_match_actual_firmware_enum():
    header = Path(__file__).parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload/System/Inc/system_lifecycle.h'
    body = re.search(r'typedef enum\s*\{(.*?)\}\s*SystemLifecycleState;', header.read_text(encoding='utf-8'), re.S).group(1)
    assert re.findall(r'SYSTEM_STATE_([A-Z_]+)', body) == [r['type_id'] for r in _API['CONTRACT']['states']]


def test_gui_edit_export_cancel_language_theme_and_resize(tmp_path, qapp, builtin_catalog, monkeypatch):
    service = FccgService(Path(__file__).parents[1])
    # Keep fixtures in the suite's task directory while retaining real plugins.
    service.policy = WorkspacePolicy(Path(__file__).resolve().parents[3])
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._model = ReferenceProject_Create(catalog=window._service.catalog)
    window._Project_Refresh()
    errors = []
    monkeypatch.setattr(window, '_Error_Show', errors.append)
    target = tmp_path / 'gui.ssmission'
    monkeypatch.setattr('silverstar_fccg.ui.main_window.QFileDialog.getSaveFileName', lambda *a, **k: (str(target), ''))
    try:
        window._ModeParameter_Change('deployment', 'Delay', 'delay', 7.5)
        window._MissionProfile_Export()
        exported = MissionProfile_Read(target)
        assert not errors
        assert next(r for r in exported['rules'] if r['option'] == 'Delay')['parameters'][0]['value'] == 7.5
        assert exported['sha256'] in window.flight_configuration_page.mission_profile_panel.identity_label.text()
        before = target.read_bytes()
        monkeypatch.setattr('silverstar_fccg.ui.main_window.QFileDialog.getSaveFileName', lambda *a, **k: ('', ''))
        window._MissionProfile_Export()
        assert target.read_bytes() == before
        panel = window.flight_configuration_page.mission_profile_panel
        from silverstar_fccg.core.i18n import Translator
        for language in ('zh_CN', 'en_US'):
            for theme in ('light', 'dark'):
                Theme_Apply(qapp, theme)
                panel.Language_Apply(Translator(language))
                panel.resize(760, 420); qapp.processEvents()
                assert panel.export_button.isEnabled()
                assert not panel.details.Expanded_Is()
                assert 'GSHC' in panel.export_button.text()
                assert 'mission_profile.' not in panel.lifecycle_label.text()
    finally:
        window._project_dirty = False
        window.close(); qapp.processEvents()
