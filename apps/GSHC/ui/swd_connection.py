"""One bounded SWD owner thread; no automatic attach or reconnect."""
from threading import Event
from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QTreeWidgetItem
from transport.swd_session import SwdSession, SwdResult, SwdReply
from transport.swd_firmware import Firmware_Import, Targets_List, DiagnosticResult
import time


class FirmwareWorker(QThread):
    update = Signal(object)

    def __init__(self, paths, target, parent=None):
        super().__init__(parent)
        self.paths, self.target, self.cancel = paths, target, Event()

    def run(self):
        self.update.emit(Firmware_Import(self.paths,target=self.target,cancel=self.cancel))


class SwdWorker(QThread):
    update = Signal(object)

    def __init__(self, probe, factory, parent=None, *, target=None, firmware=None):
        super().__init__(parent)
        self.probe = probe
        self.factory = factory
        self.cancel = Event()
        self.session = None
        self.options = {}
        if target: self.options['target'] = target
        if firmware: self.options['firmware'] = firmware

    def run(self):
        try:
            session = self.session = self.factory(cancel=self.cancel,**self.options)
            reply = session.Swd_Attach(self.probe)
            self.update.emit(reply)
            if reply.result == SwdResult.Ok and self.options.get('firmware'):
                if not self.cancel.wait(.1):
                    self.update.emit(SwdReply(SwdResult.Ok,'正在只读核对固件加载内容…'))
                    reply = session.Swd_VerifyFirmware()
                    self.update.emit(reply)
            while reply.result == SwdResult.Ok and not self.cancel.wait(1.0):
                reply = session.Swd_Diagnostics() if self.options.get('firmware') else session.Swd_Snapshot()
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
        self.import_worker = None
        self.firmware = None
        self.rows = ()
        self.import_detail = ''
        page = self.window.maintenance_page
        page.btn_swd_attach.clicked.connect(self.attach)
        page.btn_swd_detach.clicked.connect(self.detach)
        page.swd_target.addItem('自动识别已验证设备族 / Auto', None)
        for name in Targets_List(): page.swd_target.addItem(name,name)
        page.btn_swd_import.clicked.connect(self.import_files)
        page.swd_target.currentTextChanged.connect(self._target_changed)
        self.window.on_swd_render = self.render
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.render)
        self.timer.start()
        self.render()

    def attach(self):
        if self.closing or self.worker is not None or self.probes.worker is not None or self._failed_owner or self.import_worker:
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
        target = self._selected_target()
        self.worker = SwdWorker(probe, self.factory, self, target=target, firmware=self.firmware)
        self.worker.update.connect(self._updated)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.render()
        return True

    def detach(self):
        self.snapshot = None
        self.rows = ()
        if self.import_worker:
            self.import_worker.cancel.set()
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
        if self.worker is None or self.sender() is not self.worker:
            return
        if self.closing or (self.worker is not None and self.worker.cancel.is_set()):
            # Do not suppress a failed release; it is not a successful detach.
            if reply.result != SwdResult.ReleaseFailed:
                return
        self.snapshot = reply.snapshot if reply.result == SwdResult.Ok else None
        self.status = 'swd.' + (reply.snapshot.core_state if self.snapshot else reply.result.value)
        self.detail = reply.detail
        self.rows = reply.diagnostics if reply.result == SwdResult.Ok else ()
        self.render()

    def _finished(self):
        if self.worker is None or self.sender() is not self.worker:
            return
        worker, self.worker = self.worker, None
        if self.status == 'swd.release_failed':
            self._failed_owner = worker
        elif worker is not None:
            worker.deleteLater()
        self.snapshot = None
        self.rows = ()
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
        importing = self.import_worker is not None
        page.btn_swd_attach.setEnabled(bool(self.probes.selection.identity) and
                                      not active and not importing and not self.closing and self.probes.worker is None and not self._failed_owner)
        page.btn_swd_detach.setEnabled((active or importing) and not self.closing)
        page.btn_swd_import.setEnabled(not active and not importing and not self.closing and not self._failed_owner)
        page.swd_target.setEnabled(not active and not importing and not self.closing and not self._failed_owner)
        page.swd_import_status.setText(self.import_detail)
        text = tr(self.status)
        selected = next((p for p in self.probes.selection.probes if p.identity == self.probes.selection.identity), None)
        if selected is not None and selected.family == 'ST-Link':
            text += '\n' + tr('swd.stlink_experimental')
        if self.snapshot:
            snapshot = self.snapshot
            identity = (f'ID 0x{snapshot.device_id:03X} REV 0x{snapshot.revision_id:04X}' if snapshot.device_id else tr('swd.core_verified'))
            text += (f' | {snapshot.target} | {identity}\n' + tr('swd.matched' if snapshot.symbols=='matched' else 'swd.unmatched') +
                     f' | {tr("swd.age")}: {snapshot.age_ms / 1000:.1f}s | ' + tr('swd.non_atomic'))
        if self.detail:
            text += '\n' + self.detail
        page.swd_target_status.setText(text)
        page.swd_diagnostics.setVisible(bool(self.rows))
        page.swd_diagnostics.clear()
        for row in self.rows:
            age = max(0,(time.monotonic_ns()-row['received_ns'])/1e9)
            item = QTreeWidgetItem([row['name']+'\n'+row['id'],row['state']+': '+row['reason'],
                    '; '.join(f'{k}={v}' for k,v in row['fields'].items()),
                    f'{age:.1f}s RX; '+row['consistency']])
            for column in range(4): item.setToolTip(column,item.text(column))
            page.swd_diagnostics.addTopLevelItem(item)

    def _selected_target(self):
        page = self.window.maintenance_page
        return None if page.swd_target.currentIndex()==0 and page.swd_target.currentText()==page.swd_target.itemText(0) else page.swd_target.currentText()

    def _target_changed(self, _):
        if self.worker or self.import_worker: return
        self.firmware = None
        self.rows = ()
        self.import_detail = ''
        self.render()

    def import_files(self, paths=None):
        if self.closing or self.worker or self.import_worker or self._failed_owner: return False
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(self.window,self.window.i18n.tr('swd.import'),'',
                                                  'Firmware diagnostics (*.ssdiag *.elf)')
        if not paths: return False
        self.firmware = None
        self.rows = ()
        self.import_detail = self.window.i18n.tr('swd.importing')
        # A descriptor contains the selected part. Manual ELF uses the combo.
        target = None if any(str(p).lower().endswith('.ssdiag') for p in paths) else self._selected_target()
        self.import_worker = FirmwareWorker(paths,target,self)
        self.import_worker.update.connect(self._imported)
        self.import_worker.finished.connect(self._import_finished)
        self.import_worker.start()
        self.render()
        return True

    def _imported(self, reply):
        if self.import_worker is None or self.sender() is not self.import_worker:
            return
        if self.closing or self.import_worker.cancel.is_set(): return
        self.import_detail = reply.detail
        if reply.result == DiagnosticResult.Ok:
            self.firmware = reply.firmware
            available = sum(not e.unavailable for e in self.firmware.entries)
            self.import_detail = self.window.i18n.tr('swd.imported').format(
                target=self.firmware.target.name,sha=self.firmware.sha256[:12],
                available=available,total=len(self.firmware.entries))
            combo = self.window.maintenance_page.swd_target
            combo.blockSignals(True)
            combo.setCurrentText(self.firmware.target.name)
            combo.blockSignals(False)
        self.render()

    def _import_finished(self):
        if self.import_worker is None or self.sender() is not self.import_worker:
            return
        worker, self.import_worker = self.import_worker, None
        if worker.cancel.is_set():
            self.firmware = None
            self.import_detail = self.window.i18n.tr('swd.cancelled')
        worker.deleteLater()
        self.render()
        if self.closing: self.window.close()

    def request_close(self):
        self.closing = True
        self.timer.stop()
        self.detach()
        return self.worker is None and self.import_worker is None

    def shutdown(self):
        self.request_close()
        imported = self.import_worker is None or self.import_worker.wait(4000)
        return imported and (self.worker is None or self.worker.wait(4000))
