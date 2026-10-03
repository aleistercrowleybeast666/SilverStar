"""Native Qt, synthetic-only full-task trajectory QA; no serial or user window control."""

import hashlib
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
APP_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(APP_ROOT), str(APP_ROOT / "tests")]
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from config import HORIZONTAL_TRAJECTORY_MAX_POINTS
from protocol.air import AirStatusMessage
from protocol.common import AirStatusId
from services.i18n import I18n
from services.preferences import Theme
from test_mission_trajectory import _Frame_Get
from test_start_ack_state import make_controller
from ui.main_window import MainWindow

app = QApplication([])
app.setFont(QFont("Microsoft YaHei", 9))
report = {"platform": app.platformName(), "screenshots": [], "synthetic_only": True}
window = MainWindow(I18n(QSettings(str(OUT / "preferences.ini"), QSettings.Format.IniFormat)))
window.render_timer.stop()
controller = make_controller()
controller._handle_status_message(AirStatusMessage(1, int(AirStatusId.MISSION_START), 0, 0, 0), None)
for index in range(1751):
    controller._handle_flight_state(_Frame_Get(index), None)
    if index == 50:
        controller._handle_status_message(
            AirStatusMessage(2, int(AirStatusId.PARACHUTE_DEPLOY), 10000, 0, 0), None)
    elif index > 50:
        controller._handle_status_message(
            AirStatusMessage(index % 256, int(AirStatusId.GNSS_POSITION), index*200, 1, 0), None)
window.bind_runtime_model(controller.state, controller.events)
window._render_plots(controller.state)
window.show()

def pump(seconds=0.7):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)

def capture(name):
    pump()
    path = OUT / (name + ".png")
    assert window.grab().save(str(path))
    report["screenshots"].append({"file": path.name, "size": [window.width(), window.height()],
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

# Execute the original submitted renderer with the same real bounded live buffer
# as pre-fix failure evidence. This reads code from Git; it does not change a source file.
old_source = subprocess.check_output(
    ["git", "show", "553ad436f091d6d9927f7c0a6c55e03e06f5e1f3:apps/GSHC/ui/main_window.py"],
    cwd=APP_ROOT).decode("utf8")
module = types.ModuleType("ui.main_window_pre_fix_probe")
sys.modules[module.__name__] = module
exec(compile(old_source, "553ad43/ui/main_window.py", "exec"), module.__dict__)
old = module.MainWindow(I18n(QSettings(str(OUT / "pre-fix.ini"), QSettings.Format.IniFormat)))
old.render_timer.stop()
old.bind_runtime_model(controller.state, controller.events)
old._render_plots(controller.state)
old_geometry = old.horizontal_trajectory_widget.trajectory
report["pre_fix_553ad43"] = {"first_s": float(old_geometry.times_s[0]),
                            "last_s": float(old_geometry.times_s[-1]),
                            "start_clipped": old_geometry.start_clipped,
                            "early_deploy_visible": old_geometry.deploy_enu is not None}
assert old_geometry.times_s[0] == 340 and old_geometry.deploy_enu is None
old.close()
new_geometry = window.horizontal_trajectory_widget.trajectory
report["full_task_350s"] = {"sample_count": len(new_geometry.times_s),
                           "first_s": float(new_geometry.times_s[0]),
                           "last_s": float(new_geometry.times_s[-1]),
                           "start_clipped": new_geometry.start_clipped,
                           "early_deploy_visible": new_geometry.deploy_enu is not None}
assert len(new_geometry.times_s) == 1751 and not new_geometry.start_clipped
assert new_geometry.deploy_enu is not None

for language, theme in (("en_US", "light"), ("zh_CN", "dark")):
    window.i18n.set_language(language)
    window.retranslate_ui()
    window._apply_theme(Theme(theme), persist=True)
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
    for height in (720, 900):
        window.resize(1280, height)
        window.pages.setCurrentWidget(window.horizontal_trajectory_widget)
        capture(f"full_350s_{language}_{height}")
        window.pages.setCurrentWidget(window.flight_page)
        capture(f"preserved_six_curves_{language}_{height}")

# Freeze at landing, then an explicit next task, fill beyond the real capacity.
controller._handle_status_message(AirStatusMessage(3, int(AirStatusId.LANDING), 350000, 0, 0), None)
window._render_plots(controller.state)
assert not window.horizontal_trajectory_widget.trajectory.end_clipped
controller._handle_status_message(AirStatusMessage(4, int(AirStatusId.MISSION_START), 0, 0, 0), None)
assert controller.state.horizontal_trajectory.Snapshot_Get()[0] == []
for index in range(HORIZONTAL_TRAJECTORY_MAX_POINTS + 7):
    controller.state.horizontal_trajectory.Sample_Append(index / 5, _Frame_Get(index).pos_m)
window._render_plots(controller.state)
report["capacity"] = {"max_points": HORIZONTAL_TRAJECTORY_MAX_POINTS,
                      "retained": len(window.horizontal_trajectory_widget.trajectory.times_s),
                      "omitted": window.horizontal_trajectory_widget.omitted_samples}
for language, theme in (("en_US", "light"), ("zh_CN", "dark")):
    window.i18n.set_language(language)
    window.retranslate_ui()
    window._apply_theme(Theme(theme), persist=True)
    window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
    window.pages.setCurrentWidget(window.horizontal_trajectory_widget)
    window.resize(1280, 900)
    capture(f"capacity_{language}_900")

window.close()
report["limitations"] = "Qt window render only; no sky/native screen tool exposed; no hardware data/actions."
(OUT / "gui_report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
app.quit()
