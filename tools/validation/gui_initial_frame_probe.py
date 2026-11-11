"""Observe production application.main; isolate persistence and hardware discovery only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "apps/SCG/src").is_dir())
parser = argparse.ArgumentParser()
parser.add_argument("product", choices=("SCG", "FLP", "GSHC"))
parser.add_argument("output", type=Path)
parser.add_argument("--rapid-close", action="store_true")
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
product_root = ROOT / "apps" / args.product
sys.path.insert(0, str(product_root if args.product == "GSHC" else product_root / "src"))
os.environ["SILVERSTAR_GSHC_DATA_ROOT"] = str(out / "data")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QTimer, qVersion
from PySide6.QtWidgets import QApplication, QStatusBar
from shiboken6 import isValid

document = {
    "product": args.product,
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "python": sys.executable,
    "qt": qVersion(),
    "scale_factor": os.environ.get("QT_SCALE_FACTOR"),
    "rapid_close": args.rapid_close,
    "private_settings": str(out / "settings.ini"),
    "user_project_opened": False,
    "initial_geometry_modified_by_probe": False,
    "entry_fit_calls": [],
    "errors": [],
}
controllers = []

def private_settings(*unused):
    return QSettings(str(out / "settings.ini"), QSettings.Format.IniFormat)

def private_logging(*unused):
    path = out / "application.log"
    logging.basicConfig(filename=path, level=logging.INFO, encoding="utf-8")
    return path

def forbidden_hardware(*unused, **unused_keywords):
    raise AssertionError("Geometry acceptance must not open hardware")

if args.product == "SCG":
    from silverstar_fccg.app import application
    from silverstar_fccg.core.settings import SettingsStore
    application.SettingsStore = lambda unused: SettingsStore(out / "settings.ini")
    application._Logging_Configure = private_logging
elif args.product == "FLP":
    from silverstar_flp.app import application
    from silverstar_flp.core.path_preferences import PathPreferences
    from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
    from silverstar_flp.ui import main_window
    application.QSettings = private_settings
    main_window.QSettings = private_settings
    application._Logging_Configure = private_logging
    original_init = application.MainWindow.__init__

    def private_init(window, *positional, **keywords):
        keywords["plugin_manager"] = TrustedContainerPluginManager(out / "plugins")
        keywords["path_preferences"] = PathPreferences(out / "paths.json")
        original_init(window, *positional, **keywords)

    application.MainWindow.__init__ = private_init
else:
    import config
    config.CONFIG_DIR = out / "config"
    config.USER_PATHS_FILE = config.CONFIG_DIR / "user_paths.json"
    from services import i18n
    i18n.QSettings = private_settings
    application = importlib.import_module("app")
    from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
    from transport.serial_backend import SerialLink
    SerialLink.open = forbidden_hardware
    application.list_serial_port_names = lambda: []
    original_controller = application.Controller

    def private_controller(window):
        controller = original_controller(
            window,
            probe_enumerator=lambda cancelled: ProbeInventory(ProbeInventoryResult.Empty),
            swd_factory=forbidden_hardware,
        )
        controllers.append(controller)
        return controller

    application.Controller = private_controller
    document["hardware_boundary"] = "Real Controller; empty injected host inventory/ports; serial open and SWD factory reject"

source = Path(application.__file__)
document["application_source"] = str(source)
document["application_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
original_fit = application.Application_ConstrainInitialGeometry
original_show = application.MainWindow.show
window_seen = []

def rectangle(value):
    return [value.x(), value.y(), value.width(), value.height()]

def snapshot(window):
    available = window.screen().availableGeometry()
    status = window.findChild(QStatusBar)
    result = {
        "dpr": window.devicePixelRatioF(),
        "frame": rectangle(window.frameGeometry()),
        "available": rectangle(available),
        "frame_contained": available.contains(window.frameGeometry()),
        "maximized": window.isMaximized(),
        "status_bar_contained": None,
    }
    if status is not None:
        result["status_bar_contained"] = all(
            available.contains(status.mapToGlobal(point))
            for point in (status.rect().topLeft(), status.rect().bottomRight())
        )
    return result

def observed_fit(window, *positional, **keywords):
    try:
        before = snapshot(window)
        original_fit(window, *positional, **keywords)
        document["entry_fit_calls"].append({"before": before, "after": snapshot(window)})
    except Exception:
        document["errors"].append(traceback.format_exc())
        QApplication.instance().exit(92)

application.Application_ConstrainInitialGeometry = observed_fit

def guarded(function):
    def invoke():
        try:
            function()
        except Exception:
            document["errors"].append(traceback.format_exc())
            QApplication.instance().exit(91)
    return invoke

def assert_hardware_idle():
    for controller in controllers:
        assert not controller.link.is_open()
        assert controller.worker is None and controller.protocol_worker is None
        assert not controller.state.connected

def change_view(window):
    document["settled_first_show"] = snapshot(window)
    assert document["settled_first_show"]["frame_contained"]
    assert document["settled_first_show"]["status_bar_contained"] is not False
    assert len(document["entry_fit_calls"]) == 2
    if args.product == "SCG":
        document["model_before_view"] = copy.deepcopy(window._model.Dictionary_Get())
    if args.product == "GSHC":
        window.language_combo.setCurrentIndex(window.language_combo.findData("en_US"))
        window.theme_combo.setCurrentIndex(window.theme_combo.findData("dark"))
    else:
        window.Language_Apply("en_US")
        window.Theme_Apply("dark")
    old_page = window.pages.currentIndex()
    window.pages.setCurrentIndex((old_page + 1) % window.pages.count())
    window.pages.setCurrentIndex(old_page)

def finish_contracts(window):
    document["after_view_changes"] = snapshot(window)
    assert document["after_view_changes"]["frame"] == document["settled_first_show"]["frame"]
    assert len(document["entry_fit_calls"]) == 2, "View changes must not repeat initial fitting"
    if args.product == "SCG":
        assert document.pop("model_before_view") == window._model.Dictionary_Get()
    elif args.product == "FLP":
        assert not window._project_dirty
    assert_hardware_idle()
    available = window.screen().availableGeometry()
    # A later user-chosen legal size/position must be preserved by the helper.
    window.resize(min(window.width(), available.width() - 100), min(window.height(), available.height() - 100))
    QApplication.processEvents()
    frame = window.frameGeometry()
    window.move(available.left() + min(24, max(0, available.width() - frame.width())), available.top())
    QApplication.processEvents()
    before = snapshot(window)
    assert before["frame_contained"]
    original_fit(window)
    document["valid_geometry_preserved"] = before == snapshot(window)
    assert document["valid_geometry_preserved"]
    window.showMaximized()
    QApplication.processEvents()
    before = snapshot(window)
    assert before["maximized"]
    original_fit(window)
    document["maximized_preserved"] = before == snapshot(window)
    assert document["maximized_preserved"]
    document["normal_close_accepted"] = window.close()
    assert document["normal_close_accepted"]

def rapid_close(window):
    application_instance = QApplication.instance()
    if args.product == "FLP":
        # Continue briefly after accepted WA_DeleteOnClose, so the queued startup
        # callback would raise if its QObject receiver lifetime were not honored.
        application_instance.setQuitOnLastWindowClosed(False)
    document["normal_close_accepted"] = window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    document["valid_after_rapid_close"] = isValid(window)
    if args.product == "FLP":
        assert document["normal_close_accepted"] and not isValid(window)
        QTimer.singleShot(80, application_instance.quit)
    assert_hardware_idle()

def observed_show(window):
    window_seen.append(window)
    document["platform"] = QApplication.platformName()
    document["before_show_size"] = [window.width(), window.height()]
    original_show(window)
    if args.rapid_close:
        QTimer.singleShot(0, window, guarded(lambda: rapid_close(window)))
    else:
        QTimer.singleShot(1500, window, guarded(lambda: change_view(window)))
        QTimer.singleShot(3000, window, guarded(lambda: finish_contracts(window)))
    QTimer.singleShot(20000, QApplication.instance(), lambda: QApplication.instance().exit(93))

application.MainWindow.show = observed_show
try:
    sys.argv = [str(source)]
    code = application.main() if args.product == "GSHC" else application.main(["--lang", "zh_CN", "--theme", "light"])
    document["main_exit_code"] = code
    assert code == 0 and not document["errors"]
    assert len(window_seen) == 1
    if args.rapid_close and args.product == "FLP":
        assert len(document["entry_fit_calls"]) == 1, "Destroyed receiver must cancel queued fit"
    assert_hardware_idle()
except Exception:
    document["errors"].append(traceback.format_exc())
    code = 90
(out / "receipt.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"product": args.product, "code": code, "fit_calls": len(document["entry_fit_calls"]), "errors": document["errors"]}, ensure_ascii=False), flush=True)
raise SystemExit(code)
