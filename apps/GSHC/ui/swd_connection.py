"""One bounded SWD owner thread; no automatic attach or reconnect."""
from threading import Event, Lock
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import QFileDialog, QTreeWidgetItem
from transport.swd_session import SwdSession, SwdResult, SwdReply
from transport.swd_firmware import DiagnosticResult, FirmwareReply
from services.swd_import import Firmware_ImportAuto
import time
import logging
from ui.diagnostic_labels import DiagnosticValue_Format, DiagnosticReason_Format, DiagnosticState_Format, Text

_logger = logging.getLogger(__name__)


class FirmwareWorker(QThread):
    update = Signal(object)

    def __init__(self, paths, target_cache, parent=None):
        super().__init__(parent)
        self.paths, self.target_cache, self.cancel = paths, dict(target_cache), Event()
        self.reply = None
        self.completed_at = None
        self.cancel_started = None

    def run(self):
        try:
            self.reply = Firmware_ImportAuto(self.paths,target_cache=self.target_cache,cancel=self.cancel)
            if not isinstance(self.reply,FirmwareReply):
                raise TypeError('Importer returned no diagnostic result')
        except Exception as exc:
            _logger.exception('Firmware diagnostic import worker failed')
            self.reply = FirmwareReply(DiagnosticResult.InvalidFile,str(exc)[:400])
        self.completed_at = time.monotonic()
        self.update.emit(self.reply)


class SwdReleaseWorker(QThread):
    """Retry only the already-owned session's release, never attach or read."""
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session, self.reply = session, None
        self.started_at = time.monotonic()
        self.timeout_reported = False

    def run(self):
        try:
            self.reply = self.session.Swd_Detach()
            if not isinstance(self.reply,SwdReply):
                raise TypeError('Release returned no result')
        except Exception as exc:
            _logger.exception('SWD owned-session release retry failed')
            self.reply = SwdReply(SwdResult.ReleaseFailed,str(exc)[:400])


class SwdWorker(QThread):
    update = Signal(object)
    VERIFY_START_MAX_ATTEMPTS = 3
    SAMPLE_RATE_LIMIT_MAX = 3

    def __init__(self, probe, factory, parent=None, *, target=None, firmware=None):
        super().__init__(parent)
        self.probe = probe
        self.factory = factory
        self.cancel = Event()
        self.session = None
        self.release_reply = None
        self.cancel_started = None
        self.options = {}
        self._selection_lock = Lock()
        self._selection = ((),1.0,False,0)
        if target: self.options['target'] = target
        if firmware: self.options['firmware'] = firmware

    def set_selection(self, identifiers, interval, paused, revision):
        # One replaceable configuration, never a growing work queue.
        if (type(interval) not in (int,float) or interval not in (1,2,5) or type(paused) is not bool or
                type(revision) is not int or revision < 0 or type(identifiers) not in (tuple,list) or
                len(identifiers)>16 or any(type(item) is not str for item in identifiers)):
            raise ValueError('Invalid watch sampling configuration')
        with self._selection_lock:
            self._selection = (tuple(identifiers),interval,paused,revision)

    def _get_selection(self):
        with self._selection_lock: return self._selection

    def _verify_firmware(self, session):
        # An Event wait is not admission to the service's monotonic rate gate.
        # Keep that gate authoritative; retry only ordinary backpressure, with
        # a finite attempt count and a cancellable wait before each request.
        for _ in range(self.VERIFY_START_MAX_ATTEMPTS):
            if self.cancel.wait(.1):
                return SwdReply(SwdResult.Cancelled,'Verification start cancelled')
            reply = session.Swd_VerifyFirmware()
            if reply.result != SwdResult.RateLimited:return reply
        return SwdReply(SwdResult.Timeout,'Firmware verification admission remained rate limited')

    def run(self):
        try:
            session = self.session = self.factory(cancel=self.cancel,**self.options)
            started = time.monotonic()
            reply = session.Swd_Attach(self.probe)
            identity = reply.snapshot
            self.update.emit(reply)
            attached = reply.result == SwdResult.Ok
            matched = False
            rate_limited = 0
            if reply.result == SwdResult.Ok and self.options.get('firmware'):
                if not self.cancel.is_set():
                    self.update.emit(SwdReply(SwdResult.Ok,'正在只读核对固件加载内容…'))
                    reply = self._verify_firmware(session)
                    matched = reply.result == SwdResult.Ok
                    if identity and reply.result in (SwdResult.Ok, SwdResult.FirmwareMismatch):
                        identity = replace(identity, symbols='matched' if matched else 'unmatched',
                                           firmware_status='matched' if matched else 'mismatch')
                        reply = replace(reply, snapshot=identity)
                    self.update.emit(reply)
                    attached = reply.result in (SwdResult.Ok, SwdResult.FirmwareMismatch)
            while attached:
                identifiers,interval,paused,revision = self._get_selection()
                if self.cancel.wait(interval): break
                # Recheck after waiting; a paused or replaced selection does not
                # cause one more read using stale configuration.
                identifiers,_,paused,revision = self._get_selection()
                if time.monotonic()-started >= SwdSession.MAX_SECONDS:
                    reply = SwdReply(SwdResult.BudgetExceeded,'Session time limit reached; explicitly reconnect')
                    self.update.emit(reply)
                    break
                # Mismatch retains identity/ownership only. No rescan or RAM
                # sampling until an explicit reimport rebuilds the connection.
                if paused or self.options.get('firmware') and not matched: continue
                reply = (session.Swd_Inspect(identifiers) if identifiers and self.options.get('firmware') else
                         session.Swd_Diagnostics() if self.options.get('firmware') else session.Swd_Snapshot())
                if reply.result == SwdResult.RateLimited:
                    rate_limited += 1
                    if rate_limited < self.SAMPLE_RATE_LIMIT_MAX:continue
                    reply = SwdReply(SwdResult.Timeout,'Sampling admission remained rate limited')
                else:rate_limited = 0
                self.update.emit(replace(reply,watch_revision=revision))
                attached = reply.result == SwdResult.Ok
        except Exception as exc:
            _logger.exception('SWD owner worker failed')
            self.update.emit(SwdReply(SwdResult.TransportError, str(exc)[:400]))
        finally:
            if self.session is not None:
                try:
                    self.release_reply = self.session.Swd_Detach()
                    if not isinstance(self.release_reply,SwdReply):
                        raise TypeError('Release returned no result')
                except Exception as exc:
                    _logger.exception('SWD owner release failed')
                    self.release_reply = SwdReply(SwdResult.ReleaseFailed,str(exc)[:400])
                if self.release_reply.result != SwdResult.Ok:
                    self.update.emit(self.release_reply)


class SwdConnectionManager(QObject):
    IMPORT_TIMEOUT_SECONDS = 25.0
    CANCEL_GRACE_SECONDS = 4.0
    SHUTDOWN_WAIT_SECONDS = 4.0

    def __init__(self, controller, factory=None):
        super().__init__(controller)
        self.window = controller.window
        self.probes = controller.probes
        self.factory = factory or SwdSession
        self.worker = None
        self.closing = False
        self.snapshot = None
        self.last_identity = None
        self.status = 'swd.detached'
        self.detail = ''
        self._failed_owner = None
        self.import_worker = None
        self._release_worker = None
        self._import_started = 0.0
        self._pending_import_reply = None
        self._import_aborted = False
        self._operation_error = None
        self.firmware = None
        self.rows = ()
        self.import_detail = ''
        self.watch_rows = ()
        self._watch_revision = 0
        self.budget = None
        self.core_observation = ''
        self._attach_intent = False
        self._restart_after_import = False
        self._restart_probe = ''
        self._bound_targets = {}
        self._descriptor_path = None
        page = self.window.maintenance_page
        page.btn_swd_attach.clicked.connect(self.attach)
        page.btn_swd_detach.clicked.connect(self.detach)
        page.btn_swd_import.clicked.connect(self.import_files)
        if hasattr(page,'btn_swd_relocate'):page.btn_swd_relocate.clicked.connect(self.relocate_elf)
        page.swd_watch.selection_changed.connect(self._watch_changed)
        page.btn_swd_variables.clicked.connect(page.watch_dialog.show)
        page.watch_dialog.visibility_changed.connect(self._watch_changed)
        self.window.on_swd_render = self.render
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.render)
        self.timer.start()
        self.lifecycle_timer = QTimer(self)
        self.lifecycle_timer.setInterval(100)
        self.lifecycle_timer.timeout.connect(self._poll_lifecycle)
        self.lifecycle_timer.start()
        self.render()

    def attach(self):
        if self.closing or self.worker is not None or self.probes.worker is not None or self._failed_owner or self.import_worker or self._release_worker:
            return False
        probe = next((p for p in self.probes.selection.probes
                      if p.identity == self.probes.selection.identity), None)
        if probe is None:
            return False
        self._attach_intent = True
        self._operation_error = None
        self.snapshot = None
        self.status, self.detail = 'swd.connecting', ''
        self.probes.target_active = True
        self.probes.render()
        target = self.firmware.target.name if self.firmware else None
        self.worker = SwdWorker(probe, self.factory, self, target=target, firmware=self.firmware)
        panel = self.window.maintenance_page.swd_watch
        self.worker.set_selection(panel.selected if self.window.maintenance_page.watch_dialog.isVisible() else (),
                                  panel.interval.currentData(),panel.pause.isChecked(),self._watch_revision)
        self.worker.update.connect(self._updated,Qt.QueuedConnection)
        self.worker.finished.connect(self._finished,Qt.QueuedConnection)
        self.worker.start()
        self.render()
        return True

    def detach(self):
        self._attach_intent = self._restart_after_import = False
        self.snapshot = None
        self.rows = ()
        self.watch_rows = ()
        if self.import_worker:
            self._cancel_worker(self.import_worker)
            self._import_aborted = True
        if self._failed_owner:
            if self._release_worker is None:
                self._release_worker = SwdReleaseWorker(self._failed_owner.session,self)
                self._release_worker.finished.connect(self._release_finished,Qt.QueuedConnection)
                self._release_worker.start()
                # The prior failure remains authoritative until this retry
                # actually confirms release. Do not imply ownership is clear.
                self.status = 'swd.release_failed'
            self.render()
            return
        if self.worker:
            self.status = 'swd.disconnecting'
            self._cancel_worker(self.worker)
        else:
            self.status = 'swd.detached'
        self.render()

    @Slot(object)
    def _updated(self, reply):
        if self.worker is None or self.sender() is not self.worker:
            return
        if self.closing or (self.worker is not None and self.worker.cancel.is_set()):
            # Do not suppress a failed release; it is not a successful detach.
            if reply.result != SwdResult.ReleaseFailed:
                return
        self.snapshot = reply.snapshot if reply.result in (SwdResult.Ok, SwdResult.FirmwareMismatch) else None
        if self.snapshot: self.last_identity = self.snapshot
        self.status = 'swd.' + (reply.snapshot.core_state if self.snapshot and reply.result == SwdResult.Ok else reply.result.value)
        self.detail = reply.detail
        self.rows = reply.diagnostics if reply.result == SwdResult.Ok else ()
        self.watch_rows = reply.watches if reply.result == SwdResult.Ok and reply.watch_revision == self._watch_revision else ()
        self.budget = reply.budget
        self.core_observation = reply.core_observation
        self.render()

    @Slot()
    def _finished(self):
        if self.worker is not None and self.sender() is self.worker:
            self._finish_swd(self.worker)

    def _finish_swd(self, worker):
        if worker is not self.worker:return
        self.worker = None
        released = worker.release_reply
        if worker.session is not None and (released is None or released.result != SwdResult.Ok):
            self._failed_owner = worker
            self.closing = False
            self.status, self.detail = 'swd.release_failed', released.detail if released else 'Release outcome missing'
        elif worker is not None:
            worker.deleteLater()
        self.snapshot = None
        self.rows = ()
        self.watch_rows = ()
        if self._operation_error:
            self.status,self.detail = self._operation_error
        elif not self._restart_after_import and self.status in ('swd.disconnecting','swd.connecting',
                'swd.running','swd.halted','swd.sleeping','swd.lockup','swd.reset_observed'):
            self.status = 'swd.detached'
        self._settle_owner()
        self.render()
        self._maybe_close()

    def _settle_owner(self):
        if self._failed_owner:
            self._restart_after_import = self._attach_intent = False
            if self._release_worker is None:
                self.status = 'swd.release_failed'
                released = self._failed_owner.release_reply
                self.detail = released.detail if released else 'Release outcome missing'
            self.probes.target_active = True
            self.probes.render()
            return
        if self.worker or self.import_worker or self._release_worker:
            return
        if self._restart_after_import and self._attach_intent and self.firmware and not self.closing:
            self._restart_after_import = False
            probe = next((p for p in self.probes.selection.probes if p.identity==self._restart_probe),None)
            if probe is not None and self.probes.selection.identity==self._restart_probe and self.probes.worker is None:
                self.attach()
                return
            self._attach_intent = False
            self.status, self.detail = 'swd.invalid_request', 'Selected probe changed during import; explicitly reconnect'
        self.probes.target_active = False
        if not self.closing and not self.probes.closing:
            self.probes.render()

    def render(self):
        from ui.connection_controls import HeaderStatus_Set, ConnectionActions_Render
        page, tr = self.window.maintenance_page, self.window.i18n.tr
        active = self.worker is not None
        importing = self.import_worker is not None
        stopping = bool(self.worker and self.worker.cancel.is_set())
        matched = bool(active and not stopping and self.snapshot and self.snapshot.symbols=='matched')
        page.btn_swd_attach.setEnabled(bool(self.probes.selection.identity) and not self._release_worker and
                                      not active and not importing and not self.closing and self.probes.worker is None and not self._failed_owner)
        page.btn_swd_detach.setEnabled(bool(active or importing or self._failed_owner) and not self.closing and not self._release_worker)
        if stopping:page.btn_swd_detach.setEnabled(False)
        page.btn_swd_import.setEnabled(not importing and not self.closing and not self._failed_owner and not self._release_worker
                                      and not (self.worker and self.worker.cancel.is_set()))
        if hasattr(page,'btn_swd_relocate'):
            page.btn_swd_relocate.setEnabled(page.btn_swd_import.isEnabled() and bool(self._descriptor_path))
            page.btn_swd_relocate.setVisible(getattr(self,'_elf_selection_required',False))
        owned=bool(active or importing or self._failed_owner or self._release_worker)
        ConnectionActions_Render(page.btn_swd_attach,page.btn_swd_detach,self.window.i18n,
            owned=owned,cancelling=bool(importing or active and self.snapshot is None),retry=bool(self._failed_owner))
        page.btn_swd_variables.setEnabled(matched and bool(self.firmware and any(not item.unavailable for item in self.firmware.watches)))
        page.swd_watch.setEnabled(matched)
        page.swd_import_status.setText((Text(self.window.i18n,'符号已导入：','Symbols imported: ')+self.firmware.target.name)
            if self.firmware else (self.import_detail or tr('swd.import_hint')))
        page.swd_import_status.setToolTip(self.import_detail)
        page.swd_watch.set_firmware(self.firmware)
        page.swd_watch.update_rows(self.watch_rows,matched)
        text = tr(self.status)
        if hasattr(self.window,'header_swd_status'):
            failed = active and self.status in {'swd.'+result.value for result in (
                SwdResult.FirmwareMismatch,SwdResult.TargetMismatch,SwdResult.TransportError,
                SwdResult.Timeout,SwdResult.SafetyNotProven,SwdResult.BudgetExceeded)}
            caption=(('释放失败','Close failed') if self._failed_owner else
                     (('释放中','Releasing') if self._release_worker or self.closing or stopping else
                      (('导入中','Importing') if importing else
                       (('异常','Error') if failed else
                        (('连接中','Connecting') if active and self.snapshot is None else
                        (('已连接','Connected') if matched else
                         (('未匹配','Unmatched') if active else ('未连接','Disconnected'))))))))
            HeaderStatus_Set(self.window.header_swd_status,Text(self.window.i18n,*caption),text+'\n'+self.detail)
        selected = next((p for p in self.probes.selection.probes if p.identity == self.probes.selection.identity), None)
        if self.snapshot:
            snapshot = self.snapshot
            text += (' · ' + tr('swd.matched' if snapshot.symbols=='matched' else 'swd.unmatched') +
                     f' | {tr("swd.age")}: {snapshot.age_ms / 1000:.1f}s | ' + tr('swd.non_atomic'))
        details = [self.detail] if self.detail else []
        if selected is not None and selected.family=='ST-Link':
            text += '\n' + tr('swd.stlink_experimental')
            details.append(tr('swd.stlink_experimental'))
        if self.firmware:
            details.append('ELF SHA256: '+self.firmware.sha256)
            details.extend(entry.id+': '+(entry.unavailable or 'resolved') for entry in self.firmware.entries)
        observation = self.snapshot or self.last_identity
        if observation:
            prefix = tr('swd.target_current' if self.snapshot and active else 'swd.target_previous')
            expected = self.firmware.target.name if self.firmware else tr('swd.target_no_descriptor')
            observed = ('STM32F405/407/415/417 (ID 0x413)' if observation.device_id==0x413 else
                        f'CPUID 0x{observation.cpuid:08X} · '+tr('swd.core_verified'))
            page.target_identity.setText(f'{prefix}: {observed} | {tr("swd.project_target")}: {expected}')
            details.append(f'identity evidence={observation.target_evidence}; CPUID=0x{observation.cpuid:08X}; family=0x{observation.device_id:03X}; REV=0x{observation.revision_id:04X}')
        else:
            page.target_identity.setText(tr('swd.target_unknown'))
        if self.budget and active:
            details.append(tr('watch.budget').format(used=self.budget['bytes_used'],limit=self.budget['bytes_limit'],
                        samples=self.budget['samples_used'],seconds=int(self.budget['seconds_used'])))
        if self.core_observation and active:
            details.append(tr('watch.core_effects'))
        details.append(tr('swd.identity_limit'))
        page.swd_details_text.setPlainText('\n'.join(details))
        page.swd_target_status.setText(text)
        page.swd_status.setText(text)
        from services.swd_summary import Summary_Build
        summary = Summary_Build(self.rows,bool(self.snapshot and self.snapshot.symbols=='matched'))
        page.set_swd_summary(summary, matched=matched)
        page.swd_diagnostics.setVisible(bool(self.rows))
        selection = page.swd_diagnostics.selectedItems()
        selected_id = selection[0].text(0).split('\n')[-1] if selection else None
        page.swd_diagnostics.clear()
        preferred = None
        for row in self.rows:
            age = max(0,(time.monotonic_ns()-row['received_ns'])/1e9)
            item = QTreeWidgetItem([row['name']+'\n'+row['id'],DiagnosticState_Format('STALE' if age>3 else row['state'],self.window.i18n)+': '+DiagnosticReason_Format(row['reason'],self.window.i18n),
                    '; '.join(f'{k}={DiagnosticValue_Format(row["id"],k,v,self.window.i18n)}' for k,v in row['fields'].items()),
                    f'{age:.1f}s RX; '+row['consistency']])
            for column in range(4): item.setToolTip(column,item.text(column))
            item.setData(0,Qt.UserRole,'reason='+row['reason']+'; consistency='+row['consistency'])
            page.swd_diagnostics.addTopLevelItem(item)
            if row['id']==selected_id or preferred is None and row['state']=='UNKNOWN':preferred=item
        if preferred is not None:page.swd_diagnostics.setCurrentItem(preferred)
        page._SwdReason_Render()

    def _watch_changed(self, *_):
        self._watch_revision += 1
        self.watch_rows = ()
        panel = self.window.maintenance_page.swd_watch
        panel.update_rows((),bool(self.worker and self.snapshot and self.snapshot.symbols=='matched'))
        if self.worker:
            self.worker.set_selection(panel.selected if self.window.maintenance_page.watch_dialog.isVisible() else (),
                panel.interval.currentData(),panel.pause.isChecked(),self._watch_revision)

    def import_files(self, paths=None):
        if self.closing or self.import_worker or self._failed_owner or self._release_worker: return False
        if self.worker and self.worker.cancel.is_set():return False
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(self.window,'ssdiag','',
                'Project / R04 diagnostics (*.ssdiag);;Advanced ELF (requires matching descriptor / exact cached target) (*.elf)')
        if not paths: return False
        self._descriptor_path=next((str(path) for path in paths if Path(path).suffix.lower()=='.ssdiag'),None)
        self._restart_after_import = bool(self.worker and self._attach_intent)
        self._operation_error = None
        self._import_aborted = False
        self._pending_import_reply = None
        self._import_started = time.monotonic()
        self._restart_probe = self.worker.probe.identity if self.worker else ''
        self.snapshot = None
        self.watch_rows = ()
        self._watch_revision += 1
        if self.worker:
            self._cancel_worker(self.worker)
        self.firmware = None
        self.window.maintenance_page.console.set_protocol_declaration(None,loading=True)
        self.rows = ()
        self.import_detail = self.window.i18n.tr('swd.reimporting' if self._restart_after_import else 'swd.importing')
        self.status = 'swd.importing'
        self.import_worker = FirmwareWorker(paths,self._bound_targets,self)
        self.import_worker.update.connect(self._imported,Qt.QueuedConnection)
        self.import_worker.finished.connect(self._import_finished,Qt.QueuedConnection)
        self.import_worker.start()
        self.render()
        return True

    def relocate_elf(self,path=None):
        if not self._descriptor_path:return False
        if not path:
            path,_=QFileDialog.getOpenFileName(self.window,'ELF','', 'Matching ELF (*.elf)')
        return bool(path) and self.import_files([self._descriptor_path,str(path)])

    @Slot(object)
    def _imported(self, reply):
        if self.import_worker is None or self.sender() is not self.import_worker:
            return
        if self.closing or self.import_worker.cancel.is_set(): return
        self._pending_import_reply = reply

    def _apply_import(self, reply):
        self.detail = reply.detail
        self.window.maintenance_page.console.set_protocol_declaration(getattr(reply,'project_metadata',None))
        self._elf_selection_required = getattr(reply,'elf_selection_required',False)
        if reply.result == DiagnosticResult.Ok:
            self.firmware = reply.firmware
            available = sum(not e.unavailable for e in self.firmware.entries)
            self.import_detail = self.window.i18n.tr('swd.imported').format(
                target=self.firmware.target.name,sha=self.firmware.sha256[:12],
                available=available,total=len(self.firmware.entries))
            if self.firmware.provenance=='build_bound':
                if len(self._bound_targets)>=8: self._bound_targets.pop(next(iter(self._bound_targets)))
                self._bound_targets[self.firmware.sha256] = self.firmware.target.name
        else:
            self.firmware = None
            self._restart_after_import = self._attach_intent = False
            self.status = 'swd.import_required' if reply.result==DiagnosticResult.Unsupported else 'swd.import_failed'
            self.import_detail = self.window.i18n.tr(self.status)+': '+reply.detail
            if 'pending_build' in reply.detail:
                self.import_detail=Text(self.window.i18n,'待编译：成功构建后再导入符号','Pending build: import symbols after a successful build')+': '+reply.detail
        self.render()

    @Slot()
    def _import_finished(self):
        if self.import_worker is not None and self.sender() is self.import_worker:
            self._finish_import(self.import_worker)

    def _finish_import(self, worker):
        if worker is not self.import_worker:return
        self.import_worker = None
        if (worker.completed_at or time.monotonic())-self._import_started >= self.IMPORT_TIMEOUT_SECONDS:
            self._import_aborted = True
            self._operation_error = ('swd.import_timeout',self.window.i18n.tr('swd.import_timeout_detail'))
        if worker.cancel.is_set() or self._import_aborted:
            self.window.maintenance_page.console.set_protocol_declaration(None)
            self.firmware = None
            self._restart_after_import = self._attach_intent = False
            self.import_detail = self.window.i18n.tr('swd.cancelled')
            self.status = 'swd.cancelled'
        else:
            reply = worker.reply or self._pending_import_reply
            if not isinstance(reply,FirmwareReply):
                reply = FirmwareReply(DiagnosticResult.InvalidFile,'Import worker finished without a result')
            self._apply_import(reply)
        self._pending_import_reply = None
        worker.deleteLater()
        if self._operation_error:
            self.status,self.detail = self._operation_error
            self.import_detail = self.window.i18n.tr(self.status)
        elif self.firmware and not self._restart_after_import and self.worker is None:
            self.status = 'swd.detached'
        self._settle_owner()
        self.render()
        self._maybe_close()

    @Slot()
    def _release_finished(self):
        if self._release_worker is not None and self.sender() is self._release_worker:
            self._finish_release(self._release_worker)

    def _finish_release(self, worker):
        if worker is not self._release_worker:return
        self._release_worker = None
        reply = worker.reply
        if isinstance(reply,SwdReply) and reply.result == SwdResult.Ok:
            self._failed_owner.deleteLater()
            self._failed_owner = None
            self._operation_error = None
            self.status,self.detail = 'swd.detached',''
        else:
            self.closing = False
            self.status,self.detail = 'swd.release_failed',reply.detail if reply else 'Release outcome missing'
        worker.deleteLater()
        self._settle_owner();self.render();self._maybe_close()

    @staticmethod
    def _cancel_worker(worker):
        if worker.cancel_started is None:worker.cancel_started = time.monotonic()
        worker.cancel.set()

    def _cancel_timeout(self):
        self._restart_after_import = self._attach_intent = False
        self._import_aborted = True
        self.closing = False
        self.snapshot,self.rows,self.watch_rows,self.firmware = None,(),(),None
        self.window.maintenance_page.console.set_protocol_declaration(None,loading=self.import_worker is not None)
        if self.import_worker:self._cancel_worker(self.import_worker)
        self.status = 'swd.cancel_pending'
        self.detail = self.window.i18n.tr('swd.cancel_pending_detail')
        self._operation_error = (self.status,self.detail)
        self.import_detail = self.window.i18n.tr(self.status)
        self.render()

    @Slot()
    def _poll_lifecycle(self):
        # Completion state is owned by each worker, independent of queued update
        # delivery order. Never destroy a running worker or force-terminate it.
        if self.import_worker and self.import_worker.isFinished():self._finish_import(self.import_worker)
        if self.worker and self.worker.isFinished():self._finish_swd(self.worker)
        if self._release_worker and self._release_worker.isFinished():self._finish_release(self._release_worker)
        now = time.monotonic()
        worker = self.import_worker
        if worker and not worker.cancel.is_set() and now-self._import_started >= self.IMPORT_TIMEOUT_SECONDS:
            self._import_aborted = True
            self._restart_after_import = self._attach_intent = False
            self._cancel_worker(worker)
            self.status = 'swd.import_timeout'
            self.detail = self.window.i18n.tr('swd.import_timeout_detail')
            self._operation_error = (self.status,self.detail)
            self.import_detail = self.window.i18n.tr(self.status)
            self.render()
        for worker in (self.worker,self.import_worker):
            if (worker and worker.cancel_started is not None and now-worker.cancel_started >= self.CANCEL_GRACE_SECONDS
                    and not getattr(worker,'timeout_reported',False)):
                worker.timeout_reported = True
                self._cancel_timeout()
        worker = self._release_worker
        if worker and not worker.timeout_reported and now-worker.started_at >= self.CANCEL_GRACE_SECONDS:
            worker.timeout_reported = True
            self._cancel_timeout()

    def _released(self):
        return self.worker is None and self.import_worker is None and self._failed_owner is None and self._release_worker is None

    def _maybe_close(self):
        if self.closing and self._released():
            self.timer.stop();self.lifecycle_timer.stop()
            self.window.close()

    def request_close(self):
        self.closing = True
        page = self.window.maintenance_page
        for dialog in (page.watch_dialog,page.swd_details,page.serial_details_dialog):
            dialog.close()
        self.detach()
        released = self._released()
        if released:
            self.timer.stop();self.lifecycle_timer.stop()
        elif self._operation_error:
            self.closing = False
        return released

    def shutdown(self):
        self.request_close()
        deadline = time.monotonic()+self.SHUTDOWN_WAIT_SECONDS
        for worker in (self.import_worker,self.worker,self._release_worker):
            if worker is not None:
                worker.wait(max(0,int((deadline-time.monotonic())*1000)))
        self._poll_lifecycle()
        return self._released()
