"""Transport-neutral magnetic calibration data and bounded sample ownership.

The fit and packet codec remain owned by the existing magnetic services.
Device output axes are not asserted to be calibrated installation/body axes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from services.magnetometer_calibration import (
    MAG_CALIBRATION_MAX_SAMPLES, MagCalibration_Fit, MagCalibrationFitResult,
)
from services.magnetometer_maintenance import MagMaintenanceSample


@dataclass(frozen=True)
class MagCalibrationDevice:
    instance: int
    physical_device_id: int
    name: str


@dataclass(frozen=True)
class MagCalibrationCapabilities:
    transport: str
    connected: bool
    operations: frozenset[str]


class MagCalibrationTransport(Protocol):
    """Async providers report completion through result_received and samples_received.

    Results are device tuples, MagCalibrationStatus or validated action mappings;
    wire parsing belongs to the provider, not the dialog. ended reports cleanup.

    Implementations must serialize commands, keep physical identity, bound sample
    delivery, and stop/unsubscribe on end(). No wireless fallback is implied.
    """
    result_received: object
    samples_received: object
    connection_changed: object
    ended: object
    stream_device: MagCalibrationDevice | None

    @property
    def session_active(self) -> bool: ...

    def capabilities(self) -> MagCalibrationCapabilities: ...
    def begin(self) -> bool: ...
    def devices(self) -> bool: ...
    def stream(self, device: MagCalibrationDevice, enabled: bool) -> bool: ...
    def apply(self, device: MagCalibrationDevice, fit: MagCalibrationFitResult) -> bool: ...
    def save(self, device: MagCalibrationDevice) -> bool: ...
    def read(self, device: MagCalibrationDevice) -> bool: ...
    def end(self) -> None: ...


def MagResponse_Fields(response: str, prefix: str) -> dict[str, str]:
    if not response.startswith("OK " + prefix + " "):
        raise ValueError(response or "No magnetic calibration response")
    fields = {}
    for pair in response[len(prefix) + 4:].split():
        key, separator, value = pair.partition("=")
        if not separator or not key or not value or key in fields:
            raise ValueError("Malformed magnetic calibration response")
        fields[key] = value
    return fields


def _uint(fields: dict[str, str], key: str, maximum=0xFFFFFFFF) -> int:
    value = fields.get(key, "")
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise ValueError("Invalid magnetic field: " + key)
    result = int(value)
    if result > maximum:
        raise ValueError("Out-of-range magnetic field: " + key)
    return result


def MagDevices_Parse(response: str) -> tuple[MagCalibrationDevice, ...]:
    if len(response) > 511 or not response.isascii() or any(ord(c) < 32 for c in response):
        raise ValueError("Invalid magnetic device-list response")
    blocks = response.split(" DATA ")
    count = _uint(MagResponse_Fields(blocks[0], "MAG LIST"), "count", 32)
    if len(blocks) - 1 != count:
        raise ValueError("Incomplete magnetic device list")
    result = []
    for block in blocks[1:]:
        # Firmware emits the human-readable device/model names unquoted.
        # Only these two terminal text fields may contain spaces; numeric
        # identity fields retain the strict unique key=value parser.
        head, marker, names = block.partition(" device=")
        device_name, model_marker, model_name = names.partition(" model=")
        if (not marker or not model_marker or not device_name or not model_name
                or len(device_name) > 96 or len(model_name) > 96
                or "=" in device_name or "=" in model_name):
            raise ValueError("Invalid magnetic device/model name")
        fields = MagResponse_Fields("OK DEVICE " + head, "DEVICE")
        instance = _uint(fields, "instance", 255)
        physical = _uint(fields, "physical_device_id", 65535)
        if not physical or any(row.instance == instance for row in result):
            raise ValueError("Invalid or duplicate magnetic device identity")
        name = device_name + " / " + model_name
        result.append(MagCalibrationDevice(instance, physical, name))
    return tuple(result)


@dataclass(frozen=True)
class MagCalibrationStatus:
    state: str
    generation: int
    physical_device_id: int
    instance: int
    saved: bool
    pending: bool
    failed: bool
    load_error: str


def MagStatus_Parse(response: str, device: MagCalibrationDevice) -> MagCalibrationStatus:
    fields = MagResponse_Fields(response, f"MAG {device.instance} CAL")
    state = fields.get("state")
    if state not in ("EMPTY", "APPLIED") or not fields.get("load_error"):
        raise ValueError("Incomplete magnetic calibration status")
    physical = _uint(fields, "physical_device_id", 65535)
    instance = _uint(fields, "instance", 255)
    # An empty slot has zero-initialized identity until its first APPLY/load.
    # This is unknown, never a replacement for the selected live device identity.
    empty_identity = state == "EMPTY" and physical == 0 and instance == 0
    if not empty_identity and (physical, instance) != (device.physical_device_id, device.instance):
        raise ValueError("Magnetic calibration physical identity changed")
    return MagCalibrationStatus(
        state, _uint(fields, "generation"), physical, instance,
        bool(_uint(fields, "saved", 1)), bool(_uint(fields, "pending", 1)),
        bool(_uint(fields, "failed", 1)), fields["load_error"],
    )


class MagSampleCollection:
    def __init__(self, device: MagCalibrationDevice):
        self.device = device
        self.points: list[tuple[float, float, float]] = []
        self.discarded = 0
        self.last_sequence: int | None = None
        self.last_timestamp: int | None = None

    def add(self, sample: MagMaintenanceSample) -> bool:
        if (sample.instance, sample.physical_device_id) != (
                self.device.instance, self.device.physical_device_id):
            raise ValueError("Magnetic sample physical identity changed")
        if self.last_sequence is not None:
            sequence_delta = (sample.sequence - self.last_sequence) & 0xFFFFFFFF
            time_delta = (sample.sample_timestamp_us - self.last_timestamp) & 0xFFFFFFFF
            if not 0 < sequence_delta < 0x80000000 or not 0 < time_delta < 0x80000000:
                self.discarded += 1
                return False
        if len(self.points) >= MAG_CALIBRATION_MAX_SAMPLES:
            self.discarded += 1
            return False
        self.points.append(sample.field_uT)
        self.last_sequence = sample.sequence
        self.last_timestamp = sample.sample_timestamp_us
        return True

    def fit(self, reference_field_uT: float) -> MagCalibrationFitResult:
        return MagCalibration_Fit(np.asarray(self.points).reshape((-1, 3)), reference_field_uT)
