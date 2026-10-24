"""Dispose GUI test cycles on their owner thread after fixture references leave.

The application runs a Qt event loop. The tests also use processEvents-only
polling, which does not deliver DeferredDelete like that event loop does.
Automatic Python GC stays enabled, including while worker threads run.
"""
import gc

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread


def QtTest_DisposeDeferred():
    application = QCoreApplication.instance()
    if application is None:
        return
    assert QThread.currentThread() is application.thread(), "GUI test cleanup must run on the application thread"
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    application.processEvents()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    try:
        return (yield)
    finally:
        # The runner has cleared item.funcargs and completed fixture teardown
        # now. An autouse fixture's finalizer is too early for these cycles.
        QtTest_DisposeDeferred()
