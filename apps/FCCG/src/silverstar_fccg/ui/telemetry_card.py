"""Shared telemetry device details and action geometry."""

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QWidget


def TelemetryName_Display(name: str) -> str:
    for suffix in (" (hardware unverified)", " (unverified)", " (validated)",
                   " (current configuration)", "（硬件未验证）", "（未验证）",
                   "（已验证）", "（当前配置）"):
        if name.casefold().endswith(suffix.casefold()):
            return name[:-len(suffix)]
    return name


def TelemetryDetails_Add(form: QFormLayout, translator, vendor: str,
                         model: str, chipset: str) -> None:
    for key, value in (("device.detail.vendor", vendor),
                       ("device.detail.model", model),
                       ("device.detail.chipset", chipset)):
        label = QLabel(value or "—")
        label.setWordWrap(True)
        form.addRow(QLabel(translator.Text_Get(key)), label)


def TelemetryRemoveButton_Add(form: QFormLayout, button: QPushButton) -> None:
    button.setFixedWidth(120)
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addStretch(1)
    layout.addWidget(button)
    form.addRow(QLabel(), container)
