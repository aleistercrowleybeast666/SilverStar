from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def radio_handshake_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    configured = os.environ.get("SILVERSTAR_RADIO_GENERATED_PROJECT")
    if configured:
        project = Path(configured).resolve()
    else:
        from silverstar_fccg.app.service import FccgService
        service = FccgService(root)
        model = service.Project_Open(root / "tests/fixtures/radio_handshake.ssproject")
        project = tmp_path_factory.mktemp("radio-handshake-generated") / "Flight_Controller"
        service.Project_Save(model, project, confirm_dangerous=True)
    assert (project / "Platform/STM32F4/Src/platform_time_stm32f4.c").is_file()
    executable = tmp_path_factory.mktemp("radio-handshake-build") / "radio.exe"
    includes = [p for p in project.rglob("Inc") if "build" not in p.parts]
    includes += [project / p for p in ["System/User", "Tests/Host",
        "Devices/Telemetry/SX1281/Src", "Modules/Src", "Middlewares/Third_Party/SX1280lib"]]
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
        "-DSILVERSTAR_AIR_LINK_ENABLED=1",
        "-include", str(project / "Generated/Inc/project_flight_config.h")]
    for path in includes:
        command.extend(["-I", str(path)])
    command += [str(root / "tests/fixtures/radio_handshake_host.c")]
    command += [str(project / path) for path in [
        "Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c",
        "Generated/Src/project_resources.c", "Protocol/Src/air_protocol.c",
        "Common/Src/silverstar_assert.c", "System/Calibration/Src/system_calibration_correction.c"]]
    command += ["-lm", "-o", str(executable)]
    result = subprocess.run(command, cwd=project, capture_output=True, text=True,
                            encoding="utf8", errors="replace", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable, project


@pytest.mark.parametrize("scenario", [
    "ack_backlog", "cap_queued", "queue_boundaries", "ack_full", "rx_fairness",
    "token_wrap", "cap_sequence_wrap", "cap_clock_wrap", "cap_reconnect_cache",
    "spi_fault_health", "cap_tx_timeout", "mixed_tokens", "cap_long_expiry", "cap_pending_long_expiry",
])
def test_generated_radio_handshake(radio_handshake_executable, scenario):
    executable, project = radio_handshake_executable
    result = subprocess.run([str(executable), scenario], cwd=project, capture_output=True,
                            text=True, encoding="utf8", errors="replace", timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
