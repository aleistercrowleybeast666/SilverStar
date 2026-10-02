"""Synthetic mission-folder acceptance. This is not TF/hardware validation."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from silverstar_flp.core.i18n import Translator
from silverstar_flp.decoder_profiles.discovery import (
    DecoderProfileCache, DiscoveryLimits, TaskDirectoryScanner,
)
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.export_settings import ImportDialog
from tests.sslog_synthetic import Event_Payload, START_TIMESTAMP_US, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    DESCRIPTOR_RECORD_TYPE, IMU_RECORD_TYPE, _CalibrationNonePayload_Build,
    _DescriptorPayload_Build, _ImuPayload_Build, _Package_Write,
)


@pytest.fixture
def mission_tree(tmp_path):
    root = tmp_path / 'SYNTHETIC_project'
    missions = root / 'Log' / 'missions'
    missions.mkdir(parents=True)
    (root / 'SilverStar.ssproject').write_text('{}', encoding='utf-8')
    decoder, hashes = _Package_Write(root / 'SYNTHETIC.ssdecoder')
    logs = []
    for mission in ('000011', '000012'):
        directory = missions / mission
        directory.mkdir()
        builder = SyntheticSslogBuilder()
        builder.Record_Add(DESCRIPTOR_RECORD_TYPE, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3)
        builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
        builder.Record_Add(0x02, Event_Payload(0x03), START_TIMESTAMP_US)
        for index in range(3):
            timestamp = START_TIMESTAMP_US + index * 10000
            builder.Record_Add(IMU_RECORD_TYPE, _ImuPayload_Build(1, 0, timestamp, (1.0, 2.0, 3.0)), timestamp)
        logs.append(builder.File_Write(directory / 'flight.sslog'))
        (directory / 'snap00.ssobj').write_bytes(b'SYNTHETIC snapshot, not a flight stream')
        (directory / 'manifest.json').write_text('{}', encoding='utf-8')
    legacy = root / 'Log' / 'SS0001.BIN'
    legacy.write_bytes(logs[0].read_bytes())
    return root, missions, decoder, (*logs, legacy)


def test_project_root_recurses_missions_and_keeps_old_bin(mission_tree):
    root, _, decoder, logs = mission_tree
    # Generated firmware paths must stay out of project-root discovery.
    vendor = root / 'Flight_Controller' / 'Drivers'
    vendor.mkdir(parents=True)
    (vendor / 'not_a_log.BIN').write_bytes(b'vendor')
    (vendor / 'not_a_decoder.ssdecoder').write_bytes(b'vendor')
    discovery = TaskDirectoryScanner().Scan(root)
    assert set(discovery.log_paths) == {path.resolve() for path in logs}
    assert discovery.decoder_package_paths == (decoder.resolve(),)
    assert discovery.scanned_file_count == 4


def test_project_recursion_obeys_depth_file_and_byte_limits(mission_tree):
    root, _, _, logs = mission_tree
    shallow = TaskDirectoryScanner(DiscoveryLimits(maximum_depth=0)).Scan(root)
    assert shallow.log_paths == (logs[-1].resolve(),)
    assert shallow.limit_reached
    assert TaskDirectoryScanner(DiscoveryLimits(maximum_file_count=1)).Scan(root).limit_reached
    assert TaskDirectoryScanner(DiscoveryLimits(maximum_total_file_bytes=1)).Scan(root).limit_reached


def test_root_folder_and_single_mission_find_exact_pairs_without_mutating_sources(mission_tree, tmp_path):
    root, missions, decoder, logs = mission_tree
    source_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / 'cache'))
    for selected, expected in ((root, logs), (missions, logs[:2]), (logs[1].parent, (logs[1],))):
        discovery = coordinator.PairDiscovery_Run(selected)
        assert {pair.log_path for pair in discovery.pairs} == {path.resolve() for path in expected}
        for pair in discovery.pairs:
            result = coordinator.Open(LogOpenRequest(log_path=pair.log_path, decoder_package_path=pair.decoder_package_path))
            assert result.match_mode == 'exact_generation_profile'
            assert result.source_package_path == decoder.resolve()
            assert result.dataset.source_path == pair.log_path
            assert len(result.dataset.Records_Get('IMU_NATIVE')) == 3
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in source_hashes.items())


def test_same_name_candidates_show_mission_paths_and_require_selection(mission_tree, tmp_path):
    application = QApplication.instance() or QApplication([])
    root, _, _, logs = mission_tree
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / 'cache'))
    discovery = coordinator.PairDiscovery_Run(root / 'Log' / 'missions')
    dialog = ImportDialog(Translator('zh_CN'))
    dialog.Folder_Set(root / 'Log' / 'missions')
    dialog.PairDiscovery_Set(discovery)
    try:
        assert dialog.candidate_combo.count() == 2
        assert dialog.candidate_combo.currentIndex() == -1
        labels = [dialog.candidate_combo.itemText(index) for index in range(2)]
        assert '000011' in labels[0] and '000012' in labels[1]
        assert 'flight.sslog' in labels[0] and labels[0] != labels[1]
        assert str(logs[1].resolve()) in dialog.candidate_combo.itemData(1, Qt.ItemDataRole.ToolTipRole)
        opened = []
        dialog.importRequested.connect(lambda log, decoder: opened.append((log, decoder)))
        dialog.candidate_combo.setCurrentIndex(1)
        dialog.import_button.click()
        assert opened == [(logs[1].resolve(), discovery.pairs[1].decoder_package_path)]
        dialog.folder_path_edit.setText(str(root / 'Log'))
        assert dialog.candidate_combo.count() == 0
    finally:
        dialog.reject()
        application.processEvents()


def test_single_mission_candidate_can_be_opened_directly(mission_tree, tmp_path):
    application = QApplication.instance() or QApplication([])
    _, _, _, logs = mission_tree
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / 'cache'))
    dialog = ImportDialog(Translator('en_US'))
    dialog.PairDiscovery_Set(coordinator.PairDiscovery_Run(logs[1].parent))
    assert dialog.candidate_combo.currentIndex() == 0
    dialog.reject()
    application.processEvents()


def test_actual_import_file_filters_and_directory_picker(mission_tree, monkeypatch):
    application = QApplication.instance() or QApplication([])
    _, missions, _, logs = mission_tree
    dialog = ImportDialog(Translator('zh_CN'))
    filters = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (filters.append(args[3]) or str(logs[1]), ''))
    dialog.browse_button.click()
    # Manual controls are disabled until manual mode is selected.
    dialog.source_type_combo.setCurrentIndex(dialog.source_type_combo.findData('manual'))
    dialog.browse_button.click()
    assert '*.sslog' in filters[-1] and '*.bin' in filters[-1]
    dialog.source_type_combo.setCurrentIndex(dialog.source_type_combo.findData('folder_search'))
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(missions))
    dialog.folder_browse_button.click()
    assert Path(dialog.folder_path_edit.text()) == missions
    selected = []
    dialog.folderSearchRequested.connect(selected.append)
    dialog.folder_search_button.click()
    assert selected == [missions]
    dialog.reject()
    application.processEvents()


def test_directory_open_and_drop_share_pair_discovery(mission_tree, monkeypatch):
    application = QApplication.instance() or QApplication([])
    root, missions, _, _ = mission_tree
    window = MainWindow(builtin_registry())
    selected, errors = [], []
    monkeypatch.setattr(window, '_FolderSearch_Start', selected.append)
    monkeypatch.setattr(window, '_Error_Show', errors.append)
    try:
        window.Path_Open(missions)
        assert selected == [missions] and not errors
        window.Path_Open(root)
        assert selected[-1] == root.resolve()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(missions))])
        event = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.dropEvent(event)
        assert event.isAccepted() and selected[-1] == missions
        assert window._DropPaths_Validate([QUrl.fromLocalFile(str(missions)), QUrl.fromLocalFile(str(root))]) is None
        assert window._DropPaths_Validate([QUrl('https://example.org/missions')]) is None
    finally:
        window.close()
        application.processEvents()
