"""Render normal controller-owned GSHC pages with an empty Host port inventory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("runtime", type=Path)
parser.add_argument("--lang", choices=("zh_CN", "en_US"), required=True)
parser.add_argument("--theme", choices=("light", "dark"), required=True)
options = parser.parse_args()
options.output.mkdir(parents=True, exist_ok=False)
options.runtime.mkdir(parents=True, exist_ok=False)
os.environ["SILVERSTAR_GSHC_DATA_ROOT"] = str(options.runtime.resolve())
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps/GSHC"))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import Controller
from services.i18n import I18n
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
from ui.main_window import MainWindow

application = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
application.setFont(QFont("Microsoft YaHei", 9))
store = QSettings(str((options.runtime / "settings.ini").resolve()), QSettings.IniFormat)
language = I18n(store)
language.set_language(options.lang)
window = MainWindow(language)
with patch("app.list_serial_port_names", return_value=[]):
    controller = Controller(window, probe_enumerator=lambda _: ProbeInventory(ProbeInventoryResult.Empty))
    window.resize(1024, 768)
    window.show()
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(options.theme))
    rows = []

    def grab(widget, name):
        QTest.qWait(100)
        assert widget.isVisible()
        file = options.output / (name + ".png")
        pixmap = widget.grab()
        assert pixmap.save(str(file))
        rows.append({"window": name, "pixels": [pixmap.width(), pixmap.height()],
                     "device_pixel_ratio": widget.devicePixelRatioF(),
                     "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})

    for name, page in (("preflight", window.preflight_page), ("flight", window.flight_page),
                       ("recovery", window.post_process_page), ("maintenance", window.maintenance_scroll)):
        window.pages.setCurrentWidget(page)
        grab(window, name)
    window.pages.setCurrentWidget(window.preflight_page)
    window.btn_mag_calibration.click()
    dialog = controller.file_transfer.mag_dialog
    assert not dialog.start.isEnabled()
    grab(dialog, "mag-calibration")
    dialog.request_close()
    controller.shutdown()
    window.close()
    QTest.qWait(50)
    assert not any(widget.isVisible() for widget in application.topLevelWidgets())
    (options.output / "receipt.json").write_text(json.dumps(
        {"scope": "Qt offscreen, empty hardware inventory, default disconnected state",
         "language": options.lang, "theme": options.theme, "windows": rows}, indent=2), encoding="utf8")
