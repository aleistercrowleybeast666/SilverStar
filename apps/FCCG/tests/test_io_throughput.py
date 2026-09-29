from __future__ import annotations

from dataclasses import replace

from silverstar_fccg.project.io_throughput import GroundPcCapacity_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create


def test_ground_uart_capacity_uses_gsp_overhead_and_8n1(builtin_catalog) -> None:
    model = ReferenceProject_Create("Capacity", catalog=builtin_catalog)
    model.ground_target = replace(
        model.ground_target, enabled=True, pc_interface="uart", baudrate=230400,
    )
    plan = GroundPcCapacity_Resolve(model)
    assert plan.serial_bytes_per_second == 23040
    assert plan.air_tx_frame_bytes == 68
    assert plan.air_rx_frame_bytes == 70
    assert plan.maximum_full_air_tx_frames_per_second == 338
    assert plan.maximum_full_air_rx_frames_per_second == 329
    assert plan.qualification == "OFFERED_LOAD_UNDECLARED"


def test_ground_usb_capacity_cannot_be_inferred_from_virtual_baud(builtin_catalog) -> None:
    model = ReferenceProject_Create("UsbCapacity", catalog=builtin_catalog)
    model.ground_target = replace(
        model.ground_target, enabled=True, pc_interface="usb_cdc", baudrate=230400,
    )
    plan = GroundPcCapacity_Resolve(model)
    assert plan.serial_bytes_per_second is None
    assert plan.maximum_full_air_rx_frames_per_second is None
    assert plan.qualification == "USB_CDC_CAPACITY_UNQUALIFIED"
