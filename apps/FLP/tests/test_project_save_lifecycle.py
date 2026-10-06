"""Deterministic tiny save lifecycle fault cases; no long replay."""
from threading import Event
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from silverstar_flp.core.project import Project_Load
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from tests.test_project_artifact_boundaries import _SmallRun

@pytest.mark.parametrize('case',['clean_close','cancel_close_option','cancel_after_commit'])
def test_save_lifecycle_respects_request_cancel_and_commit(qtbot,tmp_path,monkeypatch,case):
    import silverstar_flp.ui.main_window as module
    opened,document,_=_SmallRun(tmp_path)
    window=MainWindow(builtin_registry());qtbot.addWidget(window)
    window._LogOpenResult_Set(opened,document)
    errors=[];monkeypatch.setattr(window,'_Error_Show',errors.append)
    monkeypatch.setattr(QMessageBox,'warning',lambda *_:QMessageBox.StandardButton.Discard)
    began=Event();release=Event();original=module.Project_Save
    def controlled(*args,**kwargs):
        if case=='cancel_after_commit':
            original(*args,**kwargs);began.set();assert release.wait(5)
        else:
            began.set();assert release.wait(5);original(*args,**kwargs)
    monkeypatch.setattr(module,'Project_Save',controlled)
    target=tmp_path/'save-as.ssflp'
    window._Project_Write(target,background=True,save_data=False)
    qtbot.waitUntil(began.is_set,timeout=5000)
    try:
        if case=='clean_close':
            window._Project_SetDirty(False);event=QCloseEvent();window.closeEvent(event)
            assert not event.isAccepted()
        elif case=='cancel_close_option':
            window._Project_SetDirty(True)
            monkeypatch.setattr(QMessageBox,'warning',lambda *_:QMessageBox.StandardButton.Save)
            monkeypatch.setattr(window,'_SaveOptions_Select',lambda:None)
            QTimer.singleShot(50,release.set)
            assert not window._ProjectChanges_Confirm()
        else:
            assert target.is_file()
            window._active_worker.Worker_Cancel()
    finally:
        release.set()
        qtbot.waitUntil(lambda:window._active_worker is None,timeout=5000)
        window._Project_SetDirty(False)
    assert not errors and target.is_file()
    if case=='cancel_after_commit':
        assert window._project.project_path==target.resolve()
        assert not window._project.save_data_and_results
        assert not Project_Load(target).save_data_and_results
    window.close()
