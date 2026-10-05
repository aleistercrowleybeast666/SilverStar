"""Windowed startup rejection is visible without constructing the FLP window."""

from pathlib import Path

import pytest

from silverstar_flp.app import application, startup_error
from silverstar_flp.core import runtime


@pytest.mark.parametrize(
    "language, phrase", [("zh_CN", "启动已阻止"), ("en_US", "Startup blocked")]
)
def test_windowed_bad_runtime_shows_native_error_then_exits_two(monkeypatch, language, phrase):
    displayed = []
    monkeypatch.setattr(runtime.np, "__version__", "2.4.0")
    monkeypatch.setattr(startup_error.sys, "stderr", None)
    monkeypatch.setattr(startup_error.sys, "stdout", None)
    monkeypatch.setattr(startup_error.sys, "platform", "win32")
    monkeypatch.setattr(startup_error, "_WindowsError_Show", lambda *args: displayed.append(args))

    def forbidden(*args, **kwargs):
        raise AssertionError("FLP QApplication/MainWindow must not start on Windows rejection")

    monkeypatch.setattr(application.QApplication, "setOrganizationName", forbidden)
    monkeypatch.setattr(application, "MainWindow", forbidden)
    assert application.main(["--lang", language]) == 2
    assert len(displayed) == 1
    title, message = displayed[0]
    assert phrase in title
    assert "2.4.0" in message and "2.4.1" in message
    assert "numpy_version_unsafe" in message
    assert str(Path(startup_error.__file__).resolve().parents[3] / ".venv") in message


def test_console_rejection_preserves_stderr_and_skips_dialog(monkeypatch, capsys):
    monkeypatch.setattr(runtime.np, "__version__", "2.4.0")

    def forbidden(*args):
        raise AssertionError("Console rejection must use its existing stderr path")

    monkeypatch.setattr(startup_error, "_WindowsError_Show", forbidden)
    assert application.main(["--lang", "en_US"]) == 2
    assert capsys.readouterr().err.startswith("error: numpy_version_unsafe:")


def test_native_dialog_uses_typed_unicode_api_and_ordinary_error_flags(monkeypatch):
    import ctypes
    from ctypes import wintypes

    calls = []

    class MessageBox:
        def __call__(self, *args):
            calls.append(args)
            return 1  # User closes OK.

    class User32:
        MessageBoxW = MessageBox()

    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: User32())
    startup_error._WindowsError_Show("中文 title", "中文 reason")
    assert calls == [(None, "中文 reason", "中文 title", 0x10 | 0x2000)]
    assert User32.MessageBoxW.argtypes == [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    ]
    assert User32.MessageBoxW.restype is ctypes.c_int
