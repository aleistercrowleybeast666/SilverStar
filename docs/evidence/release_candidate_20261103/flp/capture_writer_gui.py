"""Open an actual Host-generated log through the normal Qt workflow and inspect recorded tabs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("log", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("runtime", type=Path)
options = parser.parse_args()
options.output.mkdir(parents=True, exist_ok=False)
options.runtime.mkdir(parents=True, exist_ok=False)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["LOCALAPPDATA"] = str(options.runtime.resolve())
root = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(root / "apps/FLP/src"), str(root / "apps/SCG/src")]

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from silverstar_flp.core.path_preferences import PathPreferences
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.mission_snapshot import MissionSnapshotDialog

application = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
application.setFont(QFont("Microsoft YaHei", 9))
preferences = PathPreferences(options.runtime / "preferences.json")
window = MainWindow(builtin_registry(), language="zh_CN", theme="light", path_preferences=preferences)
window._log_open_coordinator.cache = DecoderProfileCache(options.runtime / "decoder-cache")
window.resize(1100, 760)
window.show()
log = options.log.resolve()
window.Path_Open(log)
deadline = time.monotonic() + 300
while window._dataset is None and time.monotonic() < deadline:
    QTest.qWait(50)
assert window._dataset is not None and window._dataset.source_path == log
snapshot = window._dataset.metadata["mission_snapshot"]
assert snapshot["status"] == "verified" and len(snapshot["sources"]) == 7
rows = []

def save(widget, name):
    QTest.qWait(120)
    assert widget.isVisible()
    image = widget.grab()
    path = options.output / (name + ".png")
    assert image.save(str(path))
    rows.append({"screen": name, "pixels": [image.width(), image.height()],
                 "device_pixel_ratio": image.devicePixelRatio(),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

save(window, "overview")
window.overview_page.mission_snapshot_button.click()
dialog = window.findChild(MissionSnapshotDialog)
assert dialog is not None and dialog.isVisible()
for index in range(dialog.tabs.count()):
    dialog.tabs.setCurrentIndex(index)
    save(dialog, "recorded-" + str(index))
    rows[-1]["tab"] = dialog.tabs.tabText(index)
dialog.close()

def discard_test_draft():
    box = application.activeModalWidget()
    if isinstance(box, QMessageBox) and box.button(QMessageBox.StandardButton.Discard):
        box.button(QMessageBox.StandardButton.Discard).click()

QTimer.singleShot(50, discard_test_draft)
window.close()
QTest.qWait(100)
assert not window.isVisible()
(options.output / "receipt.json").write_text(json.dumps(
    {"scope": "Source Qt offscreen; actual firmware writer with synthetic input",
     "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "screens": rows},
    ensure_ascii=False, indent=2), encoding="utf8")
