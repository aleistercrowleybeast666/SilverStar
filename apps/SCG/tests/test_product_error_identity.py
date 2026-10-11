from __future__ import annotations

import logging
import sys

import pytest
from PySide6.QtWidgets import QMessageBox

from silverstar_fccg.app import application
from silverstar_fccg.app.version import PRODUCT_NAME


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_startup_error_retains_failure_and_displays_scg(
    qapp, monkeypatch, tmp_path, language
) -> None:
    dialogs = []
    marker = "isolated startup regression; no hardware"
    prior_identity = (
        qapp.organizationName(), qapp.applicationName(), qapp.applicationVersion()
    )
    root_logger = logging.getLogger()
    prior_handlers = tuple(root_logger.handlers)
    prior_level = root_logger.level
    monkeypatch.setattr(application, "QApplication", lambda arguments: qapp)
    monkeypatch.setattr(application, "WorkspaceRoot_Get", lambda: tmp_path)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)

    def startup_failure(workspace):
        assert workspace == tmp_path
        raise RuntimeError(marker)

    def capture_dialog(box):
        assert not box.isVisible()
        dialogs.append((box.windowTitle(), box.text(), box.detailedText(), box.icon()))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(application, "FccgService", startup_failure)
    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    try:
        assert application.main(["--lang", language, "--theme", "light"]) == 1
        assert len(dialogs) == 1
        title, text, details, icon = dialogs[0]
        assert title == PRODUCT_NAME == "SilverStar SCG"
        assert "SilverStar SCG" in text and "FCCG" not in text
        assert details == marker and icon == QMessageBox.Icon.Critical
        log = tmp_path / ".fccg" / "logs" / "silverstar_fccg.log"
        assert marker in log.read_text(encoding="utf-8")
    finally:
        for handler in tuple(root_logger.handlers):
            if handler not in prior_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.setLevel(prior_level)
        qapp.setOrganizationName(prior_identity[0])
        qapp.setApplicationName(prior_identity[1])
        qapp.setApplicationVersion(prior_identity[2])
