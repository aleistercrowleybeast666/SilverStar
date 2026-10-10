"""Test-only paths: avoid user settings and OS decoder-cache writes."""
import pytest


@pytest.fixture(autouse=True)
def closeout_private_paths(tmp_path, monkeypatch):
    from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
    monkeypatch.setattr(DecoderProfileCache, 'DefaultRoot_Get',
                        staticmethod(lambda: tmp_path / 'dc'))
    from PySide6.QtCore import QSettings
    from silverstar_flp.ui import main_window
    monkeypatch.setattr(main_window, 'QSettings', lambda *args:
                        QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
