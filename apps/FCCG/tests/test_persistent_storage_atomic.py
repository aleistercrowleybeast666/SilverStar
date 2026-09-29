from __future__ import annotations

from pathlib import Path

from test_joint_sensor_library import _Command_Run, _Compiler_Get

ROOT = Path(__file__).resolve().parents[1]
STORAGE = (
    ROOT / "plugins/builtin/silverstar_device_storage_sd_sdio_fatfs"
    / "payload/Devices/Storage/SdSdioFatFs"
)
INTERFACES = (
    ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Interfaces/Inc"
)
COMMON = ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc"


def test_dual_slot_object_write_preserves_last_valid_generation(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "persistent_storage.exe"
    _Command_Run(
        [
            _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wconversion", "-Wsign-conversion", "-Wvla",
            "-I" + str(STORAGE / "Inc"),
            "-I" + str(INTERFACES), "-I" + str(COMMON),
            str(STORAGE / "Src/persistent_storage.c"),
            str(ROOT / "tests/host_storage/test_persistent_storage.c"),
            "-o", str(executable),
        ],
        tmp_path,
        "compile",
    )
    _Command_Run([str(executable)], tmp_path, "run")
