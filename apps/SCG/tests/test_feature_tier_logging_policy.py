from dataclasses import replace
from io import BytesIO
import json
import zipfile

import pytest

from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _LogSource_Render, LogDecoderProfile_Render
from silverstar_fccg.project.compact_logging import CompactLogStreams_Get, CompactLogRequiredRecords_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.feature_tiers import FeatureTier_Apply, FeatureTier_LogRecordAllowed
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
    assert effective[PURE_INS].enabled == (estimator is None and (bounded or retained_enabled))
    assert loaded.logging_streams == retained
    assert len(effective) == len(retained) == 40
    source = _LogSource_Render(loaded)
    for record in (PURE_INS, TELEMETRY_DIAG):
        assert f'{{{record}, {int(effective[record].enabled)}U,' in source
        prohibited = (record == TELEMETRY_DIAG and bounded) or (record == PURE_INS and estimator == SF6)
        assert (f'case {record}: return 0U;' in source) == prohibited
    if tier == 'compact':
        header = _FlightConfigHeader_Render(loaded, builtin_catalog)
        assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH                    56U' in header
        assert 'SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH                 16U' in header
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
    restored = {s.record: s.enabled for s in CompactLogStreams_Get(saved)}
    assert restored[TELEMETRY_DIAG] and restored[PURE_INS] == (estimator is None)
    assert all(s.enabled for s in saved.logging_streams if s.record in (PURE_INS, TELEMETRY_DIAG))


@pytest.mark.parametrize('tier', ('compact', 'minimal'))
@pytest.mark.parametrize('estimator', (None, SF6))
def test_generated_decoder_matches_effective_policy_and_keeps_catalog(builtin_catalog, tier, estimator):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = estimator
    _Choices_Set(model, True)
    FeatureTier_Apply(model, tier, builtin_catalog)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    from silverstar_fccg.project.validation import Project_Validate
    assert not [issue for issue in Project_Validate(model, builtin_catalog).issues
                if issue.code in ('logging_unavailable', 'logging_required')]
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
            assert available[record]['reason_code'] == ('logging.algorithm.disabled' if record == PURE_INS
                                                      else 'logging.feature_tier.disabled')
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
            assert check.toolTip() == window._translator.Text_Get('logging.algorithm.disabled' if record == PURE_INS
                                                                else 'logging.feature_tier.disabled')
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
        assert not row(PURE_INS)[1].isEnabled() and row(TELEMETRY_DIAG)[1].isEnabled()
        profile.setCurrentIndex(profile.findData('standard'))
        qapp.processEvents()
        assert not row(PURE_INS)[0].enabled and row(TELEMETRY_DIAG)[0].enabled
        assert not row(PURE_INS)[1].isEnabled() and row(TELEMETRY_DIAG)[1].isEnabled()
    finally:
        window.close()
        qapp.processEvents()


ALGORITHM_STREAMS = {
    None: (PURE_INS,),
    'silverstar.algorithm.estimator.kf6': tuple('FLIGHT_LOG_RECORD_' + n for n in
                                              ('ESTIMATOR', 'KF6_DIAGNOSTIC', 'KF6_FULL_P')),
    SF6: ('FLIGHT_LOG_RECORD_SF6_STATE', 'FLIGHT_LOG_RECORD_SF6_MEASUREMENT'),
    'silverstar.algorithm.estimator.eskf15': tuple('FLIGHT_LOG_RECORD_ESKF15_' + n for n in
        ('STATE', 'FULL_P_PART', 'INITIAL_STATE', 'INITIAL_P_PART', 'MEASUREMENT', 'BODY_INPUT')),
}
REPLAY_COMMON = tuple('FLIGHT_LOG_RECORD_' + n for n in
                     ('ESTIMATOR_STEP', 'GNSS_MEASUREMENT', 'BARO_MEASUREMENT', 'GNSS_RECOVERY', 'NAV_QUALITY'))


@pytest.mark.parametrize('tier', ('full', 'standard', 'compact', 'minimal'))
@pytest.mark.parametrize('estimator', tuple(ALGORITHM_STREAMS))
def test_first_release_four_algorithm_tier_generation_matrix(builtin_catalog, tier, estimator):
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
    from silverstar_fccg.project.feature_tiers import FeatureTier_StrategyAllowed
    from silverstar_fccg.project.logging import LoggingProfile_Reconcile
    model = ReferenceProject_Create(catalog=builtin_catalog)
    FeatureTier_Apply(model, tier, builtin_catalog)
    # Set after Apply to exercise prohibited retained selections, not its preset replacement.
    model.strategies['estimator'] = estimator
    owned = {record for group in ALGORITHM_STREAMS.values() for record in group}
    model.logging_streams = [replace(s, enabled=True) if s.record in owned else s for s in model.logging_streams]
    LoggingProfile_Reconcile(model, builtin_catalog)
    assert all(s.enabled for s in model.logging_streams if s.record in owned)
    for owner, records in ALGORITHM_STREAMS.items():
        for record in records:
            assert FeatureTier_LogRecordAllowed(model, record) == (owner == estimator)
    for record in REPLAY_COMMON:
        assert FeatureTier_LogRecordAllowed(model, record)
    if not FeatureTier_StrategyAllowed(model, estimator):
        with pytest.raises(SourceGraphError, match='prohibited'):
            SourceGraph_Resolve(model, builtin_catalog)
        return
    effective = {s.record: s.enabled for s in CompactLogStreams_Get(model)}
    source = _LogSource_Render(model)
    for owner, records in ALGORITHM_STREAMS.items():
        for record in records:
            assert FeatureTier_LogRecordAllowed(model, record) == (owner == estimator)
            assert effective[record] == (owner == estimator)
            assert (f'case {record}: return 0U;' in source) == (owner != estimator)
    for record in REPLAY_COMMON:
        assert FeatureTier_LogRecordAllowed(model, record)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    from silverstar_fccg.project.validation import Project_Validate
    assert not [issue for issue in Project_Validate(model, builtin_catalog).issues
                if issue.code in ('logging_unavailable', 'logging_required')]
    package = LogDecoderProfile_Render(model, builtin_catalog)
    assert LogDecoderPackage_Verify(package.content)
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        semantics = json.loads(archive.read('project_semantics.json'))
    available = {r['record']: r for r in semantics['available_records']}
    views = {r['record']: r for r in semantics['record_views']}
    streams = {r['record']: r for r in semantics['logging_streams']}
    for owner, records in ALGORITHM_STREAMS.items():
        for record in records:
            assert available[record]['available'] == (owner == estimator)
            assert views[record]['available'] == (owner == estimator)
            assert streams[record]['enabled'] == (owner == estimator)
            if owner != estimator:
                assert available[record]['reason_code'] == 'logging.algorithm.disabled'


@pytest.mark.parametrize('retained_enabled', (False, True))
def test_algorithm_switch_roundtrip_preserves_owned_choices(builtin_catalog, retained_enabled):
    from copy import deepcopy
    from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
    model = ReferenceProject_Create(catalog=builtin_catalog)
    owned = {record for records in ALGORITHM_STREAMS.values() for record in records}
    # Required ESKF replay records stay mandatory; exercise optional/recommended choices.
    optional = owned - {'FLIGHT_LOG_RECORD_ESKF15_' + n for n in
                       ('INITIAL_STATE', 'INITIAL_P_PART', 'MEASUREMENT', 'BODY_INPUT')}
    model.logging_streams = [replace(s, enabled=retained_enabled) if s.record in optional else s
                             for s in model.logging_streams]
    for estimator in (SF6, None, 'silverstar.algorithm.estimator.eskf15', 'silverstar.algorithm.estimator.kf6'):
        previous = deepcopy(model)
        model.strategies['estimator'] = estimator
        LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
        model = ProjectModel_Parse(model.Dictionary_Get())
        raw = {s.record: s.enabled for s in model.logging_streams}
        effective = {s.record: s.enabled for s in CompactLogStreams_Get(model)}
        assert all(raw[r] == retained_enabled for r in optional)
        for owner, records in ALGORITHM_STREAMS.items():
            for record in records:
                if record in optional:
                    assert effective[record] == (owner == estimator and retained_enabled)


def test_active_logging_validation_keeps_unavailable_and_cadence_errors(builtin_catalog):
    from silverstar_fccg.project.validation import Project_Validate
    from silverstar_fccg.project.logging import LogAvailability_Get, ProtocolLogDefinitions_Get
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies['estimator'] = SF6
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    # Removing a previously available producer must still reject active logging.
    definition = next(d for d in ProtocolLogDefinitions_Get(model, builtin_catalog)
                      if d.record == 'FLIGHT_LOG_RECORD_GNSS_NATIVE')
    assert LogAvailability_Get(definition, model, builtin_catalog).available
    model.device_instances = [d for d in model.device_instances if d.plugin != 'silverstar.device.gnss.neo_m9n']
    model.logging_streams = [replace(s, enabled=True) if s.record == 'FLIGHT_LOG_RECORD_GNSS_NATIVE' else s
                             for s in model.logging_streams]
    issues = Project_Validate(model, builtin_catalog).issues
    assert any(i.code == 'logging_unavailable' and 'GNSS_NATIVE' in i.message for i in issues)
    # Inactive retained algorithm records still have their cadence checked.
    model.logging_streams = [replace(s, period_us=1) if s.record == 'FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT' else s
                             for s in model.logging_streams]
    assert any(i.code == 'logging_cadence' and 'ESKF15_MEASUREMENT' in i.message
               for i in Project_Validate(model, builtin_catalog).issues)


def test_logging_protocol_restore_keeps_selected_algorithm_defaults(builtin_catalog):
    from copy import deepcopy
    from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
    model = ReferenceProject_Create(catalog=builtin_catalog)
    selection = model.protocols['logging']
    previous = deepcopy(model)
    model.protocols['logging'] = None
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    previous = deepcopy(model)
    model.protocols['logging'] = selection
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    assert next(s for s in CompactLogStreams_Get(model) if s.record == 'FLIGHT_LOG_RECORD_ESTIMATOR').enabled


def test_full_gui_views_follow_algorithm_ownership_without_enabling_new_strategies(qapp, workspace_root):
    import tempfile
    from pathlib import Path
    from silverstar_fccg.app.service import FccgService
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.project.logging import ProtocolLogDefinitions_Get
    from silverstar_fccg.ui.main_window import MainWindow
    fixture = Path(tempfile.mkdtemp(prefix='AlgorithmLogGui-', dir=workspace_root / '.work'))
    window = MainWindow(SettingsStore(fixture/'settings.ini'), service=FccgService(workspace_root))
    try:
        model = window._model
        owned = {r for records in ALGORITHM_STREAMS.values() for r in records}
        model.logging_streams = [replace(s, enabled=True) if s.record in owned else s for s in model.logging_streams]
        for estimator in ALGORITHM_STREAMS:
            model.strategies['estimator'] = estimator
            views = {v.stream_id: v for v in window._LoggingViews_Get(
                ProtocolLogDefinitions_Get(model, window._service.catalog), model)}
            for owner, records in ALGORITHM_STREAMS.items():
                for record in records:
                    assert views[record].available == (owner == estimator)
                    assert views[record].enabled == (owner == estimator)
                    if owner != estimator:
                        assert not views[record].editable
                        assert views[record].availability_reason == window._translator.Text_Get('logging.algorithm.disabled')
    finally:
        window.close()
        qapp.processEvents()
