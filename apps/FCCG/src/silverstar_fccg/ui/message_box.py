from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QPushButton

from silverstar_fccg.core.i18n import Translator


def MessageBoxButtons_Localize(
    box: QMessageBox, translator: Translator
) -> None:
    for standard, key in (
        (QMessageBox.StandardButton.Ok, "action.ok"),
        (QMessageBox.StandardButton.Yes, "action.yes"),
        (QMessageBox.StandardButton.No, "action.no"),
        (QMessageBox.StandardButton.Cancel, "action.cancel"),
    ):
        button = box.button(standard)
        if button is not None:
            button.setText(translator.Text_Get(key))

    button_box = box.findChild(QDialogButtonBox)
    if button_box is None:
        return
    detail_button = next(
        (
            button
            for button in box.findChildren(QPushButton)
            if button_box.buttonRole(button)
            == QDialogButtonBox.ButtonRole.ActionRole
        ),
        None,
    )
    if detail_button is None:
        return

    expanded = {"value": False}
    detail_button.setText(translator.Text_Get("action.show_details"))

    def DetailsLabel_Toggle(_checked: bool = False) -> None:
        expanded["value"] = not expanded["value"]
        detail_button.setText(
            translator.Text_Get(
                "action.hide_details"
                if expanded["value"]
                else "action.show_details"
            )
        )

    detail_button.clicked.connect(DetailsLabel_Toggle)
