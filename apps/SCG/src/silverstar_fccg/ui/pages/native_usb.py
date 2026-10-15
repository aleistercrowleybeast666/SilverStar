"""Experimental native USB controls, separated from Flight/Ground admission."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class NativeUsbPanel(QGroupBox):
    actionRequested = Signal(str)

    def __init__(self, language: str) -> None:
        super().__init__()
        self._reference = None
        self._language = language
        layout = QVBoxLayout(self)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.source = QLabel("—")
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        buttons = QHBoxLayout()
        self.buttons = {}
        for action in ("inspect", "refresh", "prepare", "compile", "analyze"):
            button = QPushButton()
            button.clicked.connect(lambda _checked=False, selected=action: self.actionRequested.emit(selected))
            self.buttons[action] = button
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(80)
        self.details.setMaximumHeight(190)
        layout.addWidget(self.details)
        self.Language_Set(language)
        self._Buttons_Update()

    def Language_Set(self, language: str) -> None:
        self._language = language
        zh = language == "zh_CN"
        self.setTitle("原生 USB CDC（实验）" if zh else "Native USB CDC (experimental)")
        self.notice.setText(
            "选择 CubeMX 已生成 CDC 的完整工程。另行生成适配工程；原工程负责时钟、引脚和 USB 初始化。软件构建不代表准入或上板验证。"
            if zh else "Select a complete CubeMX CDC project. Derivatives use a separate directory; native clocks, pins and USB initialization remain authoritative. Compilation does not establish admission or board validation.")
        labels = (("选择并检查", "重新核验", "生成独立工程", "ARM 编译", "静态分析编译") if zh else
                  ("Select and inspect", "Recheck", "Prepare separate project", "ARM compile", "Analyzer compile"))
        for button, label in zip(self.buttons.values(), labels, strict=True):
            button.setText(label)

    def _Buttons_Update(self) -> None:
        for action in ("refresh", "prepare"):
            self.buttons[action].setEnabled(self._reference is not None)
        for action in ("compile", "analyze"):
            self.buttons[action].setEnabled(bool(self._reference and self._reference.output_root))

    def Reference_Set(self, reference) -> None:
        if reference == self._reference:
            return
        self._reference = reference
        self.source.setText(reference.native_root if reference else "—")
        self.details.setPlainText(("已保存引用，尚未重新核验" if self._language == "zh_CN" else
            "Saved reference; not rechecked") if reference else "")
        self._Buttons_Update()

    def Outcome_Set(self, outcome) -> None:
        self.Reference_Set(outcome.reference)
        plan = outcome.plan
        lines = [f"{outcome.result.value}: {plan.part} / {plan.stack}",
            str(plan.capabilities.get("automatic_integration", {}).get("status", "")),
            *plan.reasons, *plan.capabilities.get("configuration_findings", []), *plan.review]
        if outcome.reference and outcome.reference.output_root:
            lines.append(outcome.reference.output_root)
        if outcome.receipt:
            lines += [outcome.receipt["status"], "Power of Ten: " + outcome.receipt["power10"],
                      "Critical contracts / stack / WCET: NOT PROVEN", "Hardware: NOT TESTED"]
        self.details.setPlainText("\n".join(lines))

    def Failure_Set(self, error: object) -> None:
        self.details.setPlainText(str(error))
        for action in ("prepare", "compile", "analyze"):
            self.buttons[action].setEnabled(False)
