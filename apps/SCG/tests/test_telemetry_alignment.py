from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import (
    GroundRadioConfigurations_Get, GroundTargetConfiguration, ProjectModel_Parse,
)
from silverstar_fccg.project.ground_radios import GroundRadiosConfiguration_Apply
from silverstar_fccg.project.air_link import GroundTargetIssues_Get
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.core.workspace import WorkspacePolicy
from test_f103_ground_reference import _GroundF103Model_Get
from test_ground_radio_editor import _Wait
from test_scg_ui_metadata_hotfix import window


def _FixedRadio0Bindings_Get(window):
    board = window._service.catalog.Component_Get(window._model.ground_target.board)
    return {"radio0:" + role.key.removeprefix("telemetry:"): role.default
            for role in board.resource_roles
            if role.fixed and role.key.startswith("telemetry:")}


def test_ground_layout_and_power_ownership(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    page = window.ground_target_page
    row = page.radio_instances_editor.rows["radio0"]
    assert page.enabled.isHidden()
    assert window._model.ground_target.enabled
    assert row["title"].text() == window._translator.Text_Get("device.instance.telemetry", index=0)
    ground = window._model.ground_target
    assert tuple(row["selection"].currentData()) == (ground.radio_plugin, ground.module_variant)
    assert row["tx_power_dbm"].parent() is page.radio_instances_editor.power_editor
    assert page.radio_instances_editor.power_editor.parent() is window.air_link_page.air_link_group.body
    assert window.air_link_page.ground_tx_power.isHidden()
    assert not window.air_link_page.air_link_group.Expanded_Is()
    assert page.radio_instances_editor.add_button.text() == window.devices_page.add_buttons["telemetry"].text()
    assert set(row) == {"title", "selection", "tx_power_dbm", "remove"}


def test_delete_primary_keeps_secondary_identity_bindings_and_order(qapp, window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    ground = window._model.ground_target
    radio = GroundRadioConfigurations_Get(ground)[0]
    ground = GroundRadiosConfiguration_Apply(
        ground, (radio, replace(radio, instance_id="radio1", tx_power_dbm=10)), "radio0")
    ground = replace(ground, resource_assignments={
        **ground.resource_assignments, "radio1:radio_bus": "PLATFORM_SPI_1"})
    window._model.ground_target = ground
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    editor.rows["radio0"]["remove"].click()
    _Wait(qapp, lambda: window._model.ground_target.active_radio_instance == "radio1")
    survivor = window._model.ground_target
    assert [r.instance_id for r in survivor.radio_instances] == ["radio1"]
    assert survivor.resource_assignments == {"radio1:radio_bus": "PLATFORM_SPI_1"}
    assert survivor.tx_power_dbm == 10
    assert set(editor.rows) == {"radio1"}
    assert ProjectModel_Parse(window._model.Dictionary_Get()).ground_target == survivor
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    updated = window._model.ground_target
    assert [r.instance_id for r in updated.radio_instances] == ["radio1", "radio0"]
    assert updated.active_radio_instance == "radio1"
    assert updated.resource_assignments == {
        **survivor.resource_assignments, **_FixedRadio0Bindings_Get(window)}
    assert all(r.tx_power_dbm == 10 for r in updated.radio_instances)
    window._AirLink_Change("preamble_symbols", window._model.air_link.preamble_symbols)
    assert window._model.ground_target.resource_assignments == updated.resource_assignments


def test_delete_final_and_add_recovers_fixed_board_defaults(qapp, window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    editor.rows["radio0"]["remove"].click()
    _Wait(qapp, lambda: not window._model.ground_target.radio_plugin)
    assert not window._model.ground_target.resource_assignments
    assert not editor._radios
    assert tuple(editor.rows["radio0"]["selection"].currentData()) == ("", "")
    assert not editor.rows["radio0"]["remove"].isEnabled()
    editor.add_button.click()
    _Wait(qapp, lambda: bool(window._model.ground_target.radio_instances))
    assert [r.instance_id for r in window._model.ground_target.radio_instances] == ["radio0"]
    assert window._model.ground_target.resource_assignments == _FixedRadio0Bindings_Get(window)


def test_folded_per_module_power_roundtrip(qapp, window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    editor = window.ground_target_page.radio_instances_editor
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    ground = window._model.ground_target
    window._model.ground_target = GroundRadiosConfiguration_Apply(
        ground, (ground.radio_instances[0], replace(ground.radio_instances[1], tx_power_dbm=10)),
        ground.active_radio_instance)
    window._Project_Refresh()
    before = deepcopy(window._model.ground_target)
    combo = editor.rows["radio1"]["tx_power_dbm"]
    value = next(combo.itemData(i) for i in range(combo.count())
                 if combo.model().item(i).isEnabled() and combo.itemData(i) != before.radio_instances[1].tx_power_dbm)
    combo.setCurrentIndex(combo.findData(value))
    _Wait(qapp, lambda: window._model.ground_target.radio_instances[1].tx_power_dbm == value)
    ground = window._model.ground_target
    assert ground.radio_instances[0] == before.radio_instances[0]
    assert ground.tx_power_dbm == before.tx_power_dbm
    assert ground.resource_assignments == before.resource_assignments
    assert ProjectModel_Parse(window._model.Dictionary_Get()).ground_target == ground


def test_direct_selection_is_catalog_driven_and_atomic(qapp, window):
    ground = _GroundF103Model_Get(window._service.catalog).ground_target
    contract = window._service.catalog.Component_Get(ground.radio_plugin).radio
    modules = {**contract.modules, "variant27": {
        **next(iter(contract.modules.values())), "display_name": "E28 27 dBm",
        "supported_tx_powers_dbm": [27]}}
    editor = window.ground_target_page.radio_instances_editor
    editor.configurationChanged.disconnect()
    received = []
    editor.configurationChanged.connect(lambda radios, active: received.append((radios, active)))
    availability = {(ground.radio_plugin, ground.module_variant): (False, "unavailable"),
                    (ground.radio_plugin, "variant27"): (True, "")}
    editor.Configuration_Set(ground, (("E28", ground.radio_plugin, False, "unavailable"),),
                             {ground.radio_plugin: SimpleNamespace(modules=modules)}, availability)
    combo = editor.rows["radio0"]["selection"]
    selection = (ground.radio_plugin, "variant27")
    assert combo.findData(selection) >= 0
    assert combo.model().item(combo.findData(selection)).isEnabled()
    assert editor.add_button.isEnabled()
    combo.setCurrentIndex(combo.findData(selection))
    _Wait(qapp, lambda: bool(received))
    radios, active = received[0]
    assert active == "radio0"
    assert radios[0].plugin == ground.radio_plugin
    assert radios[0].module_variant == "variant27"
    assert radios[0].tx_power_dbm == 27
    updated = replace(ground, radio_instances=(replace(radios[0], tx_power_dbm=ground.tx_power_dbm),),
                      module_variant="variant27")
    editor.Configuration_Set(updated, (("E28", ground.radio_plugin, True, ""),),
                             {ground.radio_plugin: SimpleNamespace(modules=modules)})
    power = editor.rows["radio0"]["tx_power_dbm"]
    assert {power.itemData(i) for i in range(power.count()) if power.model().item(i).isEnabled()} == {27}
    assert power.currentData() == ground.tx_power_dbm
    assert not power.model().item(power.currentIndex()).isEnabled()


def test_legacy_disabled_load_enables_target_without_losing_values(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._model.ground_target = replace(window._model.ground_target, enabled=False)
    restored = ProjectModel_Parse(window._model.Dictionary_Get())
    before = restored.ground_target
    window._model = restored
    window._Project_Refresh()
    assert window._model.ground_target == replace(before, enabled=True)


def test_flight_scope_ignores_unconfigured_enabled_ground(builtin_catalog, workspace_root, tmp_path):
    model = ReferenceProject_Create("TelemetryFlightScope", catalog=builtin_catalog)
    model.ground_target = GroundTargetConfiguration(enabled=True)
    assert GroundTargetIssues_Get(model, builtin_catalog)
    result = TargetGeneration_Apply(
        model, builtin_catalog, WorkspacePolicy(workspace_root), tmp_path / "flight", TargetScope.FLIGHT)
    assert result.targets == ("Flight_Controller",)
    assert (result.project_root / "Flight_Controller/Makefile").is_file()
    assert not (result.project_root / "Ground_Station/Makefile").exists()
    assert ProjectModel_Parse(model.Dictionary_Get()).ground_target.enabled


def test_ground_scope_rejects_missing_resources_before_writes(builtin_catalog, workspace_root, tmp_path):
    model = _GroundF103Model_Get(builtin_catalog)
    model.ground_target = replace(model.ground_target, resource_assignments={})
    with pytest.raises(ValueError):
        TargetGeneration_Apply(
            model, builtin_catalog, WorkspacePolicy(workspace_root), tmp_path / "ground", TargetScope.GROUND)
    assert not (tmp_path / "ground/Ground_Station/Makefile").exists()
