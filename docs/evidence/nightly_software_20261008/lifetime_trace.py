"""Weak-only observer; no GC disabling or object lifetime extension."""
import gc
from pathlib import Path
from threading import get_ident
import pytest
import shiboken6
from PySide6.QtCore import QObject
from silverstar_flp.ui.main_window import MainWindow

stream = (Path(__file__).parent / 'lifetime.jsonl').open('a', encoding='utf-8', buffering=1)
tracked = set()
gui_thread = get_ident()
original = MainWindow.__init__
def observe(window, *args, **kwargs):
    original(window, *args, **kwargs)
    for obj in gc.get_objects():
        if isinstance(obj, QObject) and shiboken6.isValid(obj) and id(obj) not in tracked:
            key = id(obj); tracked.add(key)
            label = type(obj).__module__ + '.' + type(obj).__name__
            def destroyed(*_, key=key, label=label):
                thread = get_ident()
                if thread != gui_thread:
                    import json
                    stream.write(json.dumps(dict(event='wrong_thread_destroy', id=key,
                        label=label, gui=gui_thread, thread=thread)) + '\n')
            obj.destroyed.connect(destroyed)
MainWindow.__init__ = observe

def pytest_runtest_setup(item):
    stream.write('SETUP ' + item.nodeid + '\n')
def pytest_runtest_teardown(item):
    stream.write('TEARDOWN ' + item.nodeid + '\n')
