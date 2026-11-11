"""Native, private-state diagnostic of production FLP startup. No source edits.

Optional changes are explicit isolation experiments, never product acceptance.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--no-fit", action="store_true")
parser.add_argument("--deferred-fit", action="store_true")
parser.add_argument("--before-show-fit", action="store_true")
parser.add_argument("--fit-part", choices=("resize", "minimum", "move"))
parser.add_argument("--no-caption", action="store_true")
parser.add_argument("--no-gl", action="store_true")
parser.add_argument("--visit-gl", action="store_true")
parser.add_argument("--wait-trigger", action="store_true")
parser.add_argument("--auto-own-foreground", action="store_true")
parser.add_argument("--share-contexts", action="store_true")
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT / "apps/FLP/src"))

import numpy as np
from PySide6.QtCore import QEvent, QObject, QSettings, QTimer, Qt, qVersion
from PySide6.QtGui import QImage
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication
if args.share_contexts:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from silverstar_flp.app import application
from silverstar_flp.core.path_preferences import PathPreferences
from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
from silverstar_flp.ui import main_window
from silverstar_flp.ui.pages import charts

doc = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
       "qt": qVersion(), "pid": os.getpid(), "arguments": vars(args) | {"output": str(out)},
       "env": {k: v for k, v in os.environ.items() if k.startswith(("QT_", "QSG_"))},
       "scope": "Private settings; synthetic empty project only. QWidget.grab and QScreen.grabWindow are diagnostic and not WGC acceptance.",
       "snapshots": [], "errors": [], "source_files": {}}
for module in (application, main_window, charts):
    path = Path(module.__file__)
    doc["source_files"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()


def private_settings(*unused):
    return QSettings(str(out / "settings.ini"), QSettings.Format.IniFormat)


def private_logging():
    path = out / "application.log"
    logging.basicConfig(filename=path, level=logging.INFO, encoding="utf8")
    return path


application.QSettings = main_window.QSettings = private_settings
application._Logging_Configure = private_logging
production_fit = application.Application_ConstrainInitialGeometry
if args.no_fit or args.before_show_fit:
    application.Application_ConstrainInitialGeometry = lambda window: None
elif args.deferred_fit:
    original_fit = application.Application_ConstrainInitialGeometry
    fit_calls = []
    def deferred_fit(window):
        fit_calls.append(len(fit_calls) + 1)
        doc["fit_calls"] = list(fit_calls)
        if len(fit_calls) > 1:
            original_fit(window)
    application.Application_ConstrainInitialGeometry = deferred_fit
elif args.fit_part:
    def partial_fit(window):
        available = window.screen().availableGeometry()
        frame = window.frameGeometry()
        width = max(1, available.width() - max(0, frame.width() - window.width()))
        height = max(1, available.height() - max(0, frame.height() - window.height()))
        if args.fit_part == "minimum":
            window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
        elif args.fit_part == "resize":
            window.resize(min(window.width(), width), min(window.height(), height))
        else:
            window.move(max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
                        max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)))
    application.Application_ConstrainInitialGeometry = partial_fit
if args.no_caption:
    main_window.WindowCaption_Apply = lambda window, theme: None
if args.no_gl:
    charts.gl = None
original_init = application.MainWindow.__init__


def private_init(window, *positional, **keywords):
    keywords["plugin_manager"] = TrustedContainerPluginManager(out / "plugins")
    keywords["path_preferences"] = PathPreferences(out / "paths.json")
    original_init(window, *positional, **keywords)


application.MainWindow.__init__ = private_init
original_show = application.MainWindow.show
paint_counts = {}


class PaintCounter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:
            key = obj.metaObject().className()
            paint_counts[key] = paint_counts.get(key, 0) + 1
        return False


def image_record(pixmap, name):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    if image.isNull():
        return {"null": True}
    image.save(str(out / (name + ".png")))
    data = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    rgb = data[:, :image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, :3]
    return {"width": image.width(), "height": image.height(),
            "white_fraction": float(np.all(rgb == 255, axis=2).mean()),
            "nonwhite_pixels": int(np.any(rgb != 255, axis=2).sum()),
            "rgb_std": float(rgb.std()), "file": name + ".png"}


def snapshot(window, tag):
    try:
        children = window.findChildren(QOpenGLWidget)
        handle = int(window.winId())
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        foreground = user32.GetForegroundWindow()
        foreground_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(foreground), ctypes.byref(foreground_pid))
        row = {"tag": tag, "surface": str(window.windowHandle().surfaceType()),
               "dpr": window.devicePixelRatioF(), "updates_enabled": window.updatesEnabled(),
               "frame_contained": window.screen().availableGeometry().contains(window.frameGeometry()),
               "frame": list(window.frameGeometry().getRect()),
               "paint_counts_before_grab": dict(paint_counts), "gl": [],
               "own_hwnd": handle, "foreground_hwnd": foreground,
               "foreground_pid": foreground_pid.value,
               "native_grab_unoccluded_candidate": foreground == handle and foreground_pid.value == os.getpid()}
        for child in children:
            context = child.context()
            detail = {"visible": child.isVisible(), "valid": child.isValid(),
                "context": context is not None,
                "context_valid": context.isValid() if context else None,
                "context_version": [context.format().majorVersion(), context.format().minorVersion()] if context else None}
            if context and context.isValid():
                from OpenGL import GL
                child.makeCurrent()
                detail["pyopengl_vendor"] = str(GL.glGetString(GL.GL_VENDOR))
                detail["pyopengl_renderer"] = str(GL.glGetString(GL.GL_RENDERER))
                detail["pyopengl_version"] = str(GL.glGetString(GL.GL_VERSION))
                child.doneCurrent()
            row["gl"].append(detail)
        row["native_before_qwidget_grab"] = image_record(window.screen().grabWindow(int(window.winId())), tag + "-native-before")
        row["qwidget_grab"] = image_record(window.grab(), tag + "-qt")
        row["native_after_qwidget_grab"] = image_record(window.screen().grabWindow(int(window.winId())), tag + "-native-after")
        row["foreground_unchanged_after_grabs"] = user32.GetForegroundWindow() == handle
        doc["snapshots"].append(row)
        if tag == "initial" and args.visit_gl:
            window.pages.setCurrentWidget(window.flight_page)
            window.flight_page.tabs.setCurrentWidget(window.flight_page.replay_3d_widget)
            QTimer.singleShot(1500, window, lambda: snapshot(window, "visible-gl"))
        elif tag == "visible-gl":
            window.pages.setCurrentWidget(window.overview_page)
            QTimer.singleShot(700, window, lambda: snapshot(window, "overview-after-gl"))
        else:
            window.close()
    except Exception:
        doc["errors"].append(traceback.format_exc())
        QApplication.instance().exit(90)


filters = []


def observed_show(window):
    counter = PaintCounter(window)
    filters.append(counter)
    window.installEventFilter(counter)
    window.centralWidget().installEventFilter(counter)
    doc["before_show"] = {"frame": list(window.frameGeometry().getRect()),
        "geometry": list(window.geometry().getRect()),
        "available": list(window.screen().availableGeometry().getRect()),
        "window_handle_exists": window.windowHandle() is not None}
    if args.before_show_fit:
        production_fit(window)
        doc["before_show_after_fit"] = {"frame": list(window.frameGeometry().getRect()),
            "geometry": list(window.geometry().getRect())}
    original_show(window)
    window.setWindowTitle("FLP compositor diagnostic " + out.name)
    window.raise_()
    window.activateWindow()
    if args.wait_trigger or args.auto_own_foreground:
        ready = {"pid": os.getpid(), "hwnd": int(window.winId()), "title": window.windowTitle(),
                 "trigger": str(out / "capture.request")}
        (out / "ready.json").write_text(json.dumps(ready), encoding="utf8")
        print(json.dumps(ready), flush=True)
        deadline = time.monotonic() + (20 if args.auto_own_foreground else 180)
        def wait_capture():
            own_foreground = False
            if args.auto_own_foreground:
                user32 = ctypes.WinDLL("user32")
                user32.GetForegroundWindow.restype = ctypes.c_void_p
                own_foreground = user32.GetForegroundWindow() == int(window.winId())
            if (out / "capture.request").exists() or own_foreground:
                snapshot(window, "initial")
            elif time.monotonic() > deadline:
                doc["errors"].append("No capture trigger within bounded 180-second diagnostic wait")
                window.close()
            else:
                QTimer.singleShot(200, window, wait_capture)
        QTimer.singleShot(1500, window, wait_capture)
    else:
        QTimer.singleShot(1500, window, lambda: snapshot(window, "initial"))


application.MainWindow.show = observed_show
try:
    doc["exit"] = application.main(["--lang", "en_US", "--theme", "light"])
except Exception:
    doc["errors"].append(traceback.format_exc())
    doc["exit"] = 91
(out / "receipt.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf8")
print(json.dumps({"receipt": str(out / "receipt.json"), "exit": doc["exit"], "errors": len(doc["errors"])}), flush=True)
raise SystemExit(doc["exit"])
