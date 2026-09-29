"""Bounded line decoder for the Flight Controller maintenance MAG stream."""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass

from services.magnetometer_calibration import (
    MagCalibrationFitResult,
    MagCalibrationFitStatus,
)

MAG_MAINTENANCE_MAX_LINE_BYTES = 192
MAG_MAINTENANCE_MAX_CHUNK_BYTES = 4096
MAG_CALIBRATION_SCHEMA_REVISION = 1
MAG_CALIBRATION_ALGORITHM_REVISION = 1
MAG_CALIBRATION_PACKET = struct.Struct("<BBHBB16f8BH")


@dataclass(frozen=True)
class MagMaintenanceSample:
    instance: int
    physical_device_id: int
    sequence: int
    sample_timestamp_us: int
    field_uT: tuple[float, float, float]


class MagMaintenanceDecoder:
    """Accept complete ASCII records; discard oversized or malformed lines."""

    def __init__(self) -> None:
        self._line = bytearray()
        self._discarding = False
        self.discarded_lines = 0

    def feed(self, chunk: bytes) -> list[MagMaintenanceSample]:
        return self.feed_records(chunk)[0]

    def feed_records(
        self, chunk: bytes
    ) -> tuple[list[MagMaintenanceSample], list[str]]:
        if len(chunk) > MAG_MAINTENANCE_MAX_CHUNK_BYTES:
            self.discarded_lines += 1
            self._line.clear()
            self._discarding = True
            return [], []
        samples: list[MagMaintenanceSample] = []
        responses: list[str] = []
        for byte in chunk:
            if byte in (10, 13):
                if not self._discarding and self._line:
                    line = bytes(self._line)
                    sample = MagMaintenance_ParseSample(line)
                    if sample is not None:
                        samples.append(sample)
                    elif line.startswith((b"OK ", b"ERR ")):
                        try:
                            responses.append(line.decode("ascii", errors="strict"))
                        except UnicodeDecodeError:
                            self.discarded_lines += 1
                self._line.clear()
                self._discarding = False
            elif not self._discarding:
                if len(self._line) >= MAG_MAINTENANCE_MAX_LINE_BYTES:
                    self.discarded_lines += 1
                    self._line.clear()
                    self._discarding = True
                else:
                    self._line.append(byte)
        return samples, responses


def MagMaintenance_ParseSample(line: bytes) -> MagMaintenanceSample | None:
    try:
        text = line.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None
    if not text.startswith("EVENT MAG SAMPLE "):
        return None
    fields: dict[str, str] = {}
    for item in text.split()[3:]:
        key, separator, value = item.partition("=")
        if not separator or key in fields:
            return None
        fields[key] = value
    if set(fields) != {
        "instance", "physical_device_id", "seq", "sample_us",
        "x_uT", "y_uT", "z_uT",
    }:
        return None
    try:
        instance = int(fields["instance"])
        physical_id = int(fields["physical_device_id"])
        sequence = int(fields["seq"])
        timestamp = int(fields["sample_us"])
        vector = tuple(float(fields[key]) for key in ("x_uT", "y_uT", "z_uT"))
    except ValueError:
        return None
    if (
        not 0 <= instance <= 255
        or not 0 < physical_id <= 65535
        or not 0 <= sequence <= 0xFFFFFFFF
        or not 0 <= timestamp <= 0xFFFFFFFF
        or any(not math.isfinite(value) or abs(value) > 1000.0 for value in vector)
    ):
        return None
    return MagMaintenanceSample(instance, physical_id, sequence, timestamp, vector)


def MagMaintenance_CalibrationPacketBuild(
    instance: int,
    physical_device_id: int,
    fit: MagCalibrationFitResult,
) -> bytes:
    """Build the fixed 84-byte little-endian maintenance calibration object."""
    if (
        fit.status is not MagCalibrationFitStatus.READY
        or fit.hard_iron_uT is None
        or fit.soft_iron is None
        or fit.reference_field_uT is None
        or fit.rms_residual_uT is None
        or fit.max_residual_uT is None
        or fit.axis_condition is None
        or len(fit.octant_counts) != 8
        or not 0 <= instance <= 255
        or not 0 < physical_device_id <= 65535
        or not 128 <= fit.sample_count <= 4096
    ):
        raise ValueError("A complete ready fit and exact physical identity are required")
    values = (
        *fit.hard_iron_uT,
        *(value for row in fit.soft_iron for value in row),
        fit.reference_field_uT,
        fit.rms_residual_uT,
        fit.max_residual_uT,
        fit.axis_condition,
    )
    if len(values) != 16 or not all(math.isfinite(value) for value in values):
        raise ValueError("Calibration matrix and metrics must be finite")
    body = MAG_CALIBRATION_PACKET.pack(
        MAG_CALIBRATION_SCHEMA_REVISION,
        MAG_CALIBRATION_ALGORITHM_REVISION,
        physical_device_id,
        instance,
        0,
        *values,
        *(min(255, count) for count in fit.octant_counts),
        fit.sample_count,
    )
    return body + struct.pack("<I", zlib.crc32(body))


def MagMaintenance_CalibrationCommandBuild(
    instance: int,
    physical_device_id: int,
    fit: MagCalibrationFitResult,
) -> str:
    packet = MagMaintenance_CalibrationPacketBuild(instance, physical_device_id, fit)
    command = f"MAG {instance} CAL APPLY {packet.hex().upper()}"
    if len(command) > MAG_MAINTENANCE_MAX_LINE_BYTES - 2:
        raise ValueError("Calibration command exceeds maintenance line capacity")
    return command
