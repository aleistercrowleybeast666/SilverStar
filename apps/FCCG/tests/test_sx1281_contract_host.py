from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def radio_contract_executable(tmp_path_factory):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("Host GCC unavailable")
    root = Path(__file__).resolve().parents[1]
    core = root / "plugins/builtin/silverstar_core_0_1_0/payload"
    radio = root / "plugins/builtin/silverstar_device_telemetry_sx1281/payload"
    executable = tmp_path_factory.mktemp("sx1281-contract") / "contract.exe"
    includes = [
        core / "Tests/Host/Fixtures/MultiInstance/Inc", core / "Tests/Host",
        core / "Common/Inc", core / "Common/Src", core / "Interfaces/Inc",
        root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc",
        radio / "Devices/Telemetry/SX1281/Inc",
        radio / "Devices/Telemetry/SX1281/Src",
        radio / "Middlewares/Third_Party/SX1280lib",
    ]
    command = [gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
               *("-I" + str(path) for path in includes),
               str(root / "tests/fixtures/sx1281_contract_host.c"),
               str(core / "Tests/Host/Fixtures/MultiInstance/multi_instance_resources.c"),
               "-o", str(executable)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize("scenario", [
    "reinit", "normal", "instance", "tx_head", "tx_count", "tx_sequence",
    "tx_len", "rx_tail", "rx_len", "control_op", "control_id", "control_time",
    "control_state", "control_active_init", "flags", "packet_type", "rx_error",
    "radio_state", "tx_control_count", "tx_control_burst", "rx_window",
    "rx_count", "rx_sequence", "rx_done_flag", "force_packet_type", "try_busy",
    "raw_busy", "irq_busy", "diag_uninitialized",
    "air_sf", "air_bw", "air_cr", "air_crc", "air_header", "air_preamble", "rx_hold", "schedule_role",
])
def test_radio_contract_faults_and_normal_operation(radio_contract_executable, scenario):
    result = subprocess.run([str(radio_contract_executable), scenario],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
