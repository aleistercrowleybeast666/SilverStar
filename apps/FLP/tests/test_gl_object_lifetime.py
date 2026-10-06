"""GC-on native thread/ownership regressions; no rendered OpenGL or log data."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('case',['mainwindow','transfer','multiple'])
def test_gui_owned_gl_tree_survives_scene_changes_and_worker_collection(tmp_path,case):
    trace = tmp_path/(case+'.jsonl')
    environment = {**os.environ,'QT_QPA_PLATFORM':'offscreen'}
    command = [sys.executable,'-X','faulthandler',
        str(Path(__file__).with_name('gl_lifecycle_probe.py')),case,'--trace',str(trace)]
    result = subprocess.run(command,env=environment,capture_output=True,text=True,timeout=35)
    (tmp_path/(case+'-stdout.txt')).write_text(result.stdout,encoding='utf-8')
    (tmp_path/(case+'-stderr.txt')).write_text(result.stderr,encoding='utf-8')
    (tmp_path/(case+'-exit.txt')).write_text(str(result.returncode),encoding='utf-8')
    assert result.returncode==0, (result.returncode,result.stdout,result.stderr)
    entries = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    summary = next(entry for entry in entries if entry['kind']=='summary')
    assert summary['wrong_thread_native_count']==0 and summary['gc_enabled']
    assert any(entry['kind']=='worker_gc_done' for entry in entries)
    tracked = {entry['object']['id']:entry['object'] for entry in entries if entry['kind']=='tracked'}
    native = [entry for entry in entries if entry['kind']=='native_destroyed']
    assert tracked and all(info['affinity_gui'] and not info['python_owned']
                           and not info['parentless'] for info in tracked.values())
    assert all(sum(entry['object']['id']==identity for entry in native)==1 for identity in tracked)
    for entry in entries:
        if entry['kind']=='native_destroyed':
            assert entry['thread']==entries[0]['gui_thread']
