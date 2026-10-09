from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from silverstar_fccg.generator.multi_target import _PcAdapter_Render
from test_joint_sensor_library import _Command_Run, _Compiler_Get
from test_round2_targets import _GroundBoardProject_Get

ROOT = Path(__file__).resolve().parents[1]
GROUND_INC = (
    ROOT / "plugins/builtin/silverstar_core_ground_0_1_0"
    / "payload/Ground/Core/Inc"
)


def test_uart_fallback_compiles_with_minimal_hal_header(
    builtin_catalog, tmp_path: Path,
) -> None:
    """The generated adapter must provide its own NULL declaration."""
    model = _GroundBoardProject_Get(builtin_catalog)
    source = tmp_path / "pc_byte_stream.c"
    source.write_text(_PcAdapter_Render(model), encoding="utf-8")
    (tmp_path / "main.h").write_text(
        "#ifndef __MAIN_H\n#define __MAIN_H\n#include <stdint.h>\n"
        "typedef struct { unsigned value; } UART_HandleTypeDef;\n"
        "typedef enum { HAL_OK, HAL_BUSY, HAL_ERROR } HAL_StatusTypeDef;\n"
        "HAL_StatusTypeDef HAL_UART_Receive(UART_HandleTypeDef *, uint8_t *, uint16_t, uint32_t);\n"
        "HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *, uint8_t *, uint16_t, uint32_t);\n"
        "#endif\n",
        encoding="utf-8",
    )
    _Command_Run(
        [
            _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I" + str(tmp_path), "-I" + str(GROUND_INC),
            "-c", str(source), "-o", str(tmp_path / "pc_byte_stream.o"),
        ],
        tmp_path,
        "compile",
    )


def test_usb_cdc_receive_ring_and_busy_backpressure(
    builtin_catalog, tmp_path: Path,
) -> None:
    model = _GroundBoardProject_Get(builtin_catalog)
    model.ground_target = replace(
        model.ground_target, pc_interface="usb_cdc",
    )
    source = tmp_path / "pc_byte_stream.c"
    source.write_text(_PcAdapter_Render(model), encoding="utf-8")
    host = GROUND_INC.parent.parent.parent / "Tests/Host"
    for source_name, name in (("usb_main.h", "main.h"), ("usb_device.h", "usb_device.h"),
                              ("usb_cdc_if.h", "usbd_cdc_if.h")):
        (tmp_path / name).write_bytes((host / source_name).read_bytes())
    harness = tmp_path / "test_pc_byte_stream.c"
    (tmp_path / "usbd_conf.h").write_text("/* Host stub. */\n", encoding="utf8")
    harness.write_bytes((host / "usb_cdc.c").read_bytes())
    executable = tmp_path / "test_pc_byte_stream.exe"
    _Command_Run(
        [
            _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wvla", "-I" + str(tmp_path), "-I" + str(GROUND_INC),
            "-I" + str(GROUND_INC.parent.parent / "Protocol/Inc"),
            "-I" + str(ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc"),
            str(source), str(harness), "-o", str(executable),
        ],
        tmp_path,
        "compile",
    )
    _Command_Run([str(executable)], tmp_path, "run")
