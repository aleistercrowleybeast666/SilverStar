from dataclasses import replace
from io import BytesIO
import json
import zipfile

import pytest

from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _LogSource_Render, LogDecoderProfile_Render
from silverstar_fccg.project.compact_logging import CompactLogStreams_Get, CompactLogRequiredRecords_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create

SF6 = 'silverstar.algorithm.estimator.sf6'
PURE_INS = 'FLIGHT_LOG_RECORD_PURE_INS'
TELEMETRY_DIAG = 'FLIGHT_LOG_RECORD_TELEMETRY_DIAG'


def _Choices_Set(model, enabled):
    model.logging_streams = [replace(stream, enabled=enabled)
                             if stream.record in (PURE_INS, TELEMETRY_DIAG) else stream
                             for stream in model.logging_streams]


@pytest.mark.parametrize('tier', ('full', 'standard', 'compact', 'minimal'))
@pytest.mark.parametrize('estimator', (None, SF6))
@pytest.mark.parametrize('retained_enabled', (False, True))
def test_effective_tier_logging_policy_keeps_retained_choices(builtin_catalog, tier, estimator, retained_enabled):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = estimator
    _Choices_Set(model, retained_enabled)
    FeatureTier_Apply(model, tier, builtin_catalog)
    retained = list(model.logging_streams)
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    effective = {stream.record: stream for stream in CompactLogStreams_Get(loaded)}
    bounded = tier in ('compact', 'minimal')
    assert effective[TELEMETRY_DIAG].enabled == (retained_enabled and not bounded)
    assert effective[PURE_INS].enabled == ((estimator is None) if bounded else retained_enabled)
    assert loaded.logging_streams == retained
    assert len(effective) == len(retained) == 40
    source = _LogSource_Render(loaded)
    for record in (PURE_INS, TELEMETRY_DIAG):
        assert f'{{{record}, {int(effective[record].enabled)}U,' in source
        prohibited = bounded and (record == TELEMETRY_DIAG or estimator == SF6)
        assert (f'case {record}: return 0U;' in source) == prohibited
    if tier == 'compact':
        header = _FlightConfigHeader_Render(loaded, builtin_catalog)
        assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH' not in header
        assert 'SYSTEM_LOG_RECORD_SLOT_SIZE' not in header
    if tier == 'minimal':
        assert (PURE_INS in CompactLogRequiredRecords_Get(loaded)) == (estimator is None)
    FeatureTier_Apply(loaded, 'full' if bounded else 'compact', builtin_catalog)
    if bounded:
        assert {s.record: s.enabled for s in loaded.logging_streams if s.record in (PURE_INS, TELEMETRY_DIAG)} == {
            PURE_INS: retained_enabled, TELEMETRY_DIAG: retained_enabled}


@pytest.mark.parametrize('tier,legacy_profile', (('compact', 'all_streams'), ('minimal', 'sf6_minimal')))
@pytest.mark.parametrize('estimator', (None, SF6))
def test_legacy_load_and_save_preserve_choices_under_new_policy(builtin_catalog, tier, legacy_profile, estimator):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = estimator
    _Choices_Set(model, True)
    FeatureTier_Apply(model, tier, builtin_catalog)
    data = model.Dictionary_Get()
    data['format_version'] = 16
    data.pop('feature_tier_presets', None)
    data['build'].pop('feature_tier', None)
    data['build']['compact_mode'] = True
    data['build']['logging_profile'] = legacy_profile
    loaded = ProjectModel_Parse(data)
    assert loaded.build.feature_tier == tier
    saved = ProjectModel_Parse(loaded.Dictionary_Get())
    assert saved.Dictionary_Get() == loaded.Dictionary_Get()
    assert all(s.enabled for s in saved.logging_streams if s.record in (PURE_INS, TELEMETRY_DIAG))
    effective = {s.record: s.enabled for s in CompactLogStreams_Get(saved)}
    assert not effective[TELEMETRY_DIAG]
    assert effective[PURE_INS] == (estimator is None)
    FeatureTier_Apply(saved, 'full', builtin_catalog)
    assert all(s.enabled for s in CompactLogStreams_Get(saved) if s.record in (PURE_INS, TELEMETRY_DIAG))


@pytest.mark.parametrize('tier', ('compact', 'minimal'))
@pytest.mark.parametrize('estimator', (None, SF6))
def test_generated_decoder_matches_effective_policy_and_keeps_catalog(builtin_catalog, tier, estimator):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = estimator
    _Choices_Set(model, True)
    FeatureTier_Apply(model, tier, builtin_catalog)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    package = LogDecoderProfile_Render(model, builtin_catalog)
    assert LogDecoderPackage_Verify(package.content)
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        semantics = json.loads(archive.read('project_semantics.json'))
        catalog = json.loads(archive.read('record_catalog.json'))
    streams = {s['record']: s for s in semantics['logging_streams']}
    available = {s['record']: s for s in semantics['available_records']}
    views = {s['record']: s for s in semantics['record_views']}
    assert len(streams) == len(views) == len(catalog['records']) == 40
    assert not streams[TELEMETRY_DIAG]['enabled']
    assert streams[PURE_INS]['enabled'] == (estimator is None)
    for record in (TELEMETRY_DIAG, PURE_INS):
        if record == TELEMETRY_DIAG or estimator == SF6:
            assert not available[record]['available'] and not views[record]['available']
            assert available[record]['reason_code'] == 'logging.feature_tier.disabled'
        assert views[record]['logging']['enabled'] == streams[record]['enabled']


@pytest.mark.parametrize('tier', ('compact', 'minimal'))
def test_gui_sf6_pure_ins_switch_and_full_standard_restore(qapp, workspace_root, monkeypatch, tier):
    import tempfile
    from pathlib import Path
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.ui.main_window import MainWindow
    from silverstar_fccg.ui.widgets import StandardCheckBox, LockedCheckBox

    fixture_parent = workspace_root / '.work'
    fixture_parent.mkdir(exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='TierLoggingGui-', dir=fixture_parent))
    window = MainWindow(SettingsStore(fixture/'settings.ini'), service=FccgService(workspace_root))
    monkeypatch.setattr(window, '_Error_Show', lambda *args: pytest.fail(str(args)))
    try:
        _Choices_Set(window._model, False)
        window._model.logging_streams = [replace(s, enabled=True) if s.record == TELEMETRY_DIAG else s
                                         for s in window._model.logging_streams]
        window._Project_Refresh()
        profile = window.devices_page.feature_tier_combo
        profile.setCurrentIndex(profile.findData(tier))
        qapp.processEvents()

        def row(record):
            views = window.flight_configuration_page.Streams_Get()
            index = next(i for i, view in enumerate(views) if view.stream_id == record)
            check = window.flight_configuration_page.logging_table.cellWidget(index, 0).findChild(StandardCheckBox)
            return views[index], check

        for record in (PURE_INS, TELEMETRY_DIAG):
            view, check = row(record)
            assert not view.enabled and not view.editable and not view.available
            assert not check.isChecked() and not check.isEnabled()
            assert check.toolTip() == window._translator.Text_Get('logging.feature_tier.disabled')
        window.flight_configuration_page.Streams_SelectAllAvailable()
        window._ProjectModel_Sync()
        assert not row(PURE_INS)[0].enabled and not row(TELEMETRY_DIAG)[0].enabled
        estimator = window.flight_configuration_page.strategy_combos['estimator']
        estimator.setCurrentIndex(estimator.findData(None))
        qapp.processEvents()
        assert window._model.strategies['estimator'] is None
        view, check = row(PURE_INS)
        assert view.enabled and view.required and not view.editable
        assert isinstance(check, LockedCheckBox) and check.isChecked() and check.isEnabled()
        window.flight_configuration_page.Streams_KeepRequiredOnly()
        window._ProjectModel_Sync()
        saved = ProjectModel_Parse(window._model.Dictionary_Get())
        raw = {s.record: s.enabled for s in saved.logging_streams}
        assert not raw[PURE_INS] and raw[TELEMETRY_DIAG]
        assert next(s for s in CompactLogStreams_Get(saved) if s.record == PURE_INS).enabled
        estimator = window.flight_configuration_page.strategy_combos['estimator']
        estimator.setCurrentIndex(estimator.findData(SF6))
        qapp.processEvents()
        assert window._model.strategies['estimator'] == SF6
        assert not row(PURE_INS)[1].isChecked() and not row(PURE_INS)[1].isEnabled()
        profile.setCurrentIndex(profile.findData('full'))
        qapp.processEvents()
        assert not row(PURE_INS)[0].enabled and row(TELEMETRY_DIAG)[0].enabled
        assert row(PURE_INS)[1].isEnabled() and row(TELEMETRY_DIAG)[1].isEnabled()
        profile.setCurrentIndex(profile.findData('standard'))
        qapp.processEvents()
        assert not row(PURE_INS)[0].enabled and row(TELEMETRY_DIAG)[0].enabled
        assert row(PURE_INS)[1].isEnabled() and row(TELEMETRY_DIAG)[1].isEnabled()
    finally:
        window.close()
        qapp.processEvents()
