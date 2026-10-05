from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings


class SettingsStore:
    """Explicit repository-local settings; never uses a system/user registry scope."""

    def __init__(self, settings_path: Path) -> None:
        self.path = Path(settings_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._settings = QSettings(str(self.path), QSettings.Format.IniFormat)

    def Value_Get(self, key: str, default: Any = None) -> Any:
        return self._settings.value(key, default)

    def Value_Set(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)

