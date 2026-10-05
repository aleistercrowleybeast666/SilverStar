"""Show a startup rejection even when a windowed launcher has no console."""

from __future__ import annotations

import sys
from pathlib import Path

from silverstar_flp.app.version import PRODUCT_NAME


def _WindowsError_Show(title: str, message: str) -> None:
    import ctypes
    from ctypes import wintypes

    message_box = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW
    message_box.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    message_box.restype = ctypes.c_int
    # An ordinary modal error dialog; no renderer or application window is started.
    message_box(None, message, title, 0x10 | 0x2000)


def StartupError_Report(error: RuntimeError, language: str) -> None:
    if sys.stderr is not None:
        print(f"error: {error}", file=sys.stderr)
        return
    environment = Path(__file__).resolve().parents[3] / ".venv"
    if language == "en_US":
        title = f"{PRODUCT_NAME} — Startup blocked"
        remedy = (
            "NumPy 2.4.0 can leak memory during replay. FLP has stopped before opening "
            "the application. Install a fixed NumPy release (validated: 2.4.1) in the "
            f"FLP environment, then restart.\n\nFLP environment: {environment}"
        )
    else:
        title = f"{PRODUCT_NAME} — 启动已阻止"
        remedy = (
            "NumPy 2.4.0 在复算时可能泄漏内存。FLP 已在打开主界面前停止。"
            "请在 FLP 环境中安装修复版本（已验证：2.4.1），然后重新启动。"
            f"\n\nFLP 环境：{environment}"
        )
    message = f"{remedy}\n\n{error}"
    if sys.platform == "win32":
        _WindowsError_Show(title, message)
    else:
        from PySide6.QtWidgets import QApplication, QMessageBox

        application = QApplication.instance() or QApplication([sys.argv[0]])
        QMessageBox.critical(None, title, message)
        # Keep the minimal application alive until the modal dialog closes.
        del application
