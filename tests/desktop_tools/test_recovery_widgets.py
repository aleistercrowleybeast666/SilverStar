"""Real Qt widgets, synthetic logs and temporary files; no hardware or native dialogs."""
from pathlib import Path
from types import SimpleNamespace as NS
import os
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings

@pytest.fixture(scope='module')
def app():
    value = QApplication.instance() or QApplication([])
    yield value

def capture(widget, name):
    if os.environ.get('SILVERSTAR_QA_DIRECTORY'):
        widget.grab().save(str(Path(os.environ['SILVERSTAR_QA_DIRECTORY']) / name))

def test_recovery_panel_is_display_only_and_exports_snapshot(app, tmp_path, monkeypatch):
    from ui import recovery_panel
    from services.recovery_position import RecoveryPosition
    panel = recovery_panel.RecoveryPanel()
    state = NS(recovery=RecoveryPosition(), connected=False, recovery_current_session=2)
    panel.Render(state)
    assert not panel.export.isEnabled()
    state.recovery.Position_Observe(1, 1000, (3, 4, 8), 1, source='synthetic recorded AIR')
    panel.Render(state)
    assert panel.export.isEnabled()
    assert 'UNKNOWN' in panel.text.toPlainText()
    panel.confirm.setChecked(True)
    assert '36.9 deg' in panel.text.toPlainText()
    assert 'retained / disconnected' in panel.text.toPlainText()
    output = tmp_path / 'recovery.txt'
    monkeypatch.setattr(recovery_panel.QFileDialog, 'getSaveFileName', lambda *a: (str(output), 'Text'))
    panel._Export()
    assert 'synthetic recorded AIR' in output.read_text(encoding='utf-8')
    panel.resize(1000, 500)
    panel.show()
    app.processEvents()
    capture(panel, 'recovery-panel.png')
    panel.deleteLater()
