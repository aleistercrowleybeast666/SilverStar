"""Pytest evidence hook. It observes each phase and bounds a stalled case."""
from __future__ import annotations

import faulthandler
import io
import json
import os
from pathlib import Path
import time

import pytest


def _record(event: str, **values) -> None:
    values.update(event=event, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), pid=os.getpid())
    # Filesystem fault-injection tests deliberately reject all Path.open calls.
    # Their guard must stay active for product code without intercepting the
    # independent evidence sink while pytest reports the call phase.
    with io.open(os.environ['SS_FLP_JOURNAL'], 'a', encoding='utf8') as stream:
        stream.write(json.dumps(values, ensure_ascii=False) + '\n')


def pytest_collection_finish(session):
    _record('collection', ids=[item.nodeid for item in session.items])


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    _record('start', node=item.nodeid)
    # The built-in C watchdog also works inside a native Qt modal event loop.
    # On a deadline exit only this test process. The journal retains the case.
    dump = Path(os.environ['SS_FLP_JOURNAL']).with_suffix('.watchdog.log')
    with io.open(dump, 'a', encoding='utf8') as stream:
        faulthandler.dump_traceback_later(int(os.environ['SS_FLP_CASE_SECONDS']),
                                          file=stream, exit=True)
        try:
            result = yield
            _record('finished', node=item.nodeid)
            return result
        finally:
            faulthandler.cancel_dump_traceback_later()


def pytest_runtest_logreport(report):
    _record('phase', node=report.nodeid, phase=report.when, result=report.outcome,
            seconds=round(report.duration, 4),
            reason=str(report.longrepr) if report.failed or report.skipped else '')
