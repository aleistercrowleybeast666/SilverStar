from __future__ import annotations

from pathlib import Path

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.theme import Stylesheet_Get


def test_theme_styles_primary_shell_and_tabs() -> None:
    light = Stylesheet_Get("light")
    dark = Stylesheet_Get("dark")
    for stylesheet, brand, accent in (
        (light, "#123A78", "#2F6FED"),
        (dark, "#0B2447", "#3B82F6"),
    ):
        assert brand in stylesheet
        assert accent in stylesheet
        assert "QFrame#headerBar" in stylesheet
        assert "QListWidget#navigation::item:selected" in stylesheet
        assert "QTabBar::tab:selected" in stylesheet
        assert "QProgressBar::chunk" in stylesheet


def test_settings_use_explicit_local_ini_path(tmp_path: Path) -> None:
    settings_path = tmp_path / ".fccg" / "settings.ini"
    store = SettingsStore(settings_path)
    store.Value_Set("language", "en_US")
    assert store.path == settings_path.resolve()
    assert store.Value_Get("language") == "en_US"

