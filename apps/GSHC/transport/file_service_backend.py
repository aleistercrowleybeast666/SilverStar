"""Exclusive maintenance UART/USB Console; constructed only in a worker thread."""
from __future__ import annotations

import time
from threading import Event

import serial
from services.device_export import ExportCancelled
from transport.serial_options import SerialBaud_Parse


class FileServiceSerialTransport:
    def __init__(self, port: str, baudrate: int, *, serial_factory=serial.Serial) -> None:
        if not port.strip() or type(baudrate) is not int or SerialBaud_Parse(str(baudrate)) == 0:
            raise ValueError("Select an explicit maintenance UART/USB port and baud rate")
        self._serial = serial_factory(port=port, baudrate=baudrate, timeout=0.05, write_timeout=0.5)
        self._buffer = bytearray()

    def close(self) -> None:
        self._serial.close()

    def prepare_job(self) -> None:
        self._buffer.clear()
        self._serial.reset_input_buffer()

    def check_alive(self) -> None:
        # A bounded idle read detects unplug/driver errors in the owner thread.
        self._serial.read(128)

    def exchange(self, command: str, timeout: float, cancel: Event) -> str:
        if len(command) > 191 or not command.isascii() or "\r" in command or "\n" in command:
            raise ValueError("Invalid maintenance command")
        payload = (command + "\r\n").encode("ascii")
        if self._serial.write(payload) != len(payload):
            raise OSError("Incomplete maintenance command write")
        deadline = time.monotonic() + timeout
        discarded = 0
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise ExportCancelled("Maintenance operation cancelled")
            chunk = self._serial.read(128)
            self._buffer.extend(chunk)
            if len(self._buffer) > 1024:
                raise OSError("Maintenance response buffer exceeded its bound")
            while b"\n" in self._buffer:
                raw, _, remaining = self._buffer.partition(b"\n")
                self._buffer = bytearray(remaining)
                if len(raw) > 511:
                    raise OSError("Oversized maintenance response")
                line = raw.decode("ascii", errors="strict").strip()
                if command == "LOGFILE CAPS" and line.startswith("ERR "):
                    return line
                if command in {"SYSTEM INFO", "SYSTEM STATUS", "SYSTEM CAPABILITIES", "LOG STATUS"}:
                    for prefix in ("OK " + command + " ", "ERR " + command + " "):
                        if line.startswith(prefix) or line.startswith("> " + prefix):
                            return line.removeprefix("> ")
                    # A generic parse error is unavailable, never a status.
                    if line.startswith("ERR "):
                        return line
                    discarded += 1
                    if discarded > 32:
                        raise OSError("Too many unrelated maintenance lines")
                    continue
                # Console may emit a prompt, command echo or diagnostic line.
                # Only complete protocol responses are returned to the client.
                marker = next((line.find(prefix) for prefix in ("OK LOGFILE ", "ERR LOGFILE ", "PENDING LOGFILE ") if prefix in line), -1)
                if marker >= 0:
                    return line[marker:]
                discarded += 1
                if discarded > 32:
                    raise OSError("Too many unrelated maintenance lines")
        raise TimeoutError("Maintenance response timed out; reconnect and renegotiate")


__all__ = ["FileServiceSerialTransport"]
