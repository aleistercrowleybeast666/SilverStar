"""Ordinary production MainWindow; only settings and audit files are isolated."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/SCG/src"))
from PySide6.QtWidgets import QApplication
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow

scratch = ROOT / ".work/0.1.3-software-completion-20261101/gui/native"
scratch.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv)
window = MainWindow(SettingsStore(scratch / "settings.ini"),
                    service=FccgService(ROOT / "apps/SCG"), language="zh_CN", theme="light")
window.setWindowTitle("SilverStar SCG — 软件收尾验证")
initial = window._model.Dictionary_Get()
(scratch / "initial-model.json").write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")

def record_final():
    (scratch / "final-model.json").write_text(json.dumps(window._model.Dictionary_Get(),
        ensure_ascii=False, indent=2), encoding="utf-8")

app.aboutToQuit.connect(record_final)
window.show()
raise SystemExit(app.exec())
