from dataclasses import replace
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_scg_ui_metadata_hotfix import window


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_folds_preserve_values_bindings_and_language(qapp, window, language):
    before = window._model.Dictionary_Get()
    air = window.air_link_page.air_link_group
    other = window.devices_page.other_group
    assert not air.Expanded_Is() and not other.Expanded_Is()
    QTest.mouseClick(air.toggle_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(other.toggle_button, Qt.MouseButton.LeftButton)
    assert air.Expanded_Is() and other.Expanded_Is()
    window.Language_Apply(language)
    assert air.Expanded_Is() and other.Expanded_Is()
    assert air.toggle_button.text() == window._translator.Text_Get("group.air_link")
    assert other.toggle_button.text() == window._translator.Text_Get("group.other_sensors")
    window._Project_Refresh()
    assert air.Expanded_Is() and other.Expanded_Is()
    assert window._model.Dictionary_Get() == before
    # Unsupported technologies stay unavailable when their settings are folded.
    combo = window.air_link_page.fields["radio_technology"]
    assert not combo.model().item(combo.findData("packet")).isEnabled()


def test_telemetry_labels_follow_real_instance_ids_after_deletion(window):
    page = window.devices_page
    instances = list(page._instances)
    telemetry = next(item for item in instances if item.component_class == "telemetry")
    instances = [item for item in instances if item.component_class != "telemetry"]
    instances += [replace(telemetry, instance_id="telemetry2"), replace(telemetry, instance_id="telemetry3")]
    page.Configuration_Set(page._components, instances, page._device_availability)
    for index in (2, 3):
        label = page.telemetry_form.labelForField(page.device_combos[f"telemetry{index}"])
        assert label.text() == page._translator.Text_Get("device.instance.telemetry", index=index)
    page.Configuration_Set(page._components, instances[:-1], page._device_availability)
    assert page.telemetry_form.labelForField(page.device_combos["telemetry2"]).text().endswith("2")


def test_wireless_choices_use_installed_radio_contracts(window):
    contracts = tuple(manifest.radio for manifest in window._service.catalog.Type_Get("device") if manifest.radio is not None)
    window.air_link_page.RadioOptions_Set(contracts)
    matching = tuple(radio for radio in contracts if radio.technology == window._model.air_link.radio_technology
                     and radio.family == window._model.air_link.radio_family)
    assert matching
    allowed = {rate for radio in matching for rate in radio.coding_rates}
    for rate in sorted(allowed):
        link = replace(window._model.air_link, coding_rate=rate)
        window.air_link_page.Configuration_Set(link, ())
        combo = window.air_link_page.fields["coding_rate"]
        assert combo.currentData() == rate
        assert combo.model().item(combo.currentIndex()).isEnabled()
    window.air_link_page.Configuration_Set(replace(window._model.air_link, coding_rate="unsupported"), ())
    combo = window.air_link_page.fields["coding_rate"]
    assert combo.currentData() == "unsupported" and not combo.model().item(combo.currentIndex()).isEnabled()
