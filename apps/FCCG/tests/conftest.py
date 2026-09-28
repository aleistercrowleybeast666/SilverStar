from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import pytest
from PySide6.QtWidgets import QApplication

from silverstar_fccg.plugins.catalog import PluginCatalog


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application


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
