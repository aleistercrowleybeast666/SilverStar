"""Read-only manifest initialization facts; no fabricated device options."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.view_models import DeviceInstanceView
from silverstar_fccg.ui.widgets import CollapsibleSection

FIELDS = (
    "configure_on_boot",
    "profile",
    "output_rate_hz",
    "navigation_rate_hz",
    "target_baud",
    "accelerometer_range_g",
    "gyroscope_range_dps",
    "filter",
    "fifo",
    "readback",
    "dynamic_model",
    "constellations",
    "persistent_storage",
    "persistent_layer_default",
    "persist_if_changed",
    "conditional_persistence",
    "hardware_status",
)
RUNTIME_FIELDS = {
    "SYSTEM_IMU_OUTPUT_RATE_HZ": "output_rate_hz",
    "SYSTEM_GNSS_NAVIGATION_RATE_HZ": "navigation_rate_hz",
    "SYSTEM_GNSS_DYNAMIC_MODEL": "dynamic_model",
}
ENUMS = {
    "HARDWARE_UNVERIFIED": "unverified",
    "RAM": "ram",
    "none": "none",
    "portable_ground_test": "portable",
    "SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE": "portable",
    "SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G": "airborne4g",
}


def InitializationSection_Create(
    instance: DeviceInstanceView,
    translator: Translator,
    *,
    expanded: bool = False,
) -> CollapsibleSection:
    section = CollapsibleSection(
        translator.Text_Get("device.init.title"), expanded=expanded
    )
    section.setObjectName("deviceInitialization_" + instance.instance_id)
    layout = QVBoxLayout()
    note = QLabel(translator.Text_Get("device.init.fixed_profile"))
    note.setWordWrap(True)
    note.setProperty("muted", True)
    layout.addWidget(note)
    form = QFormLayout()
    values = dict(instance.initialization)
    for defaults in instance.runtime_defaults.values():
        for symbol, field in RUNTIME_FIELDS.items():
            if symbol in defaults:
                values.setdefault(field, defaults[symbol])
    for field in FIELDS:
        value = values.get(field)
        if value is None and field not in (
            "readback",
            "filter",
            "fifo",
            "hardware_status",
        ):
            continue
        if isinstance(value, dict):
            text = str(value.get(translator.language, value.get("en_US", "")))
        elif type(value) is bool:
            text = translator.Text_Get(
                "device.init.enabled" if value else "device.init.disabled"
            )
        elif value is None:
            text = translator.Text_Get("device.init.undeclared")
        elif str(value) in ENUMS:
            text = translator.Text_Get("device.init." + ENUMS[str(value)])
        else:
            text = str(value)
        label = QLabel(text)
        label.setObjectName(
            "deviceInitialization_" + instance.instance_id + "_" + field
        )
        label.setWordWrap(True)
        form.addRow(QLabel(translator.Text_Get("device.init." + field)), label)
    layout.addLayout(form)
    section.BodyLayout_Set(layout)
    return section
