import shutil
import subprocess
from pathlib import Path
import pytest


@pytest.fixture(scope="module")
def hal_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None: pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    radio = root / "plugins/builtin/silverstar_device_telemetry_sx1281/payload"
    includes = [core / "Tests/Host/Fixtures/MultiInstance/Inc", core / "Common/Inc", core / "Common/Src",
        core / "Interfaces/Inc", root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
        radio / "Devices/Telemetry/SX1281/Inc", radio / "Middlewares/Third_Party/SX1280lib"]
    executable = tmp_path_factory.mktemp("ground-hal") / "hal.exe"
    result = subprocess.run([gcc,"-std=c11","-O2","-Wall","-Wextra","-Werror","-pedantic",
        "-DAIR_LINK_HAL_BUFFER_SIZE=260U", *("-I" + str(path) for path in includes),
        str(root / "tests/fixtures/ground_radio_hal_host.c"),"-o",str(executable)],
        capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize("scenario", ["normal","iram","size","register","null","index"])
def test_capacity_contract(hal_executable, scenario):
    result = subprocess.run([str(hal_executable), scenario],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
