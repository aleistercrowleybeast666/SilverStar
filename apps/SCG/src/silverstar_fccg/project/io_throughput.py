"""Finite Ground PC byte-stream capacity, before offered-load qualification."""

from __future__ import annotations

from dataclasses import dataclass

from silverstar_fccg.project.model import ProjectModel


@dataclass(frozen=True, slots=True)
class GroundPcCapacity:
    interface: str
    serial_bytes_per_second: int | None
    air_tx_frame_bytes: int
    air_rx_frame_bytes: int
    maximum_full_air_tx_frames_per_second: int | None
    maximum_full_air_rx_frames_per_second: int | None
    qualification: str


def GroundPcCapacity_Resolve(model: ProjectModel) -> GroundPcCapacity:
    """Calculate an upper capacity bound, not a guaranteed traffic budget.

    GSP has six fixed frame bytes. AIR_TX adds one length byte; AIR_RX adds
    RSSI, SNR and one length byte. Status and ACK traffic further consume the
    actual stream, so the frame rates here cannot establish readiness alone.
    """
    mtu = model.air_link.packet_mtu
    if type(mtu) is not int or not 1 <= mtu <= 61:
        raise ValueError("Ground GSP AIR packet MTU must be in 1..61 bytes")
    tx_bytes = mtu + 7
    rx_bytes = mtu + 9
    ground = model.ground_target
    if ground.pc_interface == "uart":
        if type(ground.baudrate) is not int or ground.baudrate <= 0:
            raise ValueError("Ground UART baudrate must be positive")
        # 8N1 carries one byte in ten line bits in each direction.
        capacity = ground.baudrate // 10
        return GroundPcCapacity(
            ground.pc_interface, capacity, tx_bytes, rx_bytes,
            capacity // tx_bytes, capacity // rx_bytes,
            "OFFERED_LOAD_UNDECLARED",
        )
    if ground.pc_interface == "usb_cdc":
        return GroundPcCapacity(
            ground.pc_interface, None, tx_bytes, rx_bytes,
            None, None, "USB_CDC_CAPACITY_UNQUALIFIED",
        )
    raise ValueError("Ground PC interface is unbound")
