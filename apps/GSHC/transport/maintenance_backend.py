"""Dedicated Flight Controller maintenance UART session for MAG calibration."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from services.magnetometer_maintenance import (
    MAG_MAINTENANCE_MAX_LINE_BYTES,
    MagMaintenanceDecoder,
)
from transport.serial_backend import SerialConfig, SerialLink


class MagMaintenanceSession(QObject):
    sample_received = Signal(object)
    response_received = Signal(str)
    connection_changed = Signal(bool, str)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._link = SerialLink()
        self._decoder = MagMaintenanceDecoder()

    def open(self, port: str, baudrate: int) -> None:
        self.close()
        self._decoder = MagMaintenanceDecoder()
        worker = self._link.open(
            SerialConfig(
                port=port,
                baudrate=baudrate,
                read_chunk_size=512,
                tx_queue_max_frames=16,
            ),
            start=False,
        )
        # The serial QThread invokes only this bounded decoder directly. UI
        # updates cross back through queued Qt signals.
        worker.bytes_chunk_received.connect(self._on_chunk, Qt.DirectConnection)
        worker.connection_changed.connect(self.connection_changed)
        worker.error_occurred.connect(self.error_occurred)
        worker.start()

    def close(self) -> bool:
        return self._link.close()

    def send(self, command: str) -> bool:
        if (
            len(command) > MAG_MAINTENANCE_MAX_LINE_BYTES - 2
            or not command.isascii()
            or "\r" in command
            or "\n" in command
        ):
            return False
        worker = self._link.worker
        if worker is None or not worker.isRunning():
            return False
        worker.send_bytes((command + "\r\n").encode("ascii"))
        return True

    def _on_chunk(self, chunk: bytes) -> None:
        samples, responses = self._decoder.feed_records(chunk)
        for sample in samples:
            self.sample_received.emit(sample)
        for response in responses:
            self.response_received.emit(response)
