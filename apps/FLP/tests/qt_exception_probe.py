"""Opt-in exception-only evidence for rare Qt callbacks during widget lifetime.

Enable with PYTEST_PLUGINS=tests.qt_exception_probe and SS_FLP_QT_TRACE=<path>.
Every exception is forwarded unchanged to pytest-qt's normal failing gate.
Normal Qt methods and callback scheduling are never wrapped or replaced.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path

import pytest
import pytestqt.exceptions


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    selected = os.environ.get("SS_FLP_QT_TRACE")
    if not selected:
        return
    destination = Path(selected)
    original = pytestqt.exceptions._except_hook

    def capture(exc_type, value, tb, exceptions=None):
        try:
            with destination.open("a", encoding="utf8") as stream:
                stream.write("\nQt callback exception; original gate receives this unchanged\n")
                traceback.print_stack(file=stream)
                traceback.print_exception(exc_type, value, tb, file=stream)
                frame = tb
                while frame is not None:
                    owner = frame.tb_frame.f_locals.get("self")
                    if owner is not None:
                        stream.write(
                            f"{frame.tb_frame.f_code.co_filename}:"
                            f"{frame.tb_lineno} self={type(owner).__module__}."
                            f"{type(owner).__name__} "
                            f"attributes={sorted(getattr(owner, '__dict__', {}))}\n"
                        )
                    frame = frame.tb_next
        except OSError:
            # Diagnostic I/O cannot replace or hide the original Qt exception.
            traceback.print_exc()
        finally:
            original(exc_type, value, tb, exceptions=exceptions)

    pytestqt.exceptions._except_hook = capture
    config.add_cleanup(lambda: setattr(pytestqt.exceptions, "_except_hook", original))
