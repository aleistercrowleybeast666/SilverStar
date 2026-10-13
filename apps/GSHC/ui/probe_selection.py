"""Asynchronous host probe inventory; selection does not create a debug session."""
from threading import Event
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult, ProbeInventory_Read, ProbeSelection


class ProbeInventoryWorker(QThread):
    completed = Signal(object)

    def __init__(self, enumerator, parent=None):
        super().__init__(parent)
        self.enumerator = enumerator
        self.cancel = Event()

    def run(self):
        try:
            result = self.enumerator(self.cancel)
        except Exception as exc:
            result = ProbeInventory(ProbeInventoryResult.Failed, detail=str(exc)[:300])
        self.completed.emit(result)


class ProbeSelectionManager(QObject):
    def __init__(self, controller, enumerator=None):
        super().__init__(controller)
        self.window = controller.window
        self.enumerator = enumerator or ProbeInventory_Read
        self.selection = ProbeSelection()
        self.worker = None
        self.target_active = False
        self.closing = False
        self.status = 'probe.not_scanned'
        self.detail = ''
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.refresh)
        self.window.btn_probe_refresh.clicked.connect(self.refresh)
        self.window.probe_combo.currentIndexChanged.connect(self._selected)
        self.window.on_probe_render = self.render
        self.render()
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        if self.closing or self.worker is not None or self.target_active:
            return False
        self.timer.stop()
        self.status = 'probe.busy'
        self.render()
        self.worker = ProbeInventoryWorker(self.enumerator, self)
        self.worker.completed.connect(self._completed)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        return True

    def _completed(self, inventory):
        if self.closing:
            return
        lost = self.selection.apply(inventory)
        self.detail = inventory.detail
        if lost and inventory.result == ProbeInventoryResult.Ready:
            self.status = 'probe.removed'
        elif inventory.result == ProbeInventoryResult.Ready:
            self.status = 'probe.selected' if self.selection.identity else 'probe.available'
        else:
            self.status = 'probe.' + inventory.result.value
        self.render()
        if inventory.result in (ProbeInventoryResult.Ready, ProbeInventoryResult.Empty):
            self.timer.start()

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        if self.closing:
            self.window.close()
        else:
            self.render()

    def _selected(self, _index):
        if self.closing or self.worker is not None or self.target_active:
            return
        if self.selection.select(self.window.probe_combo.currentData() or ''):
            self.status = 'probe.selected' if self.selection.identity else ('probe.available' if self.selection.probes else 'probe.empty')
            self.render()

    def render(self):
        window = self.window
        tr = window.i18n.tr
        combo = window.probe_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(tr('probe.choose'), '')
        for probe in self.selection.probes:
            combo.addItem(probe.label, probe.identity)
            combo.setItemData(combo.count()-1, probe.identity, Qt.ToolTipRole)
        combo.setCurrentIndex(max(0, combo.findData(self.selection.identity)))
        combo.blockSignals(False)
        busy = self.status == 'probe.busy' or self.worker is not None or self.target_active
        combo.setEnabled(not busy and bool(self.selection.probes) and not self.closing)
        window.btn_probe_refresh.setEnabled(not busy and not self.closing)
        detail = self.detail
        selected = next((p for p in self.selection.probes if p.identity == self.selection.identity), None)
        if selected is not None:
            detail = f'{selected.label}\nID: {selected.identity} ({selected.identity_kind})\nHost PnP: {selected.host_status}\n' + '\n'.join(selected.interfaces)
        display_status = 'probe.in_session' if self.target_active else self.status
        window.set_probe_status(tr(display_status), detail)

    def request_close(self):
        self.closing = True
        self.timer.stop()
        self.selection = ProbeSelection()
        self.status, self.detail = 'probe.cancelled', ''
        self.render()
        if self.worker is not None:
            self.worker.cancel.set()
        return self.worker is None

    def shutdown(self):
        self.request_close()
        return self.worker is None or self.worker.wait(2500)
