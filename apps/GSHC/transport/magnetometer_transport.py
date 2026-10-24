"""Magnetic capability adapter over the existing exclusive maintenance owner.

No port is opened here. Future transports implement the same operations rather
than routing these requests through AIR calibration commands.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from services.magnetometer_maintenance import MagMaintenance_CalibrationCommandBuild
from services.magnetometer_workflow import (
    MagCalibrationCapabilities, MagDevices_Parse, MagResponse_Fields, MagStatus_Parse,
)


class MaintenanceMagTransport(QObject):
    result_received = Signal(str, object, str)
    samples_received = Signal(object, int)
    connection_changed = Signal(bool, str)
    ended = Signal(bool, str)

    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.owner = None
        self.pending = None
        self.active = None
        self.stream_device = None
        self.ending = False
        self._deadline = 0.0
        self._drop_baseline = 0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.pump)

    def capabilities(self):
        owner = self.manager.owner
        connection_check = getattr(getattr(owner, "connected", None), "is_set", None)
        stopped_check = getattr(getattr(owner, "stop", None), "is_set", None)
        connected = bool(callable(connection_check) and callable(stopped_check)
                         and connection_check() and not stopped_check())
        return MagCalibrationCapabilities(
            "maintenance_serial", connected,
            frozenset(("devices", "stream", "apply", "save", "read")),
        )

    @property
    def session_active(self):
        return self.owner is not None

    def begin(self):
        if self.owner is not None:
            return self.owner is self.manager.owner and self.capabilities().connected
        if not self.capabilities().connected or not self.manager.mag_acquire():
            return False
        self.owner = self.manager.owner
        self.ending = False
        self._drop_baseline = self.owner.mag_dropped
        self.owner.mag_subscribe(True)
        self.timer.start()
        return True

    def _queue(self, operation, command, device=None):
        if self.owner is None or self.ending and operation != "stop" or self.pending or self.active:
            return False
        if self.owner is not self.manager.owner or not self.capabilities().connected:
            return False
        self.pending = (operation, command, device)
        self._deadline = time.monotonic() + 5.0
        return True

    def devices(self):
        return self._queue("devices", "MAG LIST")

    def stream(self, device, enabled):
        if enabled:
            accepted = self._queue("start", f"MAG {device.instance} STREAM START", device)
            if accepted:
                # A queued START may execute before its acknowledgement reaches UI.
                self.stream_device = device
                self.owner.mag_subscribe(True)
            return accepted
        return self._queue("stop", f"MAG {device.instance} STREAM STOP", device)

    def apply(self, device, fit):
        return self._queue("apply", MagMaintenance_CalibrationCommandBuild(
            device.instance, device.physical_device_id, fit), device)

    def save(self, device):
        return self._queue("save", f"MAG {device.instance} CAL SAVE", device)

    def read(self, device):
        return self._queue("read", f"MAG {device.instance} CAL READ", device)

    def pump(self):
        if self.owner is None:
            return
        if self.owner is not self.manager.owner or not self.capabilities().connected:
            self.link_changed(False, "Maintenance connection lost; remote stream stop is unconfirmed")
            return
        samples, dropped = self.owner.mag_take()
        if samples and not self.ending:
            self.samples_received.emit(samples, max(0, dropped - self._drop_baseline))
        if self.active is not None:
            return
        # A response precedes the owner's job_finished handoff. Ending must
        # retain the lease until that handoff, so the next TF job is available.
        if self.ending and self.manager.job_busy:
            return
        if self.ending and self.pending is None:
            if self.stream_device is None:
                self._release(True, "")
                return
            self._queue("stop", f"MAG {self.stream_device.instance} STREAM STOP", self.stream_device)
        if self.pending is None:
            return
        if time.monotonic() >= self._deadline:
            operation = self.pending[0]
            self.pending = None
            self.result_received.emit(operation, None, "Maintenance command queue timed out")
            if self.ending:
                self.ending = False
                self.ended.emit(False, "Stream stop unconfirmed; retry or disconnect maintenance")
            return
        if self.manager.job_busy or self.manager.worker is not None:
            return
        operation, command, device = self.pending
        if self.manager.send_command(command, magnetic=True):
            self.active, self.pending = (operation, command, device), None

    def accept_result(self, command, response, error):
        if self.active is None or command != self.active[1]:
            return
        operation, _, device = self.active
        self.active = None
        result = None
        try:
            if error:
                raise ValueError(error)
            if operation == "devices":
                result = MagDevices_Parse(response)
            elif operation == "read":
                result = MagStatus_Parse(response, device)
            else:
                verb = "STREAM" if operation in ("start", "stop") else "CAL"
                result = MagResponse_Fields(response, f"MAG {device.instance} {verb}")
                if operation in ("start", "stop"):
                    expected = "STARTED" if operation == "start" else "STOPPED"
                    if result.get("state") != expected:
                        raise ValueError("Magnetic stream state was not confirmed")
                elif result.get("action") != operation.upper() or result.get("accepted") != "1":
                    raise ValueError("Magnetic calibration action was not accepted")
        except ValueError as exc:
            error = str(exc)
            result = None
        if operation == "stop" and not error:
            self.stream_device = None
            self.owner.mag_subscribe(False)
        self.result_received.emit(operation, result, error)
        if self.ending and operation == "stop" and self.stream_device is not None:
            self.ending = False
            self.ended.emit(False, error or "Device did not confirm STREAM STOP")

    def end(self):
        if self.owner is None:
            self.ended.emit(True, "")
            return
        self.ending = True
        self.owner.mag_subscribe(False)
        # An unsubmitted START is safe to drop. A submitted START still requires STOP.
        if self.pending is not None:
            if self.pending[0] == "start" and self.active is None:
                self.stream_device = None
            self.pending = None
        self.pump()

    def _release(self, confirmed, detail):
        if self.owner is not None:
            self.owner.mag_subscribe(False)
        self.timer.stop()
        self.owner = self.pending = self.active = self.stream_device = None
        self.ending = False
        self.manager.mag_release()
        self.ended.emit(confirmed, detail)

    def link_changed(self, connected, detail):
        if not connected and self.owner is not None:
            self._release(False, detail)
        self.connection_changed.emit(bool(connected), detail)
