from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from silverstar_flp.decoder_profiles.discovery import TaskDirectoryScanner
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow


def test_project_root_scans_only_canonical_decoder_and_log_tree(tmp_path: Path) -> None:
    root = tmp_path / "mission"
    logs = root / "Log"
    logs.mkdir(parents=True)
    (root / "SilverStar.ssproject").write_text("{}", encoding="utf-8")
    decoder = root / "Mission.ssdecoder"
    decoder.write_bytes(b"decoder")
    first = logs / "SS0000.BIN"
    second = logs / "SS0001.sslog"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    vendor = root / "Flight_Controller" / "Drivers"
    vendor.mkdir(parents=True)
    (vendor / "fake.ssdecoder").write_bytes(b"vendor")
    (vendor / "fake.BIN").write_bytes(b"vendor")

    found = TaskDirectoryScanner().Scan(root)
    assert set(found.log_paths) == {first.resolve(), second.resolve()}
    assert found.decoder_package_paths == (decoder.resolve(),)
    assert found.scanned_file_count == 3


def test_project_root_default_export_stays_beside_selected_log(tmp_path: Path) -> None:
    application = QApplication.instance() or QApplication([])
    root = tmp_path / "mission"
    log_root = root / "Log"
    log_root.mkdir(parents=True)
    (root / "SilverStar.ssproject").write_text("{}", encoding="utf-8")
    source = log_root / "SS0001.BIN"
    source.write_bytes(b"log")
    window = MainWindow(builtin_registry())
    try:
        window._silverstar_project_root = root
        window._dataset = type("Dataset", (), {"source_path": source})()
        assert window._ExportDirectory_Default() == log_root / "SS0001_Export"
        assert window.open_silverstar_project_action.text() == "打开 SilverStar 工程文件夹"
    finally:
        window.close()
        application.processEvents()
