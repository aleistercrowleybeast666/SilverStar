"""Schema declarations and the authoritative model parser share these boundaries."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re

import pytest
from silverstar_fccg.project.model import GroundRadioConfiguration, ProjectModel_Parse, ProjectModelError
from test_f103_ground_reference import _GroundF103Model_Get


@pytest.fixture
def document(builtin_catalog):
    return _GroundF103Model_Get(builtin_catalog).Dictionary_Get()


@pytest.fixture(scope="module")
def schema():
    return json.loads((Path(__file__).resolve().parents[1] / "schemas/project.schema.json").read_text(encoding="utf8"))


def test_schema_and_parser_keep_format14_without_optional_fields(schema, document):
    ground = schema["properties"]["ground_target"]
    optional = {"radio_instances", "active_radio_instance", "tx_led_resource", "rx_led_resource",
                "tx_led_active_high", "rx_led_active_high", "activity_led_pulse_ms"}
    assert optional <= ground["properties"].keys()
    assert not optional & set(ground["required"])
    assert document["format_version"] == 14
    assert not optional & document["ground_target"].keys()
    assert ProjectModel_Parse(document).Dictionary_Get() == document
    assert ground["additionalProperties"] is False
    condition = schema["allOf"][0]
    assert condition["if"]["properties"]["format_version"]["const"] == 15
    assert set(condition["then"]["properties"]["ground_target"]["required"]) == {"radio_instances", "active_radio_instance"}
    assert condition["else"]["properties"]["ground_target"]["not"]["anyOf"] == [
        {"required": ["radio_instances"]}, {"required": ["active_radio_instance"]}]


@pytest.mark.parametrize("count", [1, 4])
def test_schema_and_parser_support_bounded_format15_radios(schema, document, count):
    model = ProjectModel_Parse(document)
    ground = model.ground_target
    model.ground_target = replace(ground, radio_instances=tuple(GroundRadioConfiguration(
        f"radio{index}", ground.radio_plugin, ground.module_variant, ground.tx_power_dbm)
        for index in range(count)))
    data = model.Dictionary_Get()
    assert data["format_version"] == 15
    reopened = ProjectModel_Parse(data)
    assert reopened.Dictionary_Get() == data
    field = schema["properties"]["ground_target"]["properties"]["radio_instances"]
    assert (field["minItems"], field["maxItems"]) == (1, 4)
    item = schema["$defs"]["groundRadio"]
    assert set(item["required"]) == {"instance_id", "plugin", "module_variant", "tx_power_dbm"}
    assert item["additionalProperties"] is False


@pytest.mark.parametrize("count", [0, 5])
def test_parser_rejects_radio_counts_outside_schema_bounds(schema, document, count):
    ground = document["ground_target"]
    document["format_version"] = 15
    ground["radio_instances"] = [dict(instance_id=f"radio{i}", plugin=ground["radio_plugin"],
         module_variant=ground["module_variant"], tx_power_dbm=ground["tx_power_dbm"]) for i in range(count)]
    ground["active_radio_instance"] = "radio0"
    with pytest.raises(ProjectModelError, match="1..4"):
        ProjectModel_Parse(document)


@pytest.mark.parametrize("key,bad", [("tx_led_resource", "bad/pin"), ("rx_led_resource", None),
    ("tx_led_active_high", 1), ("rx_led_active_high", "false"),
    ("activity_led_pulse_ms", 0), ("activity_led_pulse_ms", 201), ("activity_led_pulse_ms", True)])
def test_schema_led_types_and_limits_match_parser(schema, document, key, bad):
    field = schema["properties"]["ground_target"]["properties"][key]
    if key.endswith("_resource"):
        assert field["type"] == "string" and re.fullmatch(field["pattern"], "LED_PB6")
        assert re.fullmatch(field["pattern"], "")
        assert not isinstance(bad, str) or not re.fullmatch(field["pattern"], bad)
    elif key.endswith("_active_high"):
        assert field["type"] == "boolean"
    else:
        assert (field["type"], field["minimum"], field["maximum"]) == ("integer", 1, 200)
    document["ground_target"][key] = bad
    with pytest.raises(ProjectModelError, match="ground_target"):
        ProjectModel_Parse(document)
