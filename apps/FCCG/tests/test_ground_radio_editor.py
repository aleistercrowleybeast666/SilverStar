from dataclasses import replace
import time

import pytest
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.model import GroundRadioConfigurations_Get, ProjectModel_Parse, ProjectModelError
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from test_f103_ground_reference import _GroundF103Model_Get
from test_scg_ui_metadata_hotfix import window


def _Wait(qapp, predicate):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert predicate()


def test_legacy_single_ground_refresh_does_not_promote_or_rebind(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    before = window._model.Dictionary_Get()
    window._Project_Refresh()
    for language in ("zh_CN", "en_US"):
        window.Language_Apply(language)
        assert window._model.Dictionary_Get() == before
        assert not window._model.ground_target.radio_instances
        assert not window.ground_target_page.radio.isHidden()
        assert window.ground_target_page.radio_instances_editor.initial_instance.isHidden()
    assert window._model.Dictionary_Get()["format_version"] == 14


def test_ground_editor_order_initial_binding_and_reopen(qapp, window, monkeypatch):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    errors = []
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    before = dict(window._model.ground_target.resource_assignments)
    editor = window.ground_target_page.radio_instances_editor
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    ground = window._model.ground_target
    assert [r.instance_id for r in ground.radio_instances] == ["radio0", "radio1"]
    assert ground.resource_assignments == before
    assert ground.active_radio_instance == "radio0"
    assert not window.ground_target_page.generate_button.isEnabled()
    assert "GROUND_RADIO_RUNTIME_UNAVAILABLE" not in {i.code for i in GroundTargetIssues_Get(window._model, window._service.catalog)}
    assert set(editor.rows) == {"radio0", "radio1"}
    assert not window.ground_target_page.assignments["radio1:radio_bus"].currentData()
    editor.initial_instance.setCurrentIndex(editor.initial_instance.findData("radio1"))
    _Wait(qapp, lambda: window._model.ground_target.active_radio_instance == "radio1")
    editor.rows["radio1"]["up"].click()
    _Wait(qapp, lambda: window._model.ground_target.radio_instances[0].instance_id == "radio1")
    assert window._model.ground_target.resource_assignments == before
    data = window._model.Dictionary_Get()
    assert data["format_version"] == 15
    assert ProjectModel_Parse(data).Dictionary_Get() == data
    window.Language_Apply("en_US")
    assert window._model.Dictionary_Get() == data
    # Explicitly bind one secondary resource; deleting that instance only releases its keys.
    assignment = window.ground_target_page.assignments["radio1:radio_bus"]
    assignment.setCurrentIndex(assignment.findData("PLATFORM_SPI_1"))
    _Wait(qapp, lambda: window._model.ground_target.resource_assignments.get("radio1:radio_bus") == "PLATFORM_SPI_1")
    assert all(window._model.ground_target.resource_assignments[key] == value for key,value in before.items())
    editor.rows["radio1"]["remove"].click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 1)
    assert window._model.ground_target.resource_assignments == before
    assert window._model.ground_target.active_radio_instance == "radio0"
    assert not errors, errors


def test_ground_editor_caps_instances_at_four(qapp, window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    for count in (2, 3, 4):
        editor.add_button.click()
        _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == count)
    assert not editor.add_button.isEnabled()
    assert len(set(r.instance_id for r in window._model.ground_target.radio_instances)) == 4
    assert all(not key.startswith(("radio1:","radio2:","radio3:")) for key in window._model.ground_target.resource_assignments)


def test_ground_runtime_gate_stops_generation_before_payload_writes(builtin_catalog, tmp_path):
    from silverstar_fccg.core.workspace import WorkspacePolicy
    model = _GroundF103Model_Get(builtin_catalog)
    ground = model.ground_target
    radio = GroundRadioConfigurations_Get(ground)[0]
    model.ground_target = GroundRadiosConfiguration_Apply(ground,
        (radio, replace(radio, instance_id="radio1")), "radio0")
    from copy import copy
    unavailable_catalog = copy(builtin_catalog)
    unavailable_catalog._components = dict(builtin_catalog._components)
    core = builtin_catalog.Component_Get("silverstar.core.ground.0_1_0")
    assert core.metadata["ground_radio_instances_ready"] is True
    unavailable_catalog._components[core.component_id] = replace(core,
        metadata={key: value for key,value in core.metadata.items() if key != "ground_radio_instances_ready"})
    with pytest.raises(ValueError, match="Multiple Ground radio instances"):
        TargetGeneration_Apply(model, unavailable_catalog, WorkspacePolicy(tmp_path), tmp_path, TargetScope.GROUND)
    assert not (tmp_path / "Ground_Station/Makefile").exists()


@pytest.mark.parametrize("case", ["duplicate", "missing_active", "mismatched_snapshot", "format14_fields"])
def test_format15_parser_keeps_identity_and_snapshot_boundaries(builtin_catalog, case):
    model = _GroundF103Model_Get(builtin_catalog)
    ground = model.ground_target
    radio = GroundRadioConfigurations_Get(ground)[0]
    model.ground_target = GroundRadiosConfiguration_Apply(ground, (radio, replace(radio, instance_id="radio1")), "radio0")
    data = model.Dictionary_Get();target = data["ground_target"]
    if case == "duplicate":
        target["radio_instances"][1]["instance_id"] = "radio0"
    elif case == "missing_active":
        target["active_radio_instance"] = "missing_radio"
    elif case == "mismatched_snapshot":
        target["radio_instances"][0]["tx_power_dbm"] += 1
    else:
        data["format_version"] = 14
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(data)


def test_ground_plugin_change_only_releases_its_own_bindings(builtin_catalog):
    ground = _GroundF103Model_Get(builtin_catalog).ground_target
    radio = GroundRadioConfigurations_Get(ground)[0]
    ground = GroundRadiosConfiguration_Apply(ground, (radio, replace(radio, instance_id="radio1")), "radio0")
    ground = replace(ground, resource_assignments={**ground.resource_assignments, "radio1:radio_bus": "SPI_OTHER"})
    changed = GroundRadiosConfiguration_Apply(ground,
        (radio, replace(ground.radio_instances[1], plugin="silverstar.device.telemetry.unavailable")), "radio0")
    assert changed.resource_assignments == {key: value for key,value in ground.resource_assignments.items() if key.startswith("radio0:")}


def test_ground_power_choices_only_allow_declared_values(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    ground = window._model.ground_target
    radio = GroundRadioConfigurations_Get(ground)[0]
    manifest = window._service.catalog.Component_Get(radio.plugin)
    allowed = set(manifest.radio.modules[radio.module_variant]["supported_tx_powers_dbm"])
    stale = max(allowed) + 1
    window._model.ground_target = GroundRadiosConfiguration_Apply(ground,
        (radio, replace(radio, instance_id="radio1", tx_power_dbm=stale)), "radio0")
    window._Project_Refresh()
    combo = window.ground_target_page.radio_instances_editor.rows["radio1"]["tx_power_dbm"]
    assert combo.currentData() == stale
    assert not combo.model().item(combo.currentIndex()).isEnabled()
    assert {combo.itemData(index) for index in range(combo.count()) if combo.model().item(index).isEnabled()} == allowed
    assert window._model.ground_target.radio_instances[1].tx_power_dbm == stale
