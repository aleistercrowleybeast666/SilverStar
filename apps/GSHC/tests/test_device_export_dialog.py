"""Offscreen destination selection only; no MTP, serial or probe access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from unittest.mock import patch
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from services.i18n import I18n, Language
from ui.device_export_dialog import DeviceExportDialog, DeviceExportDestination_Choose


@pytest.fixture
def dialog(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / 'ui.ini'), QSettings.IniFormat)
    window = DeviceExportDialog(I18n(settings), [str(tmp_path / 'synthetic.jsonl')])
    yield window
    window.close()
    window.deleteLater()
    app.processEvents()


def test_directory_requires_destination_and_cancelled_browse_keeps_it(dialog, tmp_path):
    start = dialog.buttons.button(QDialogButtonBox.Ok)
    assert not start.isEnabled() and dialog.selection() is None
    dialog.path.setText(str(tmp_path))
    assert start.isEnabled() and dialog.selection() == ('directory', str(tmp_path))
    with patch('ui.device_export_dialog.QFileDialog.getExistingDirectory', return_value=''):
        dialog.browse.click()
    assert dialog.selection() == ('directory', str(tmp_path))


def test_phone_choice_does_not_reuse_directory_or_start_io(dialog, tmp_path):
    dialog.path.setText(str(tmp_path))
    dialog.target.setCurrentIndex(dialog.target.findData('mtp'))
    assert dialog.path.isHidden() and dialog.browse.isHidden()
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert dialog.selection() == ('mtp', '')
    dialog.target.setCurrentIndex(dialog.target.findData('directory'))
    assert not dialog.path.isHidden()
    assert dialog.selection() == ('directory', str(tmp_path))


@pytest.mark.parametrize('language', [Language.ZH_CN, Language.EN_US])
def test_cancel_never_returns_a_destination(dialog, language):
    dialog.i18n.set_language(language)
    with patch.object(QDialog, 'exec', return_value=QDialog.Rejected):
        assert DeviceExportDestination_Choose(dialog.i18n, ['synthetic.jsonl']) is None

