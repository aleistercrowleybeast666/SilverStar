from dataclasses import replace
import json

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import HardwareResource, ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.ground_activity import GroundActivityLedIssues_Get
from test_f103_ground_reference import _GroundF103Model_Get
from test_scg_ui_metadata_hotfix import window


@pytest.fixture
def model(workspace_root):
    return _GroundF103Model_Get(FccgService(workspace_root).catalog)


def _Output_Add(model, identity="LED_OUTPUT", pin="PB6"):
    ground = model.ground_target
    resource = HardwareResource(identity, "gpio_output", {"physical_pin": pin})
    model.ground_target = replace(ground,
        hardware=replace(ground.hardware, resources=(*ground.hardware.resources, resource)))
    return model.ground_target


def test_unused_led_defaults_keep_legacy_dictionary(model):
    data = model.Dictionary_Get()
    assert not any(key in data["ground_target"] for key in
                   ("tx_led_resource", "rx_led_resource", "tx_led_active_high",
                    "rx_led_active_high", "activity_led_pulse_ms"))
    reopened = ProjectModel_Parse(data)
    assert reopened.Dictionary_Get() == data
    assert reopened.ground_target.tx_led_resource == reopened.ground_target.rx_led_resource == ""
    assert reopened.ground_target.activity_led_pulse_ms == 40
    assert not GroundActivityLedIssues_Get(reopened.ground_target)


@pytest.mark.parametrize("pulse", [1, 40, 200])
def test_shared_output_roundtrip_and_bounds(model, pulse):
    ground = _Output_Add(model)
    model.ground_target = replace(ground, tx_led_resource="LED_OUTPUT", rx_led_resource="LED_OUTPUT",
                                 tx_led_active_high=True, rx_led_active_high=True, activity_led_pulse_ms=pulse)
    assert not GroundActivityLedIssues_Get(model.ground_target)
    reopened = ProjectModel_Parse(model.Dictionary_Get())
    assert reopened.ground_target == model.ground_target


@pytest.mark.parametrize("key,value", [
    ("activity_led_pulse_ms", 0), ("activity_led_pulse_ms", 201),
    ("activity_led_pulse_ms", True), ("activity_led_pulse_ms", "40"),
    ("tx_led_active_high", 1), ("rx_led_active_high", "false"),
    ("tx_led_resource", None), ("rx_led_resource", "bad/pin")])
def test_invalid_led_fields_are_rejected(model, key, value):
    data = model.Dictionary_Get()
    data["ground_target"][key] = value
    with pytest.raises(ProjectModelError, match="ground_target"):
        ProjectModel_Parse(data)


def test_led_rejects_input_unknown_and_radio_claims(model):
    ground = model.ground_target
    for identity, expected in (("DOES_NOT_EXIST", "GROUND_LED_OUTPUT_UNBOUND"),
                               ("PLATFORM_GPIO_2", "GROUND_LED_OUTPUT_UNBOUND"),
                               ("PLATFORM_GPIO_0", "GROUND_LED_RESOURCE_CONFLICT")):
        errors = GroundActivityLedIssues_Get(replace(ground, tx_led_resource=identity))
        assert expected in {issue.code for issue in errors}


@pytest.mark.parametrize("role,pin", [("spi", "PA5"), ("uart", "PA9")])
def test_led_rejects_physical_interface_pin_aliases(model, role, pin):
    ground = _Output_Add(model, pin=pin)
    identity = "PLATFORM_SPI_1" if role == "spi" else ground.pc_resource
    resources = tuple(replace(resource, metadata={**resource.metadata, "pins": {"test": pin}})
                      if resource.resource_id == identity else resource
                      for resource in ground.hardware.resources)
    ground = replace(ground, hardware=replace(ground.hardware, resources=resources),
                     tx_led_resource="LED_OUTPUT")
    assert "GROUND_LED_RESOURCE_CONFLICT" in {issue.code for issue in GroundActivityLedIssues_Get(ground)}


def test_shared_gpio_requires_equal_polarity(model):
    ground = _Output_Add(model)
    ground = replace(ground, tx_led_resource="LED_OUTPUT", rx_led_resource="LED_OUTPUT", rx_led_active_high=True)
    assert "GROUND_LED_POLARITY_CONFLICT" in {issue.code for issue in GroundActivityLedIssues_Get(ground)}


def test_led_gui_keeps_defaults_until_explicit_binding(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    _Output_Add(window._model)
    window._Project_Refresh()
    controls = window.ground_target_page.activity_led_controls
    assert controls["tx_led_resource"].currentData() == controls["rx_led_resource"].currentData() == ""
    assert controls["activity_led_pulse_ms"].value() == 40
    assert not controls["tx_led_active_high"].isChecked()
    assert controls["tx_led_resource"].findData("PLATFORM_GPIO_2") < 0
    combo = controls["tx_led_resource"]
    combo.setCurrentIndex(combo.findData("LED_OUTPUT"))
    assert window._model.ground_target.tx_led_resource == "LED_OUTPUT"
    controls["tx_led_active_high"].setChecked(True)
    assert window._model.ground_target.tx_led_active_high
    before = window._model.ground_target
    window.Language_Apply("en_US")
    assert window._model.ground_target == before
    assert window.ground_target_page.activity_led_controls["tx_led_resource"].currentData() == "LED_OUTPUT"
