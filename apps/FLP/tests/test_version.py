from __future__ import annotations

import tomllib
from pathlib import Path

from silverstar_flp import __version__ as package_version
from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.version import __version__ as compatibility_version


def test_version_has_one_runtime_authority_and_dynamic_packaging_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert PRODUCT_NAME == "SilverStar FLP"
    assert __version__ == compatibility_version == package_version == (root.parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    assert "version" not in payload["project"]
    assert "version" in payload["project"]["dynamic"]
    assert payload["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "silverstar_flp.app.version.__version__"
    )


def test_about_dialog_uses_runtime_version() -> None:
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.plugin_manager import AboutDialog

    app = QApplication.instance() or QApplication([])
    dialog = AboutDialog(Translator("en_US"))
    assert __version__ in dialog.version_label.text()
    dialog.close()
    app.processEvents()
