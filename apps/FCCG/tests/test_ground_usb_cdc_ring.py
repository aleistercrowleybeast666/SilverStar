from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from test_joint_sensor_library import _Command_Run, _Compiler_Get
from test_round2_targets import _GroundBoardProject_Get

from silverstar_fccg.generator.multi_target import _PcAdapter_Render

ROOT = Path(__file__).resolve().parents[1]
GROUND_INC = (
    ROOT / "plugins/builtin/silverstar_core_ground_0_1_0"
    / "payload/Ground/Core/Inc"
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
    (tmp_path / "usbd_cdc_if.h").write_text(
        "#ifndef __USBD_CDC_IF_H\n#define __USBD_CDC_IF_H\n"
        "#include <stdint.h>\n#define USBD_OK 0U\n#define USBD_BUSY 1U\n"
        "#define USBD_FAIL 2U\n"
        "uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);\n#endif\n",
        encoding="utf-8",
    )
    harness = tmp_path / "test_pc_byte_stream.c"
    harness.write_text(
        r"""
#include <assert.h>
#include <stdint.h>
#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"

static uint8_t s_transmit_result = USBD_BUSY;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{ assert(data != 0 && length == 3U); return s_transmit_result; }

int main(void)
{
    uint8_t input[700];
    uint8_t output[700];
    uint16_t index;
    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
    for (index = 0U; index < 700U; index++)
    { input[index] = (uint8_t)index; }
    PcByteStream_OnUsbReceive(input, 700U);
    assert(PcByteStream_OverflowCount_Get() == 189U);
    assert(PcByteStream_Read(output, 700U) == 511U);
    for (index = 0U; index < 511U; index++)
    { assert(output[index] == input[index]); }
    assert(PcByteStream_Read(output, 700U) == 0U);
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    s_transmit_result = USBD_OK;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_OK);
    s_transmit_result = USBD_FAIL;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_ERROR);
    return 0;
}
""",
        encoding="utf-8",
    )
    executable = tmp_path / "test_pc_byte_stream.exe"
    _Command_Run(
        [
            _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wvla", "-I" + str(tmp_path), "-I" + str(GROUND_INC),
            "-I" + str(GROUND_INC.parent.parent / "Protocol/Inc"),
            str(source), str(harness), "-o", str(executable),
        ],
        tmp_path,
        "compile",
    )
    _Command_Run([str(executable)], tmp_path, "run")
