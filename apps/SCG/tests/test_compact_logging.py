from dataclasses import replace
import re

import pytest

from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _LogSource_Render
from silverstar_fccg.project.compact_logging import CompactLogStreams_Get, CompactLogProfileErrors_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.generation_state import ProjectGenerationFingerprint_Get


def test_profile_roundtrip_preserves_all_stream_choices(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    original = model.Dictionary_Get()
    assert "logging_profile" not in original["build"]
    retained = list(model.logging_streams)
    model.build = replace(model.build, compact_mode=True, logging_profile="sf6_minimal")
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    loaded = ProjectModel_Parse(model.Dictionary_Get())
    assert loaded.build.logging_profile == "sf6_minimal"
    active = {s.record: s for s in CompactLogStreams_Get(loaded)}
    assert not active["FLIGHT_LOG_RECORD_ESTIMATOR"].enabled
    assert active["FLIGHT_LOG_RECORD_SF6_STATE"].enabled
    assert active["FLIGHT_LOG_RECORD_SF6_MEASUREMENT"].enabled
    assert loaded.logging_streams == retained
    before_digest = ProjectGenerationFingerprint_Get(loaded)
    loaded.build = replace(loaded.build, logging_profile="all_streams")
    assert ProjectGenerationFingerprint_Get(loaded) != before_digest
    model.build = replace(model.build, compact_mode=False, logging_profile="all_streams")
    model.strategies = original["components"]["strategies"]
    assert model.Dictionary_Get() == original


def test_profile_requires_explicit_compact_sf6_logging_and_releases_other_algorithms(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, logging_profile="sf6_minimal")
    assert CompactLogProfileErrors_Get(model)
    model.build = replace(model.build, compact_mode=True)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    assert not CompactLogProfileErrors_Get(model)
    model.protocols["logging"] = None
    assert CompactLogProfileErrors_Get(model)
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.build = replace(model.build, compact_mode=True, logging_profile="sf6_minimal")
    result = ProjectConfiguration_Reconcile(model, builtin_catalog)
    assert result.model.build.logging_profile == "all_streams"
    assert result.model.strategies["estimator"] == model.strategies["estimator"]


def test_profile_has_fixed_slots_proven_from_c_object_sizes(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    normal = _FlightConfigHeader_Render(model, builtin_catalog)
    assert "SYSTEM_LOG_RECORD_SLOT_SIZE" not in normal
    model.build = replace(model.build, compact_mode=True, logging_profile="sf6_minimal")
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    assert re.search(r"#define SYSTEM_LOG_RECORD_SLOT_SIZE\s+168U", header)
    assert re.search(r"#define SYSTEM_LOG_ESTIMATOR_SLOT_SIZE\s+96U", header)
    source = _LogSource_Render(model)
    assert "offsetof(FlightLogRecord, payload) + sizeof(((FlightLogRecord *)0)->payload.initial_state)" in source
    assert "case FLIGHT_LOG_RECORD_ESTIMATOR: return 0U" in source
    assert "case FLIGHT_LOG_RECORD_NAV_QUALITY: return 0U" in source
    assert "case FLIGHT_LOG_RECORD_GNSS_RECOVERY: return 0U" in source
    assert len(CompactLogStreams_Get(model)) == len(model.logging_streams) == 40


def test_unknown_profile_rejected(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog).Dictionary_Get()
    model["build"]["logging_profile"] = "typo"
    with pytest.raises(ProjectModelError, match="logging_profile"):
        ProjectModel_Parse(model)


def test_manual_gui_profile_preserves_streams_and_restores_other_algorithms(workspace_root, qapp, monkeypatch):
    import tempfile
    from pathlib import Path
    from silverstar_fccg.core.settings import SettingsStore
    from silverstar_fccg.ui.main_window import MainWindow

    fixture_parent = workspace_root / ".work"
    fixture_parent.mkdir(exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix="CompactLogGui-", dir=fixture_parent))
    window = MainWindow(SettingsStore(fixture / "settings.ini"))
    monkeypatch.setattr(window, "_Error_Show", lambda *args: pytest.fail(str(args)))
    try:
        window._model = window._service.ReferenceProject_Create("CompactLogGui")
        window._Project_Refresh()
        estimator = window.flight_configuration_page.strategy_combos["estimator"]
        estimator.setCurrentIndex(estimator.findData("silverstar.algorithm.estimator.sf6"))
        qapp.processEvents()
        window.build_page.compact_mode_checkbox.setChecked(True)
        qapp.processEvents()
        retained = list(window._model.logging_streams)
        profile = window.build_page.compact_log_profile_combo
        assert profile.isEnabled()
        profile.setCurrentIndex(profile.findData("sf6_minimal"))
        qapp.processEvents()
        window._ProjectModel_Sync()
        assert window._model.logging_streams == retained
        loaded = ProjectModel_Parse(window._model.Dictionary_Get())
        assert loaded.build.logging_profile == "sf6_minimal"
        views = window.flight_configuration_page.Streams_Get()
        assert not next(view for view in views if view.stream_id == "FLIGHT_LOG_RECORD_ESTIMATOR").enabled
        assert next(view for view in views if view.stream_id == "FLIGHT_LOG_RECORD_SF6_STATE").enabled
        profile.setCurrentIndex(profile.findData("all_streams"))
        qapp.processEvents()
        assert window._model.logging_streams == retained
        profile.setCurrentIndex(profile.findData("sf6_minimal"))
        qapp.processEvents()
        estimator = window.flight_configuration_page.strategy_combos["estimator"]
        estimator.setCurrentIndex(estimator.findData("silverstar.algorithm.estimator.kf6"))
        qapp.processEvents()
        assert window._model.strategies["estimator"] == "silverstar.algorithm.estimator.kf6"
        assert window._model.build.logging_profile == "all_streams"
    finally:
        window.close()
