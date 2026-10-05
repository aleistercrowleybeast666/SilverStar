"""Shared telemetry device details and action geometry."""

from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton


def TelemetryName_Display(name: str) -> str:
    for suffix in (" (hardware unverified)", " (unverified)", " (validated)",
                   " (current configuration)", "（硬件未验证）", "（未验证）",
                   "（已验证）", "（当前配置）"):
        if name.casefold().endswith(suffix.casefold()):
            return name[:-len(suffix)]
    return name


def TelemetryDetails_Add(form: QFormLayout, translator, chipset: str) -> None:
    label = QLabel(chipset or "—")
    label.setWordWrap(True)
    form.addRow(QLabel(translator.Text_Get("device.detail.rf_chip")), label)


def TelemetryRemoveButton_Add(form: QFormLayout, button: QPushButton) -> None:
    form.addRow(button)
