from copy import deepcopy
from dataclasses import replace
import json

import pytest

from silverstar_fccg.project.model import ProjectModel_Save
from silverstar_fccg.project.radio_variants import (
    EBYTE_VARIANTS, LEGACY_MODULE, RADIO_PLUGIN, FlightRadioConfiguration_Get,
)
from test_f103_ground_reference import _GroundF103Model_Get
from test_ground_radio_editor import _Wait
from test_scg_ui_metadata_hotfix import window


def _Configure(window):
    # Initialize the board metadata through the application's normal reconcile
    # before measuring module edits, rather than counting initial board setup.
    window._model = window._service.ProjectConfiguration_Reconcile(
        _GroundF103Model_Get(window._service.catalog)).model
    errors = []
    window._Error_Show = lambda *args: errors.append(args)
    window._Project_Refresh()
    return errors


def _SaveReopen(window, path):
    # Hardware reconciliation returns a native tuple for timebase errors.
    # Compare the complete JSON document across save, load and GUI refresh.
    data = json.loads(json.dumps(window._model.Dictionary_Get()))
    ProjectModel_Save(window._model, path, window._service.policy)
    loaded = window._service.Project_Open(path)
    assert loaded.Dictionary_Get() == data
    window._model = loaded
    window._Project_Refresh()
    assert json.loads(json.dumps(window._model.Dictionary_Get())) == data
    return data


@pytest.mark.parametrize("module", list(EBYTE_VARIANTS))
def test_flight_all_variants_selector_add_delete_save_power_and_bindings(qapp, window, tmp_path, module):
    errors = _Configure(window)
    before = deepcopy(window._model)
    combo = window.devices_page.device_combos["telemetry0"]
    choices = {tuple(combo.itemData(i)) for i in range(combo.count())}
    assert {(RADIO_PLUGIN, identity) for identity in EBYTE_VARIANTS} <= choices
    combo.setCurrentIndex(combo.findData((RADIO_PLUGIN, module)))
    nominal = EBYTE_VARIANTS[module].nominal_output_dbm
    _Wait(qapp, lambda: FlightRadioConfiguration_Get(
        window._model, window._model.DeviceInstance_Get("telemetry0")) == (module, nominal))
    # Reconciliation may allocate the newly required PA pins, while retaining
    # every existing binding and the other endpoint's serialized configuration.
    assert all(window._model.resource_assignments.get(key) == value
               for key, value in before.resource_assignments.items())
    assert json.loads(json.dumps(window._model.Dictionary_Get()["ground_target"])) == json.loads(
        json.dumps(before.Dictionary_Get()["ground_target"]))
    assert window.air_link_page.fields["frequency_hz"].isEnabled()
    assert window.air_link_page.flight_tx_power.value() == nominal
    power = window.devices_page.radio_power_combos["telemetry0"]
    assert {power.itemData(i) for i in range(power.count()) if power.model().item(i).isEnabled()} == {nominal}
    assert power.currentData() == nominal
    if module != LEGACY_MODULE:
        assert window._model.Dictionary_Get()["format_version"] == 16
    # Loading a stale saved output retains it; the folded control repairs only its owner.
    window._model.device_instances = [replace(item, module_variant=module, tx_power_dbm=nominal-1)
        if item.instance_id == "telemetry0" else item for item in window._model.device_instances]
    window._Project_Refresh()
    power = window.devices_page.radio_power_combos["telemetry0"]
    assert power.currentData() == nominal-1
    assert not power.model().item(power.currentIndex()).isEnabled()
    power.setCurrentIndex(power.findData(nominal))
    _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0").tx_power_dbm == nominal)
    assert window._model.flight_tx_power_dbm == before.flight_tx_power_dbm
    _SaveReopen(window, tmp_path/"selected.ssproject")
    primary_bindings = {key:value for key,value in window._model.resource_assignments.items()
                        if key.startswith("telemetry0:")}
    window.devices_page.add_buttons["telemetry"].click()
    _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry1") is not None)
    added = window._model.DeviceInstance_Get("telemetry1")
    assert FlightRadioConfiguration_Get(window._model, added) == (module, nominal)
    assert all(window._model.resource_assignments[key] == value for key,value in primary_bindings.items())
    window._model.resource_assignments["telemetry1:radio_bus"] = "PLATFORM_SPI_1"
    window._Project_Refresh()
    secondary = window._model.DeviceInstance_Get("telemetry1")
    secondary_bindings = {key:value for key,value in window._model.resource_assignments.items()
                          if key.startswith("telemetry1:")}
    window.devices_page.remove_buttons["telemetry0"].click()
    _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0") is None)
    assert window._model.DeviceInstance_Get("telemetry1") == secondary
    assert window._model.air_link.flight_radio_instance == "telemetry1"
    assert not any(key.startswith("telemetry0:") for key in window._model.resource_assignments)
    assert all(window._model.resource_assignments.get(key) == value
               for key,value in secondary_bindings.items())
    # Freed pins can fill previously unbound requirements under the existing
    # auto-assignment policy; record them before checking save and re-add.
    secondary_bindings = {key:value for key,value in window._model.resource_assignments.items()
                          if key.startswith("telemetry1:")}
    _SaveReopen(window, tmp_path/"survivor.ssproject")
    window.devices_page.add_buttons["telemetry"].click()
    _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0") is not None)
    assert window._model.air_link.flight_radio_instance == "telemetry1"
    assert FlightRadioConfiguration_Get(window._model, window._model.DeviceInstance_Get("telemetry0")) == (module, nominal)
    assert {key:value for key,value in window._model.resource_assignments.items()
            if key.startswith("telemetry1:")} == secondary_bindings
    assert not errors, errors


@pytest.mark.parametrize("module", list(EBYTE_VARIANTS))
def test_ground_all_variants_selector_add_delete_save_power_and_requirements(qapp, window, tmp_path, module):
    errors = _Configure(window)
    before = deepcopy(window._model)
    editor = window.ground_target_page.radio_instances_editor
    combo = editor.rows["radio0"]["selection"]
    combo.setCurrentIndex(combo.findData((RADIO_PLUGIN, module)))
    nominal = EBYTE_VARIANTS[module].nominal_output_dbm
    _Wait(qapp, lambda: window._model.ground_target.module_variant == module
          and window._model.ground_target.tx_power_dbm == nominal)
    ground = window._model.ground_target
    assert ground.resource_assignments == before.ground_target.resource_assignments
    assert window._model.device_instances == before.device_instances
    required = set(window.ground_target_page.assignments)
    if EBYTE_VARIANTS[module].external_frontend:
        assert {"radio0:radio_rx_en", "radio0:radio_tx_en"} <= required
    else:
        assert not any(key.endswith(("radio_rx_en", "radio_tx_en")) for key in required)
    power = editor.rows["radio0"]["tx_power_dbm"]
    assert {power.itemData(i) for i in range(power.count()) if power.model().item(i).isEnabled()} == {nominal}
    assert power.currentData() == nominal
    ground = window._model.ground_target
    radios = tuple(replace(radio, tx_power_dbm=nominal-1)
                   if radio.instance_id == ground.active_radio_instance else radio
                   for radio in ground.radio_instances)
    window._model.ground_target = replace(ground, radio_instances=radios, tx_power_dbm=nominal-1)
    window._Project_Refresh()
    power = editor.rows["radio0"]["tx_power_dbm"]
    assert power.currentData() == nominal-1
    assert not power.model().item(power.currentIndex()).isEnabled()
    power.setCurrentIndex(power.findData(nominal))
    _Wait(qapp, lambda: window._model.ground_target.tx_power_dbm == nominal)
    _SaveReopen(window, tmp_path/"ground_selected.ssproject")
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    assert window._model.ground_target.radio_instances[1].module_variant == module
    assert window._model.ground_target.radio_instances[1].tx_power_dbm == nominal
    assert not any(key.startswith("radio1:") for key in window._model.ground_target.resource_assignments)
    window._model.ground_target = replace(window._model.ground_target, resource_assignments={
        **window._model.ground_target.resource_assignments, "radio1:radio_bus":"PLATFORM_SPI_1"})
    window._Project_Refresh()
    secondary = window._model.ground_target.radio_instances[1]
    editor.rows["radio0"]["remove"].click()
    _Wait(qapp, lambda: window._model.ground_target.active_radio_instance == "radio1")
    assert window._model.ground_target.radio_instances == (secondary,)
    assert window._model.ground_target.resource_assignments == {"radio1:radio_bus":"PLATFORM_SPI_1"}
    _SaveReopen(window, tmp_path/"ground_survivor.ssproject")
    editor.add_button.click()
    _Wait(qapp, lambda: len(window._model.ground_target.radio_instances) == 2)
    assert [radio.instance_id for radio in window._model.ground_target.radio_instances] == ["radio1","radio0"]
    assert window._model.ground_target.active_radio_instance == "radio1"
    board = window._service.catalog.Component_Get(window._model.ground_target.board)
    fixed = {"radio0:" + role.key.removeprefix("telemetry:"): role.default
             for role in board.resource_roles
             if role.fixed and role.key.startswith("telemetry:")}
    assert window._model.ground_target.resource_assignments == {
        "radio1:radio_bus": "PLATFORM_SPI_1", **fixed}
    assert not errors, errors


def test_legacy_m12_refresh_language_save_reopen_does_not_promote(window, tmp_path):
    _Configure(window)
    before = window._model.Dictionary_Get()
    assert before["format_version"] == 14
    for language in ("en_US", "zh_CN"):
        window.Language_Apply(language)
        assert window._model.Dictionary_Get() == before
    assert window._model.DeviceInstance_Get("telemetry0").module_variant == ""
    assert window._model.DeviceInstance_Get("telemetry0").tx_power_dbm is None
    assert _SaveReopen(window, tmp_path/"legacy.ssproject") == json.loads(json.dumps(before))


def test_delete_final_flight_selection_does_not_revive_a_device(qapp, window, tmp_path):
    _Configure(window)
    window.devices_page.remove_buttons["telemetry0"].click()
    _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0") is None)
    assert not window.devices_page.radio_power_combos
    assert tuple(window.devices_page.device_combos["telemetry0"].currentData()) == ("","")
    assert not any(key.startswith("telemetry0:") for key in window._model.resource_assignments)
    _SaveReopen(window, tmp_path/"no_flight_radio.ssproject")
    assert window._model.DeviceInstance_Get("telemetry0") is None


@pytest.mark.parametrize("endpoint", ["flight","ground"])
def test_pa_to_m12_removes_only_own_frontend_bindings_and_changes_nominal(qapp, window, endpoint):
    _Configure(window)
    if endpoint == "flight":
        combo = window.devices_page.device_combos["telemetry0"]
        combo.setCurrentIndex(combo.findData((RADIO_PLUGIN,"e28_2g4m27sx")))
        _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0").module_variant == "e28_2g4m27sx")
        window._model.resource_assignments.update({
            "telemetry0:radio_rx_en":"PLATFORM_GPIO_1", "telemetry0:radio_tx_en":"PLATFORM_GPIO_2"})
        window._Project_Refresh()
        before = dict(window._model.resource_assignments)
        combo = window.devices_page.device_combos["telemetry0"]
        combo.setCurrentIndex(combo.findData((RADIO_PLUGIN,LEGACY_MODULE)))
        _Wait(qapp, lambda: window._model.DeviceInstance_Get("telemetry0").module_variant == LEGACY_MODULE)
        assert window._model.resource_assignments == {key:value for key,value in before.items()
            if key not in {"telemetry0:radio_rx_en","telemetry0:radio_tx_en"}}
        assert FlightRadioConfiguration_Get(window._model, window._model.DeviceInstance_Get("telemetry0")) == (LEGACY_MODULE,12)
    else:
        editor = window.ground_target_page.radio_instances_editor
        editor.rows["radio0"]["selection"].setCurrentIndex(
            editor.rows["radio0"]["selection"].findData((RADIO_PLUGIN,"e28_2g4m27sx")))
        _Wait(qapp, lambda: window._model.ground_target.module_variant == "e28_2g4m27sx")
        ground = window._model.ground_target
        window._model.ground_target = replace(ground, resource_assignments={
            **ground.resource_assignments,"radio0:radio_rx_en":"PLATFORM_GPIO_1",
            "radio0:radio_tx_en":"PLATFORM_GPIO_2"})
        window._Project_Refresh()
        before = dict(window._model.ground_target.resource_assignments)
        editor.rows["radio0"]["selection"].setCurrentIndex(
            editor.rows["radio0"]["selection"].findData((RADIO_PLUGIN,LEGACY_MODULE)))
        _Wait(qapp, lambda: window._model.ground_target.module_variant == LEGACY_MODULE)
        assert window._model.ground_target.resource_assignments == {key:value for key,value in before.items()
            if key not in {"radio0:radio_rx_en","radio0:radio_tx_en"}}
        assert window._model.ground_target.tx_power_dbm == 12
