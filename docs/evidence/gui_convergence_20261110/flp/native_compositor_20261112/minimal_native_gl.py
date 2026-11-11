"""No FLP imports: distinguish Qt/OpenGL native presentation from application code."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from PySide6.QtCore import QPoint, QRect, QTimer, qVersion
from PySide6.QtGui import QImage, QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLFunctions_2_0
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--raster", action="store_true")
parser.add_argument("--swap", choices=("single", "double", "triple"))
parser.add_argument("--swap-interval", type=int)
parser.add_argument("--alpha", type=int)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
doc = {"pid": os.getpid(), "qt": qVersion(), "scope": "Minimal Qt only; no FLP, pyqtgraph or PyOpenGL imports",
       "env": {k: v for k, v in os.environ.items() if k.startswith("QT_")},
       "raster": args.raster, "paints": 0, "errors": []}
format_ = QSurfaceFormat.defaultFormat()
if args.swap:
    format_.setSwapBehavior({"single": QSurfaceFormat.SwapBehavior.SingleBuffer,
        "double": QSurfaceFormat.SwapBehavior.DoubleBuffer,
        "triple": QSurfaceFormat.SwapBehavior.TripleBuffer}[args.swap])
if args.swap_interval is not None:
    format_.setSwapInterval(args.swap_interval)
if args.alpha is not None:
    format_.setAlphaBufferSize(args.alpha)
QSurfaceFormat.setDefaultFormat(format_)
doc["requested_format"] = {"swap": args.swap, "interval": args.swap_interval, "alpha": args.alpha}


class Canvas(QOpenGLWidget):
    def initializeGL(self):
        self.functions = QOpenGLFunctions_2_0()
        doc["functions_initialized"] = self.functions.initializeOpenGLFunctions()
        doc["version"] = [self.context().format().majorVersion(), self.context().format().minorVersion()]
        doc["actual_format"] = str(self.context().format())

    def paintGL(self):
        doc["paints"] += 1
        self.functions.glClearColor(0.1, 0.3, 0.65, 1.0)
        self.functions.glClear(0x00004000)


app = QApplication([])
window = QMainWindow()
window.setWindowTitle("Minimal Qt native compositor " + out.name)
root = QWidget()
layout = QVBoxLayout(root)
label = QLabel("Minimal Qt: native blue canvas below; no FLP or pyqtgraph")
label.setStyleSheet("background: #e0e0e0; color: #101010; font-size: 22px")
layout.addWidget(label)
canvas = QWidget() if args.raster else Canvas()
if args.raster:
    canvas.setStyleSheet("background: #1a4da6")
layout.addWidget(canvas, 1)
window.setCentralWidget(root)
window.resize(1000, 700)
window.show()
window.raise_()
window.activateWindow()
deadline = time.monotonic() + 20


def capture_image(pixmap, name):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    image.save(str(out / (name + ".png")))
    a = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    rgb = a[:, :image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, :3]
    return {"white_fraction": float(np.all(rgb == 255, axis=2).mean()), "rgb_std": float(rgb.std())}


def capture():
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        hwnd = int(window.winId())
        foreground = user32.GetForegroundWindow()
        if foreground != hwnd and time.monotonic() < deadline:
            QTimer.singleShot(200, capture)
            return
        doc["own_hwnd"] = hwnd
        doc["foreground_hwnd"] = foreground
        doc["foreground_is_self"] = foreground == hwnd
        doc["surface"] = str(window.windowHandle().surfaceType())
        doc["dpr"] = window.devicePixelRatioF()
        doc["native_before_qwidget_grab"] = capture_image(window.screen().grabWindow(hwnd), "native-before")
        client = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        screen = window.screen()
        doc["client_global"] = list(client.getRect())
        doc["screen_geometry"] = list(screen.geometry().getRect())
        if foreground == hwnd and screen.geometry().contains(client):
            local = client.translated(-screen.geometry().x(), -screen.geometry().y())
            doc["own_client_desktop_pregrab"] = capture_image(
                screen.grabWindow(0, local.x(), local.y(), local.width(), local.height()),
                "own-client-desktop-before")
        else:
            doc["own_client_desktop_pregrab"] = {"skipped": "Not self foreground or client outside one screen"}
        doc["qwidget_grab"] = capture_image(window.grab(), "qt")
        doc["native_after_qwidget_grab"] = capture_image(window.screen().grabWindow(hwnd), "native-after")
        window.close()
    except Exception:
        doc["errors"].append(traceback.format_exc())
        app.exit(90)


QTimer.singleShot(1500, capture)
doc["exit"] = app.exec()
(out / "receipt.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf8")
print(json.dumps(doc), flush=True)
sys.exit(doc["exit"])
