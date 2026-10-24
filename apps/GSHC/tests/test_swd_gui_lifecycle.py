"""Real Qt/ARM ELF, synthetic memory only. Faults retain all acceptance checks."""
import json
from pathlib import Path
from threading import Event
import time

import pytest
from PySide6.QtCore import QTimer,QThread
from PySide6.QtWidgets import QApplication

import ui.swd_connection as module
from test_probe_ui import panel
from test_swd_ui import swd_panel,wait_for
from test_swd_firmware import arm_elf,ImageMemory,load
from transport.swd_firmware import FirmwareReply,DiagnosticResult
from transport.swd_session import SwdSession,SwdResult,SwdError,SwdReply


def state(manager):
    worker=manager.worker
    return {'status':manager.status,'detail':manager.detail,'rows':len(manager.rows),
        'firmware':bool(manager.firmware),'worker':bool(worker),'worker_finished':worker.isFinished() if worker else None,
        'import_worker':bool(manager.import_worker),'import_finished':manager.import_worker.isFinished() if manager.import_worker else None,
        'failed_owner':bool(manager._failed_owner),'restart':manager._restart_after_import,'intent':manager._attach_intent,
        'probe_worker':bool(manager.probes.worker),'target_active':manager.probes.target_active,
        'pause':manager.window.maintenance_page.swd_watch.pause.isChecked(),
        'selection':worker._get_selection() if worker else None}


def wait_state(manager,predicate,path,seconds=4):
    deadline=time.monotonic()+seconds;events=[]
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents();time.sleep(.01)
        events.append(dict(time=time.monotonic(),**state(manager)))
        events=events[-160:]
    path.write_text(json.dumps(events,indent=2),encoding='utf-8')
    assert predicate(),state(manager)


def connected(create,arm_elf):
    firmware=load(arm_elf);backends=[]
    def factory(**kwargs):
        backend=ImageMemory(kwargs['firmware']);backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory);manager.firmware=firmware
    assert manager.attach();wait_for(lambda:bool(manager.rows))
    return manager,backends


@pytest.mark.parametrize('repeat',[0,1,2])
def test_reimport_twenty_times_without_changing_four_second_expectation(swd_panel,arm_elf,tmp_path,repeat):
    _,_,create=swd_panel;manager,backends=connected(create,arm_elf)
    descriptor=tmp_path/'fixture.ssdiag';descriptor.write_text(json.dumps(load(arm_elf).descriptor))
    for index in range(20):
        assert manager.import_files([descriptor,arm_elf] if index==0 else [arm_elf])
        assert manager.snapshot is None and not manager.rows
        wait_state(manager,lambda:manager.import_worker is None and bool(manager.rows),tmp_path/f'iteration{index:02}.json')
        assert manager.snapshot.symbols=='matched'
    assert len(backends)==21 and all(b.closed==1 for b in backends[:-1])


def test_unexpected_import_exception_has_terminal_error(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None)
    def broken(*args,**kwargs):raise RuntimeError('injected import failure')
    monkeypatch.setattr(module,'Firmware_ImportAuto',broken)
    assert manager.import_files([arm_elf]);wait_for(lambda:manager.import_worker is None)
    assert manager.status=='swd.import_failed' and 'injected import failure' in manager.detail
    assert not manager.firmware and not manager.rows


def test_finished_worker_result_survives_missing_update_signal(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;firmware=load(arm_elf);manager=create(lambda **_:None)
    class NoUpdate(module.FirmwareWorker):
        def run(self):self.reply=FirmwareReply(DiagnosticResult.Ok,firmware=firmware)
    monkeypatch.setattr(module,'FirmwareWorker',NoUpdate)
    assert manager.import_files([arm_elf]);wait_for(lambda:manager.import_worker is None)
    assert manager.firmware is firmware and manager.status=='swd.detached'


def test_import_timeout_ignores_late_success_and_keeps_ui_responsive(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None);firmware=load(arm_elf)
    entered=Event();release=Event();ticks=[]
    def stuck(*args,**kwargs):
        entered.set();release.wait(3)
        return FirmwareReply(DiagnosticResult.Ok,firmware=firmware)
    monkeypatch.setattr(module,'Firmware_ImportAuto',stuck)
    manager.IMPORT_TIMEOUT_SECONDS=.05;manager.CANCEL_GRACE_SECONDS=.05
    heartbeat=QTimer(manager);heartbeat.setInterval(10);heartbeat.timeout.connect(lambda:ticks.append(1));heartbeat.start()
    try:
        assert manager.import_files([arm_elf]);wait_for(entered.is_set)
        deadline=time.monotonic()+.8
        while time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
        assert manager.import_worker.cancel.is_set() and len(ticks)>=10
        assert manager.status in ('swd.import_timeout','swd.cancel_pending')
        assert not manager.import_files([arm_elf]) and not manager.attach()
    finally:
        release.set();wait_for(lambda:manager.import_worker is None);heartbeat.stop()
    assert manager.firmware is None and not manager.rows


def test_close_with_stuck_import_cancels_without_blocking_gui(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None);entered=Event();release=Event()
    def stuck(*args,**kwargs):
        entered.set();release.wait(3)
        return FirmwareReply(DiagnosticResult.Cancelled,'cancelled')
    monkeypatch.setattr(module,'Firmware_ImportAuto',stuck)
    manager.CANCEL_GRACE_SECONDS=.05
    try:
        assert manager.import_files([arm_elf]);wait_for(entered.is_set)
        started=time.monotonic();assert manager.request_close() is False
        assert time.monotonic()-started<.1
        deadline=time.monotonic()+.8
        while time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
        assert manager.status=='swd.cancel_pending' and not manager.closing
        assert manager.import_worker is not None and manager.import_worker.cancel.is_set()
    finally:
        release.set();wait_for(lambda:manager.import_worker is None)


def test_reimport_release_timeout_retains_owner_and_prevents_restart(swd_panel,arm_elf,monkeypatch,tmp_path):
    _,_,create=swd_panel;manager,backends=connected(create,arm_elf);release=Event();entered=Event()
    old=backends[0];close=old.close
    def stuck():entered.set();release.wait(3);return close()
    old.close=stuck
    manager.CANCEL_GRACE_SECONDS=.05
    descriptor=tmp_path/'fixture.ssdiag';descriptor.write_text(json.dumps(manager.firmware.descriptor))
    try:
        assert manager.import_files([descriptor,arm_elf]);wait_for(entered.is_set)
        deadline=time.monotonic()+.8
        while time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
        assert manager.status=='swd.cancel_pending' and manager.worker is not None
        assert manager.probes.target_active and len(backends)==1
        assert not manager.snapshot and not manager.rows
    finally:
        release.set();wait_for(lambda:manager.worker is None)
    assert len(backends)==1 and not manager._restart_after_import


def test_failed_release_blocks_close_and_can_retry_only_its_owned_session(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,backends=connected(create,arm_elf);permitted=Event();backend=backends[0];close=backend.close
    def failing():
        if not permitted.is_set():raise SwdError(SwdResult.ReleaseFailed,'injected release failure')
        return close()
    backend.close=failing
    try:
        manager.detach();wait_for(lambda:manager.worker is None)
        assert manager._failed_owner and manager.probes.target_active
        assert not manager.attach()
        assert manager.request_close() is False
        deadline=time.monotonic()+.5
        while time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
        assert manager._failed_owner and not manager.closing
        assert manager.window.maintenance_page.btn_swd_detach.isEnabled()
        permitted.set();manager.detach();wait_for(lambda:manager._failed_owner is None)
        assert not manager.probes.target_active and len(backends)==1 and backend.closed==1
    finally:
        permitted.set()
        if manager._failed_owner:
            manager._failed_owner.session.Swd_Detach();manager._failed_owner=None


def test_result_completes_after_deadline_before_watchdog_dispatch(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None);firmware=load(arm_elf)
    def slow(*args,**kwargs):
        time.sleep(.08)
        return FirmwareReply(DiagnosticResult.Ok,firmware=firmware)
    monkeypatch.setattr(module,'Firmware_ImportAuto',slow)
    manager.IMPORT_TIMEOUT_SECONDS=.03
    assert manager.import_files([arm_elf])
    assert manager.import_worker.wait(1000)  # Deliberately hold GUI dispatch.
    wait_for(lambda:manager.import_worker is None)
    assert manager.status=='swd.import_timeout' and not manager.firmware


def test_worker_without_any_outcome_gets_explicit_error(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None)
    class NoOutcome(module.FirmwareWorker):
        def run(self):pass
    monkeypatch.setattr(module,'FirmwareWorker',NoOutcome)
    assert manager.import_files([arm_elf]);wait_for(lambda:manager.import_worker is None)
    assert manager.status=='swd.import_failed' and 'without a result' in manager.detail


def test_worker_updates_and_import_publication_stay_on_gui_thread(swd_panel,arm_elf,monkeypatch,tmp_path):
    window,_,create=swd_panel;observed=[];original=window.maintenance_page.set_swd_summary
    def summary(value, **kwargs):
        observed.append(QThread.currentThread() is QApplication.instance().thread())
        return original(value, **kwargs)
    monkeypatch.setattr(window.maintenance_page,'set_swd_summary',summary)
    manager,backends=connected(create,arm_elf)
    descriptor=tmp_path/'fixture.ssdiag';descriptor.write_text(json.dumps(manager.firmware.descriptor))
    assert manager.import_files([descriptor,arm_elf]);wait_for(lambda:manager.import_worker is None and bool(manager.rows))
    assert observed and all(observed) and len(backends)==2


def test_repeated_cancel_does_not_reset_deadline_or_create_more_workers(swd_panel,arm_elf,monkeypatch):
    _,_,create=swd_panel;manager=create(lambda **_:None);release=Event();entered=Event()
    def stuck(*args,**kwargs):
        entered.set();release.wait(3)
        return FirmwareReply(DiagnosticResult.Cancelled,'cancelled')
    monkeypatch.setattr(module,'Firmware_ImportAuto',stuck)
    try:
        assert manager.import_files([arm_elf]);wait_for(entered.is_set)
        worker=manager.import_worker;manager.detach();started=worker.cancel_started
        for _ in range(5):manager.detach()
        assert manager.import_worker is worker and worker.cancel_started==started
    finally:
        release.set();wait_for(lambda:manager.import_worker is None)


def test_shutdown_has_one_total_wait_budget_and_retains_slow_owner(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,backends=connected(create,arm_elf);release=Event();close=backends[0].close
    def slow():release.wait(3);return close()
    backends[0].close=slow;manager.SHUTDOWN_WAIT_SECONDS=.05
    try:
        started=time.monotonic();assert manager.shutdown() is False
        assert time.monotonic()-started<.25 and manager.worker is not None
        assert manager.probes.target_active and not manager.snapshot and not manager.rows
    finally:
        release.set();wait_for(lambda:manager.worker is None)


def rate_manager(create,elf,verify=0,sample=0,permanent=False):
    sessions=[];backends=[]
    class Limited(SwdSession):
        verify_calls=0
        sample_calls=0
        def Swd_VerifyFirmware(self):
            self.verify_calls+=1
            if verify and (permanent or self.verify_calls<=verify):return SwdReply(SwdResult.RateLimited,'injected ordinary backpressure')
            return super().Swd_VerifyFirmware()
        def Swd_Diagnostics(self,*args):
            self.sample_calls+=1
            if sample and (permanent or self.sample_calls<=sample):return SwdReply(SwdResult.RateLimited,'injected ordinary backpressure')
            return super().Swd_Diagnostics(*args)
    def factory(**kwargs):
        backend=ImageMemory(kwargs['firmware']);backends.append(backend)
        session=Limited(**kwargs,_backend_factory=lambda _:backend);sessions.append(session)
        return session
    manager=create(factory);manager.firmware=load(elf);assert manager.attach()
    return manager,sessions,backends


def test_rate_verify_transient_keeps_connection_until_full_match(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,sessions,backends=rate_manager(create,arm_elf,verify=1)
    wait_for(lambda:bool(manager.rows))
    assert manager.snapshot.symbols=='matched' and sessions[0].verify_calls==2 and backends[0].closed==0


def test_rate_sample_transient_waits_next_period_without_disconnect(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,sessions,backends=rate_manager(create,arm_elf,sample=1)
    wait_for(lambda:bool(manager.rows))
    assert sessions[0].sample_calls==2 and backends[0].closed==0 and manager.worker is not None


def test_rate_verify_permanent_is_bounded_timeout_not_ram_or_busy_loop(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,sessions,backends=rate_manager(create,arm_elf,verify=1,permanent=True)
    wait_for(lambda:manager.worker is None)
    assert manager.status=='swd.timeout' and sessions[0].verify_calls==3
    assert not manager.rows and backends[0].closed==1
    assert not any(0x10000000<=a<0x10010000 or 0x20000000<=a<0x20020000 for a,_ in backends[0].reads)


def test_rate_sample_permanent_is_bounded_timeout_with_release(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,sessions,backends=rate_manager(create,arm_elf,sample=1,permanent=True)
    wait_for(lambda:manager.worker is None)
    assert manager.status=='swd.timeout' and sessions[0].sample_calls==3 and backends[0].closed==1


def test_rate_wait_is_cancellable_without_another_request(swd_panel,arm_elf):
    _,_,create=swd_panel;manager,sessions,backends=rate_manager(create,arm_elf,verify=1,permanent=True)
    wait_for(lambda:bool(sessions) and sessions[0].verify_calls==1)
    manager.detach();wait_for(lambda:manager.worker is None)
    assert sessions[0].verify_calls==1 and backends[0].closed==1 and not manager.rows


def test_rate_early_wait_uses_real_unchanged_session_gate(swd_panel,arm_elf,monkeypatch,tmp_path):
    _,_,create=swd_panel
    class EarlyEvent:
        def __init__(self):self.event=Event();self.used=False
        def is_set(self):return self.event.is_set()
        def set(self):self.event.set()
        def wait(self,seconds):
            if seconds==.1 and not self.used:
                self.used=True
                return self.event.wait(.01)
            return self.event.wait(seconds)
    monkeypatch.setattr(module,'Event',EarlyEvent)
    firmware=load(arm_elf);backends=[]
    def factory(**kwargs):
        backend=ImageMemory(firmware);backends.append(backend)
        return SwdSession(**kwargs,_backend_factory=lambda _:backend)
    manager=create(factory);manager.firmware=firmware;assert manager.attach()
    wait_state(manager,lambda:bool(manager.rows),tmp_path/'early-wait.json')
    assert manager.snapshot.symbols=='matched' and backends[0].closed==0
