from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from silverstar_fccg.plugins.catalog import PluginCatalog


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _QtTestWindows_Dispose(qapp):
    """Release each test's widgets before global theme changes in later tests."""
    previous = set(qapp.topLevelWidgets())
    yield
    for widget in set(qapp.topLevelWidgets()) - previous:
        if shiboken6.isValid(widget):
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture(scope="session")
def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def builtin_catalog(workspace_root: Path) -> PluginCatalog:
    catalog = PluginCatalog(
        workspace_root / "plugins" / "builtin",
        workspace_root / "plugins" / "installed",
    )
    catalog.Scan()
    return catalog
