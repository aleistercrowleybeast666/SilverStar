"""One bounded SWD owner thread; no automatic attach or reconnect."""
from threading import Event
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from transport.swd_session import SwdSession, SwdResult, SwdReply


class SwdWorker(QThread):
    update = Signal(object)

    def __init__(self, probe, factory, parent=None):
        super().__init__(parent)
        self.probe = probe
        self.factory = factory
        self.cancel = Event()
        self.session = None

    def run(self):
        try:
            session = self.session = self.factory(cancel=self.cancel)
            reply = session.Swd_Attach(self.probe)
            self.update.emit(reply)
            while reply.result == SwdResult.Ok and not self.cancel.wait(1.0):
                reply = session.Swd_Snapshot()
                self.update.emit(reply)
        except Exception as exc:
            self.update.emit(SwdReply(SwdResult.TransportError, str(exc)[:400]))
        finally:
            if self.session is not None:
                released = self.session.Swd_Detach()
                if released.result != SwdResult.Ok:
                    self.update.emit(released)


class SwdConnectionManager(QObject):
    def __init__(self, controller, factory=None):
        super().__init__(controller)
        self.window = controller.window
        self.probes = controller.probes
        self.factory = factory or SwdSession
        self.worker = None
        self.closing = False
        self.snapshot = None
        self.status = 'swd.detached'
        self.detail = ''
        self._failed_owner = None
        page = self.window.maintenance_page
        page.btn_swd_attach.clicked.connect(self.attach)
        page.btn_swd_detach.clicked.connect(self.detach)
        self.window.on_swd_render = self.render
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.render)
        self.timer.start()
        self.render()

    def attach(self):
        if self.closing or self.worker is not None or self.probes.worker is not None or self._failed_owner:
            return False
        probe = next((p for p in self.probes.selection.probes
                      if p.identity == self.probes.selection.identity), None)
        if probe is None:
            return False
        self.snapshot = None
        self.status, self.detail = 'swd.connecting', ''
        self.probes.target_active = True
        self.probes.timer.stop()
        self.probes.render()
        self.worker = SwdWorker(probe, self.factory, self)
        self.worker.update.connect(self._updated)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.render()
        return True

    def detach(self):
        self.snapshot = None
        if self._failed_owner:
            self.render()
            return
        if self.worker:
            self.status = 'swd.disconnecting'
            self.worker.cancel.set()
        else:
            self.status = 'swd.detached'
        self.render()

    def _updated(self, reply):
        if self.closing or (self.worker is not None and self.worker.cancel.is_set()):
            # Do not suppress a failed release; it is not a successful detach.
            if reply.result != SwdResult.ReleaseFailed:
                return
        self.snapshot = reply.snapshot if reply.result == SwdResult.Ok else None
        self.status = 'swd.' + (reply.snapshot.core_state if self.snapshot else reply.result.value)
        self.detail = reply.detail
        self.render()

    def _finished(self):
        worker, self.worker = self.worker, None
        if self.status == 'swd.release_failed':
            self._failed_owner = worker
        elif worker is not None:
            worker.deleteLater()
        self.snapshot = None
        if self.status in ('swd.disconnecting', 'swd.connecting') or self.status in (
                'swd.running', 'swd.halted', 'swd.sleeping', 'swd.lockup', 'swd.reset_observed'):
            self.status = 'swd.detached'
        self.probes.target_active = self._failed_owner is not None
        if not self.closing and not self.probes.closing:
            self.probes.timer.start()
            self.probes.render()
        self.render()
        if self.closing:
            self.window.close()

    def render(self):
        page, tr = self.window.maintenance_page, self.window.i18n.tr
        active = self.worker is not None
        page.btn_swd_attach.setEnabled(bool(self.probes.selection.identity) and
                                      not active and not self.closing and self.probes.worker is None and not self._failed_owner)
        page.btn_swd_detach.setEnabled(active and not self.closing)
        text = tr(self.status)
        if self.snapshot:
            snapshot = self.snapshot
            text += (f' | {snapshot.target} | ID 0x{snapshot.device_id:03X} '
                     f'REV 0x{snapshot.revision_id:04X}\n' + tr('swd.unmatched') +
                     f' | {tr("swd.age")}: {snapshot.age_ms / 1000:.1f}s | ' + tr('swd.non_atomic'))
        if self.detail:
            text += '\n' + self.detail
        page.swd_target_status.setText(text)

    def request_close(self):
        self.closing = True
        self.timer.stop()
        self.detach()
        return self.worker is None

    def shutdown(self):
        self.request_close()
        return self.worker is None or self.worker.wait(4000)
